#!/usr/bin/env bash
# CrimeAI one-command launcher for macOS and Linux.
#
#   ./start.sh            install what is missing, build, start, seed demo data, open the app
#   ./start.sh stop       stop everything (data is kept)
#   ./start.sh status     show running services
#   ./start.sh logs       follow API and worker logs
#   ./start.sh reset      delete all data and start again from scratch
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/crimeai"
COMPOSE_FILE="$ROOT/docker-compose.dev.yml"
CRED_FILE="$ROOT/backend/var/demo-credentials.txt"
APP_URL="http://localhost:5173"
API_URL="http://localhost:8000"

say() { printf '\033[36m==> %s\033[0m\n' "$*"; }
fail() { printf '\n\033[31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }
compose() { docker compose -f "$COMPOSE_FILE" "$@" || fail "docker compose $* failed."; }
# One image at a time (parallel torch builds can drop Docker's build engine); on failure prune the
# cache, which a mid-build Docker restart can leave broken, and retry once.
build_images() {
  export COMPOSE_PARALLEL_LIMIT=1
  docker compose -f "$COMPOSE_FILE" build && return
  say "Build failed; clearing the Docker build cache and retrying once..."
  docker builder prune -f >/dev/null 2>&1 || true
  docker compose -f "$COMPOSE_FILE" build || fail "Image build failed twice. Restart Docker, wait until it is running, then run ./start.sh again."
}

ensure_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    say "Docker is not installed."
    case "$(uname -s)" in
      Darwin)
        command -v brew >/dev/null 2>&1 || fail "Install Docker Desktop from https://www.docker.com/products/docker-desktop/ and rerun."
        say "Installing Docker Desktop with Homebrew..."
        brew install --cask docker
        open -a Docker ;;
      Linux)
        read -r -p "Install Docker Engine with Docker's official script (needs sudo)? [y/N] " ok
        [[ "$ok" =~ ^[Yy]$ ]] || fail "Install Docker from https://docs.docker.com/engine/install/ and rerun."
        curl -fsSL https://get.docker.com | sudo sh
        sudo usermod -aG docker "$USER" || true
        fail "Docker is installed. Log out and back in (so your user can use Docker), then rerun." ;;
      *) fail "Install Docker Desktop and rerun." ;;
    esac
  fi
  if ! docker info >/dev/null 2>&1; then
    [[ "$(uname -s)" == "Darwin" ]] && { say "Starting Docker Desktop..."; open -a Docker || true; }
    [[ "$(uname -s)" == "Linux" ]] && { say "Starting the Docker service..."; sudo systemctl start docker || true; }
    for _ in $(seq 1 60); do docker info >/dev/null 2>&1 && break; sleep 3; done
    docker info >/dev/null 2>&1 || fail "Docker is not running. Start it and rerun."
  fi
  docker compose version >/dev/null 2>&1 || fail "Docker Compose v2 is required. Update Docker and rerun."
}

# Name of a non-Docker process listening on a port, or nothing when the port is free or held by Docker.
foreign_listener() {
  command -v lsof >/dev/null 2>&1 || return 0
  local owner
  owner="$( { lsof -nP -iTCP:"$1" -sTCP:LISTEN -Fc 2>/dev/null || true; } | sed -n 's/^c//p'             | grep -Ev '^(com\.docker|docker|vpnkit|rootlessport)' | head -1 || true)"
  printf '%s' "$owner"
}

resolve_ports() {
  # The app's URL and API origin are fixed, so these two must be free.
  for port in 5173 8000; do
    owner="$(foreign_listener "$port")"
    [[ -z "$owner" ]] || fail "Port $port is already used by '$owner'. Close it and rerun."
  done
  # Database and Redis ports are only for connecting from this machine; move them if something else has them.
  local port
  port=5433; while [[ -n "$(foreign_listener "$port")" ]]; do port=$((port + 1)); done
  [[ "$port" == 5433 ]] || say "YugabyteDB: port 5433 is taken; using $port instead."
  export CRIMEAI_DB_PORT="$port"
  port=6379; while [[ -n "$(foreign_listener "$port")" ]]; do port=$((port + 1)); done
  [[ "$port" == 6379 ]] || say "Redis: port 6379 is taken; using $port instead."
  export CRIMEAI_REDIS_PORT="$port"
}

wait_http() {
  local url="$1" label="$2" minutes="$3" deadline=$(( $(date +%s) + $3 * 60 ))
  printf '    waiting for %s' "$label"
  until curl -fsS -o /dev/null --max-time 5 "$url"; do
    (( $(date +%s) > deadline )) && { echo; fail "$label did not come up within $minutes minutes. See: ./start.sh logs"; }
    printf '.'; sleep 5
  done
  echo ' ready'
}

init_demo_data() {
  local users
  users="$(docker compose -f "$COMPOSE_FILE" exec -T db bash -c 'bin/ysqlsh -h $(hostname) -U crimeai -d crimeai -tAc "SELECT count(*) FROM users"' 2>/dev/null | tr -d '[:space:]' || true)"
  if [[ -n "$users" && "$users" != "0" ]]; then say "Demo data already loaded."; return; fi
  local password
  password="$(head -c 400 /dev/urandom | LC_ALL=C tr -dc 'abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789' | cut -c1-14)aA1"
  say "Loading demo data (3,000 cases, FIRs in several Indian languages, a planted crime series)..."
  compose exec -T -e "SEED_PASSWORD=$password" -e LOG_LEVEL=WARNING api python scripts/seed_data.py
  mkdir -p "$(dirname "$CRED_FILE")"
  cat >"$CRED_FILE" <<EOF
CrimeAI local demo users (all share one password)

admin@crimeai.example     (Admin)
analyst@crimeai.example   (Analyst)
police@crimeai.example    (Police / SHO)
readonly@crimeai.example  (Read-only)
officer01..05@crimeai.example (Police)

password: $password
EOF
  say "Training models and building intelligence (a few minutes on first run)..."
  compose exec -T -e LOG_LEVEL=WARNING worker python scripts/bootstrap_demo.py
}

# Meko shared memory: datapacks, SOPs and partner-agency history. Idempotent; skipped without MEKO_API_KEY.
init_meko() {
  if ! grep -qE '^MEKO_API_KEY=\S+' "$ROOT/backend/.env" 2>/dev/null; then
    say "Meko is off (add MEKO_API_KEY=mko_tkn_... to crimeai/backend/.env and run start again to turn it on)."
    return
  fi
  say "Setting up Meko shared memory (datapacks, SOPs, partner agencies)..."
  docker compose -f "$COMPOSE_FILE" exec -T -e LOG_LEVEL=WARNING api python scripts/meko_setup.py \
    || say "Meko setup did not finish; the app still runs. Retry: ./start.sh"
}

show_summary() {
  local password="(see crimeai/backend/var/demo-credentials.txt)"
  [[ -f "$CRED_FILE" ]] && password="$(sed -n 's/^password:[[:space:]]*//p' "$CRED_FILE" | head -1)"
  printf '\n  \033[32mCrimeAI is running\033[0m\n'
  echo   "  ------------------------------------------------------------"
  printf '  App        \033[33m%s\033[0m\n' "$APP_URL"
  echo   "  API docs   $API_URL/docs"
  echo   "  Login      admin@crimeai.example   (sees every screen; also analyst@ / police@ / readonly@)"
  echo   "  Password   $password"
  echo   "  ------------------------------------------------------------"
  echo   "  Stop: ./start.sh stop    Logs: ./start.sh logs    Fresh start: ./start.sh reset"
  echo
}

open_browser() {
  if command -v open >/dev/null 2>&1; then open "$APP_URL"
  elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$APP_URL" >/dev/null 2>&1 || true
  fi
}

case "${1:-up}" in
  stop)   ensure_docker; compose stop; say "Stopped. Your data is kept; run ./start.sh to start again." ;;
  status) ensure_docker; compose ps ;;
  logs)   ensure_docker; docker compose -f "$COMPOSE_FILE" logs -f --tail 100 api worker ;;
  reset)
    ensure_docker
    read -r -p "This deletes all CrimeAI data (cases, FIRs, users, uploads). Type YES to continue: " answer
    [[ "$answer" == "YES" ]] || fail "Cancelled."
    compose down -v; rm -f "$CRED_FILE"
    say "All data removed. Run ./start.sh to start fresh." ;;
  up)
    ensure_docker
    resolve_ports
    say "Building and starting CrimeAI (the first run downloads about 3 GB and can take 10-20 minutes)..."
    build_images
    compose up -d
    wait_http "$API_URL/health" "API" 15
    init_demo_data
    init_meko
    wait_http "$APP_URL" "web app" 15
    show_summary
    open_browser ;;
  *) fail "Unknown command '$1'. Use: up | stop | status | logs | reset" ;;
esac

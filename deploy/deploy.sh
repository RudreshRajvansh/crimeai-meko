#!/usr/bin/env bash
# One-command production deploy on a fresh Ubuntu/Debian VM (e.g. a GCP Compute Engine instance).
#
#   GEMINI_API_KEY=your-key bash deploy/deploy.sh
#
# Installs Docker, writes random secrets to crimeai/.env, serves HTTPS at <external-ip>.sslip.io
# (or DOMAIN=your.domain), builds and starts the stack, loads the demo data on first run, and
# prints the URL and login. Safe to re-run: it keeps the secrets and data from the first run.
set -euo pipefail
cd "$(dirname "$0")/../crimeai"
say() { printf '\n==> %s\n' "$*"; }

if ! command -v docker >/dev/null 2>&1; then
  say "Installing Docker"
  curl -fsSL https://get.docker.com | sudo sh
fi
DOCKER=docker
docker info >/dev/null 2>&1 || DOCKER="sudo docker"

# The ML images and the embedding model need headroom on smaller machines.
if [ "$(swapon --show | wc -l)" -eq 0 ]; then
  say "Adding 4 GB of swap"
  sudo fallocate -l 4G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile >/dev/null
  sudo swapon /swapfile && echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
fi

ip=$(curl -fsS -H "Metadata-Flavor: Google" \
  http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/access-configs/0/external-ip 2>/dev/null \
  || curl -fsS https://api.ipify.org || true)

if [ ! -f .env ]; then
  say "Writing secrets to crimeai/.env"
  rnd() { openssl rand -hex 32; }
  umask 077
  cat > .env <<ENV
DOMAIN=${DOMAIN:-${ip//./-}.sslip.io}
POSTGRES_PASSWORD=$(rnd)
APP_SECRET_KEY=$(rnd)
JWT_SECRET_KEY=$(rnd)
ENTITY_HASH_KEY=$(rnd)
DEMO_PASSWORD=Demo-$(openssl rand -hex 6)
ENV
fi
set -a; . ./.env; set +a
# A VM restarted without a reserved IP comes back on a new address: follow it unless a real domain was set.
if [ -n "$ip" ] && [[ "$DOMAIN" == *.sslip.io ]] && [ "$DOMAIN" != "${ip//./-}.sslip.io" ]; then
  DOMAIN="${ip//./-}.sslip.io"
  sed -i "s/^DOMAIN=.*/DOMAIN=$DOMAIN/" .env
  say "New IP: serving at https://$DOMAIN"
fi
# On Google Cloud, Vertex AI backs up the Gemini API keys, paid from this project and authorised by the VM's
# service account (needs the cloud-platform scope and roles/aiplatform.user).
VERTEX_PROJECT=${VERTEX_PROJECT:-$(curl -sf -m 2 -H "Metadata-Flavor: Google" \
  http://169.254.169.254/computeMetadata/v1/project/project-id || true)}
if [ -n "${GEMINI_API_KEY:-}" ] || [ -n "$VERTEX_PROJECT" ]; then
  (umask 077; printf 'GEMINI_API_KEY=%s\nVERTEX_PROJECT=%s\n' "${GEMINI_API_KEY:-}" "$VERTEX_PROJECT" > backend/.env)
fi

C="$DOCKER compose -f docker-compose.prod.yml"
say "Building images one at a time (first run takes 10-20 minutes)"
COMPOSE_PARALLEL_LIMIT=1 $C build
say "Starting CrimeAI"
$C up -d
say "Waiting for the API"
until $C exec -T api curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; do sleep 5; done

users=$($C exec -T db psql -U crimeai -d crimeai -tAc 'SELECT count(*) FROM users' | tr -d '[:space:]')
if [ "$users" = "0" ]; then
  say "Loading demo data and training the models (about 3 minutes)"
  # The seed script refuses APP_ENV=production; staging keeps every other production check.
  $C exec -T -e APP_ENV=staging -e SEED_PASSWORD="$DEMO_PASSWORD" -e LOG_LEVEL=WARNING api python scripts/seed_data.py
  $C exec -T -e LOG_LEVEL=WARNING worker python scripts/bootstrap_demo.py
fi

say "CrimeAI is live: https://$DOMAIN"
echo "    Login: admin@crimeai.example / $DEMO_PASSWORD   (also analyst@, police@, readonly@)"
echo "    The HTTPS certificate is issued on the first visit; give it a few seconds."

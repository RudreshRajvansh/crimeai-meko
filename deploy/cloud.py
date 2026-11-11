#!/usr/bin/env python3
"""
Deploy CrimeAI to DigitalOcean: one droplet in Bangalore running the production stack (Caddy with HTTPS, API,
workers, YugabyteDB, Redis) through deploy/deploy.sh. DIGITALOCEAN_TOKEN in the environment.

  python deploy/cloud.py up                  # create the droplet, then ship
  python deploy/cloud.py create              # only create the droplet and print its address
  python deploy/cloud.py ship 203.0.113.10   # copy the code and keys to an existing droplet and (re)deploy

`up` and `create` create a billable droplet: 4 vCPU / 8 GB in blr1, with your SSH public key
(~/.ssh/id_ed25519.pub or id_rsa.pub) and a cloud firewall that allows only SSH, HTTP and HTTPS. `ship` sends the
committed code (git archive, without the sample FIR images), the service keys found in crimeai/backend/.env
(Meko, Tiger Cloud, Gemini) and the Solana sealing key over SSH, then runs deploy/deploy.sh, which prints the HTTPS
address and the demo login. Standard library only.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND_ENV = ROOT / "crimeai" / "backend" / ".env"
SOLANA_KEY = ROOT / "crimeai" / "backend" / "var" / "solana-devnet.json"
SHIPPED_KEYS = ("MEKO_API_KEY", "MEKO_AGENCY_CODE", "MEKO_DATAPACK_PREFIX", "TIGER_DATABASE_URL", "GEMINI_API_KEY",
                "GEMINI_MODEL", "STORAGE_BACKEND")
NAME = "crimeai"
API = "https://api.digitalocean.com/v2"
REGION, SIZE, IMAGE = "blr1", "s-4vcpu-8gb", "ubuntu-24-04-x64"


def say(msg: str) -> None:
    print(f"==> {msg}", flush=True)


def api(method: str, path: str, body: dict | None = None) -> dict:
    token = os.environ.get("DIGITALOCEAN_TOKEN")
    if not token:
        sys.exit("Set DIGITALOCEAN_TOKEN (an API token from the DigitalOcean control panel) in the environment.")
    req = urllib.request.Request(f"{API}{path}", method=method, data=json.dumps(body).encode() if body else None,
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 - fixed https API endpoint
            raw = resp.read()
    except urllib.error.HTTPError as e:
        sys.exit(f"DigitalOcean API {method} {path}: HTTP {e.code} {e.read().decode(errors='replace')[:400]}")
    return json.loads(raw) if raw else {}


def public_key() -> str:
    for name in ("id_ed25519.pub", "id_rsa.pub"):
        path = Path.home() / ".ssh" / name
        if path.is_file():
            return path.read_text(encoding="utf-8").strip()
    sys.exit("No SSH public key in ~/.ssh: create one with  ssh-keygen -t ed25519")


def ssh_key_id() -> str:
    key = public_key()
    body = " ".join(key.split()[:2])
    for k in api("GET", "/account/keys?per_page=200")["ssh_keys"]:
        if " ".join(k["public_key"].split()[:2]) == body:
            return str(k["id"])
    return str(api("POST", "/account/keys", {"name": f"{NAME}-deploy", "public_key": key})["ssh_key"]["id"])


def create() -> str:
    key = ssh_key_id()
    say(f"Creating a {SIZE} droplet in {REGION}")
    droplet = api("POST", "/droplets", {"name": NAME, "region": REGION, "size": SIZE, "image": IMAGE,
                                        "ssh_keys": [key], "tags": [NAME], "monitoring": True})["droplet"]
    ip = ""
    while not ip:
        time.sleep(5)
        d = api("GET", f"/droplets/{droplet['id']}")["droplet"]
        ip = next((n["ip_address"] for n in d["networks"]["v4"] if n["type"] == "public"), "") if d["status"] == "active" else ""
    api("POST", "/firewalls", {
        "name": f"{NAME}-web", "droplet_ids": [droplet["id"]],
        "inbound_rules": [{"protocol": "tcp", "ports": p, "sources": {"addresses": ["0.0.0.0/0", "::/0"]}}
                          for p in ("22", "80", "443")],
        "outbound_rules": [{"protocol": proto, "ports": "all", "destinations": {"addresses": ["0.0.0.0/0", "::/0"]}}
                           for proto in ("tcp", "udp")] + [{"protocol": "icmp", "destinations": {"addresses": ["0.0.0.0/0", "::/0"]}}],
    })
    say(f"Droplet ready at {ip}; waiting for SSH")
    for _ in range(60):
        if ssh(ip, "true", check=False, quiet=True) == 0:
            return ip
        time.sleep(5)
    sys.exit(f"SSH to root@{ip} did not come up; retry with: python deploy/cloud.py ship {ip}")


def ssh(ip: str, command: str, *, data: bytes | None = None, check: bool = True, quiet: bool = False) -> int:
    args = ["ssh", "-o", "StrictHostKeyChecking=accept-new", "-o", "ConnectTimeout=10", f"root@{ip}", command]
    out = subprocess.run(args, input=data, stdout=subprocess.DEVNULL if quiet else None,  # noqa: S603
                         stderr=subprocess.DEVNULL if quiet else None)
    if check and out.returncode != 0:
        sys.exit(f"ssh root@{ip} '{command[:60]}' failed ({out.returncode})")
    return out.returncode


def shipped_env() -> str:
    lines = []
    if BACKEND_ENV.is_file():
        for line in BACKEND_ENV.read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition("=")
            if key.strip() in SHIPPED_KEYS and value.strip():
                lines.append(f"{key.strip()}={value.strip()}")
    return "\n".join(lines) + "\n"


def ship(ip: str) -> None:
    say(f"Copying the committed code to root@{ip}:/opt/crimeai")
    archive = subprocess.run(["git", "-C", str(ROOT), "archive", "--format=tar", "HEAD", "--", ".",  # noqa: S603, S607
                              ":(exclude)FIR_Organized_5Languages"], capture_output=True, check=True).stdout
    ssh(ip, "mkdir -p /opt/crimeai && tar -x -C /opt/crimeai", data=archive)
    env = shipped_env()
    say(f"Sending service keys: {', '.join(line.split('=')[0] for line in env.split() if '=' in line) or 'none'}")
    ssh(ip, "umask 077 && cat > /opt/crimeai/crimeai/backend/.env.deploy", data=env.encode())
    if SOLANA_KEY.is_file():
        say("Sending the Solana sealing key")
        # The API and worker run as uid 10001 (backend Dockerfile): the key stays private to that user.
        ssh(ip, "umask 077 && mkdir -p /opt/crimeai/crimeai/secrets && cat > /opt/crimeai/crimeai/secrets/solana-devnet.json"
                " && chown -R 10001:10001 /opt/crimeai/crimeai/secrets", data=SOLANA_KEY.read_bytes())
    say("Running deploy/deploy.sh on the droplet (first run: 15-25 minutes)")
    ssh(ip, "cd /opt/crimeai && bash deploy/deploy.sh")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("up")
    sub.add_parser("create")
    sub.add_parser("ship").add_argument("ip")
    args = parser.parse_args()
    if args.command == "ship":
        ship(args.ip)
        return
    ip = create()
    if args.command == "up":
        ship(ip)
    else:
        print(ip)


if __name__ == "__main__":
    main()

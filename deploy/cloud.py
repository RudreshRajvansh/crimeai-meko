#!/usr/bin/env python3
"""
Deploy CrimeAI to DigitalOcean or Vultr: one VM in Bangalore running the production stack (Caddy with HTTPS, API,
workers, YugabyteDB, Redis) through deploy/deploy.sh.

  python deploy/cloud.py up digitalocean      # DIGITALOCEAN_TOKEN in the environment
  python deploy/cloud.py up vultr             # VULTR_API_KEY in the environment
  python deploy/cloud.py create digitalocean  # only create the VM and print its address
  python deploy/cloud.py ship 203.0.113.10    # copy the code and keys to an existing VM and (re)deploy

`up` and `create` create a billable VM: a 4 vCPU / 8 GB plan in the Bangalore region (blr1 / blr), with your SSH
public key (~/.ssh/id_ed25519.pub or id_rsa.pub). On DigitalOcean a cloud firewall allows only SSH, HTTP and
HTTPS. `ship` sends the committed code (git archive, without the sample FIR images), the service keys found in
crimeai/backend/.env (Meko, Tiger Cloud, Gemini, object storage) and the Solana sealing key over SSH, then runs
deploy/deploy.sh, which prints the HTTPS address and the demo login. Standard library only.
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
                "GEMINI_MODEL", "STORAGE_BACKEND", "S3_ENDPOINT", "S3_REGION", "S3_BUCKET", "S3_ACCESS_KEY", "S3_SECRET_KEY")
NAME = "crimeai"

PROVIDERS = {
    "digitalocean": {"api": "https://api.digitalocean.com/v2", "token": "DIGITALOCEAN_TOKEN",
                     "region": "blr1", "size": "s-4vcpu-8gb", "image": "ubuntu-24-04-x64"},
    "vultr": {"api": "https://api.vultr.com/v2", "token": "VULTR_API_KEY",
              "region": "blr", "size": "vc2-4c-8gb", "image": "Ubuntu 24.04 LTS x64"},
}


def say(msg: str) -> None:
    print(f"==> {msg}", flush=True)


def api(provider: str, method: str, path: str, body: dict | None = None) -> dict:
    conf = PROVIDERS[provider]
    token = os.environ.get(conf["token"])
    if not token:
        sys.exit(f"Set {conf['token']} (an API token from the {provider} control panel) in the environment.")
    req = urllib.request.Request(f"{conf['api']}{path}", method=method, data=json.dumps(body).encode() if body else None,
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 - fixed https API endpoints
            raw = resp.read()
    except urllib.error.HTTPError as e:
        sys.exit(f"{provider} API {method} {path}: HTTP {e.code} {e.read().decode(errors='replace')[:400]}")
    return json.loads(raw) if raw else {}


def public_key() -> str:
    for name in ("id_ed25519.pub", "id_rsa.pub"):
        path = Path.home() / ".ssh" / name
        if path.is_file():
            return path.read_text(encoding="utf-8").strip()
    sys.exit("No SSH public key in ~/.ssh: create one with  ssh-keygen -t ed25519")


def ssh_key_id(provider: str) -> str:
    key = public_key()
    body = " ".join(key.split()[:2])
    if provider == "digitalocean":
        for k in api(provider, "GET", "/account/keys?per_page=200")["ssh_keys"]:
            if " ".join(k["public_key"].split()[:2]) == body:
                return str(k["id"])
        return str(api(provider, "POST", "/account/keys", {"name": f"{NAME}-deploy", "public_key": key})["ssh_key"]["id"])
    for k in api(provider, "GET", "/ssh-keys?per_page=500")["ssh_keys"]:
        if " ".join(k["ssh_key"].split()[:2]) == body:
            return k["id"]
    return api(provider, "POST", "/ssh-keys", {"name": f"{NAME}-deploy", "ssh_key": key})["ssh_key"]["id"]


def create(provider: str) -> str:
    conf, key = PROVIDERS[provider], ssh_key_id(provider)
    say(f"Creating a {conf['size']} VM in {conf['region']} on {provider}")
    if provider == "digitalocean":
        droplet = api(provider, "POST", "/droplets", {
            "name": NAME, "region": conf["region"], "size": conf["size"], "image": conf["image"],
            "ssh_keys": [key], "tags": [NAME], "monitoring": True})["droplet"]
        ip = ""
        while not ip:
            time.sleep(5)
            d = api(provider, "GET", f"/droplets/{droplet['id']}")["droplet"]
            ip = next((n["ip_address"] for n in d["networks"]["v4"] if n["type"] == "public"), "") if d["status"] == "active" else ""
        api(provider, "POST", "/firewalls", {
            "name": f"{NAME}-web", "droplet_ids": [droplet["id"]],
            "inbound_rules": [{"protocol": "tcp", "ports": p, "sources": {"addresses": ["0.0.0.0/0", "::/0"]}}
                              for p in ("22", "80", "443")],
            "outbound_rules": [{"protocol": proto, "ports": "all", "destinations": {"addresses": ["0.0.0.0/0", "::/0"]}}
                               for proto in ("tcp", "udp")] + [{"protocol": "icmp", "destinations": {"addresses": ["0.0.0.0/0", "::/0"]}}],
        })
    else:
        os_id = next(o["id"] for o in api(provider, "GET", "/os?per_page=500")["os"] if o["name"] == conf["image"])
        inst = api(provider, "POST", "/instances", {
            "region": conf["region"], "plan": conf["size"], "os_id": os_id, "label": NAME, "hostname": NAME,
            "sshkey_id": [key], "tags": [NAME], "backups": "disabled"})["instance"]
        ip = ""
        while not ip:
            time.sleep(5)
            i = api(provider, "GET", f"/instances/{inst['id']}")["instance"]
            ready = i["status"] == "active" and i["power_status"] == "running" and i["main_ip"] != "0.0.0.0"
            ip = i["main_ip"] if ready else ""
    say(f"VM ready at {ip}; waiting for SSH")
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
        ssh(ip, "umask 077 && mkdir -p /opt/crimeai/crimeai/secrets && cat > /opt/crimeai/crimeai/secrets/solana-devnet.json",
            data=SOLANA_KEY.read_bytes())
    say("Running deploy/deploy.sh on the VM (first run: 15-25 minutes)")
    ssh(ip, "cd /opt/crimeai && bash deploy/deploy.sh")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("up", "create"):
        p = sub.add_parser(name)
        p.add_argument("provider", choices=sorted(PROVIDERS))
    sub.add_parser("ship").add_argument("ip")
    args = parser.parse_args()
    if args.command == "ship":
        ship(args.ip)
        return
    ip = create(args.provider)
    if args.command == "up":
        ship(ip)
    else:
        print(ip)


if __name__ == "__main__":
    main()

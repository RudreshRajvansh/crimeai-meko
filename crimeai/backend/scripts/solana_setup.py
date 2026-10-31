#!/usr/bin/env python3
"""
Set up Solana sealing for this CrimeAI deployment.

  python scripts/solana_setup.py

Creates the deployment's sealing key at SOLANA_KEYPAIR_FILE (var/solana-devnet.json by default, in the Solana CLI's
JSON format) if it does not exist, prints its address, and on devnet asks the faucet for 1 SOL to pay transaction
fees. When the faucet is rate-limited, fund the printed address at https://faucet.solana.com and rerun.
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import settings
from app.core.exceptions import ExternalServiceError
from app.integrations import solana


async def main() -> int:
    from solders.keypair import Keypair

    path = Path(settings.SOLANA_KEYPAIR_FILE)
    if path.is_file():
        print(f"  [ok] sealing key exists: {path}")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(list(bytes(Keypair()))), encoding="utf-8")
        print(f"  [ok] sealing key created: {path} (keep it out of git; var/ is ignored)")
    address = str(solana.keypair().pubkey())
    print(f"  address: {address} on {settings.SOLANA_CLUSTER} ({settings.SOLANA_RPC_URL})")
    try:
        sol = await solana.balance(address)
        print(f"  balance: {sol:.4f} SOL")
        if sol < 0.01 and settings.SOLANA_CLUSTER == "devnet":
            sig = await solana.rpc("requestAirdrop", [address, 1_000_000_000])
            print(f"  [ok] devnet airdrop requested: {sig}")
            for _ in range(15):
                await asyncio.sleep(2)
                if (sol := await solana.balance(address)) > 0:
                    break
            print(f"  balance: {sol:.4f} SOL")
    except ExternalServiceError as exc:
        print(f"  [!!] {exc} {exc.detail or ''}")
        print(f"  Fund {address} at https://faucet.solana.com (devnet), then seal a case from its dossier.")
        return 1
    print("Done. Open a case dossier and press 'Seal on Solana'.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

"""
Solana anchoring for the chain of custody.

A seal is one transaction to the Memo program, signed by this deployment's key: the memo carries the case
reference and the Merkle root of the case file's hashes, so anyone with the transaction signature can check that
a document set existed unchanged at that time. Only hashes go on chain. JSON-RPC over httpx; transactions are
built and signed with solders.
"""
from __future__ import annotations

import asyncio
import base64
import json
import re
from pathlib import Path
from typing import Any

import httpx

from app.core.config import settings
from app.core.exceptions import ExternalServiceError

MEMO_PROGRAM = "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr"
_MEMO_LOG = re.compile(r'Memo \(len \d+\): "(.*)"$')


def keypair():
    from solders.keypair import Keypair

    path = Path(settings.SOLANA_KEYPAIR_FILE)
    if not path.is_file():
        raise ExternalServiceError("Solana is not configured: run scripts/solana_setup.py")
    return Keypair.from_bytes(bytes(json.loads(path.read_text(encoding="utf-8"))))


def explorer_url(signature: str) -> str:
    suffix = "" if settings.SOLANA_CLUSTER == "mainnet-beta" else f"?cluster={settings.SOLANA_CLUSTER}"
    return f"https://explorer.solana.com/tx/{signature}{suffix}"


async def rpc(method: str, params: list[Any], client: httpx.AsyncClient | None = None) -> Any:
    owned = client is None
    client = client or httpx.AsyncClient(timeout=20.0)
    try:
        resp = await client.post(settings.SOLANA_RPC_URL, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
        body = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise ExternalServiceError("Solana RPC could not be reached", detail=type(exc).__name__) from exc
    finally:
        if owned:
            await client.aclose()
    if body.get("error"):
        raise ExternalServiceError("Solana RPC error", detail=str(body["error"].get("message", body["error"]))[:300])
    return body.get("result")


def memo_transaction(memo: str, blockhash: str) -> bytes:
    """A signed transaction with one Memo instruction, signed by this deployment's key."""
    from solders.hash import Hash
    from solders.instruction import AccountMeta, Instruction
    from solders.message import Message
    from solders.pubkey import Pubkey
    from solders.transaction import Transaction

    kp = keypair()
    ix = Instruction(Pubkey.from_string(MEMO_PROGRAM), memo.encode(), [AccountMeta(kp.pubkey(), is_signer=True, is_writable=True)])
    return bytes(Transaction([kp], Message([ix], kp.pubkey()), Hash.from_string(blockhash)))


async def anchor(memo: str, *, client: httpx.AsyncClient | None = None, wait_seconds: float = 20.0) -> dict[str, Any]:
    """Send the memo and wait for confirmation. Returns signature, slot and status ('anchored' or 'submitted')."""
    owned = client is None
    client = client or httpx.AsyncClient(timeout=20.0)
    try:
        latest = await rpc("getLatestBlockhash", [{"commitment": "confirmed"}], client)
        raw = memo_transaction(memo, latest["value"]["blockhash"])
        signature = await rpc("sendTransaction", [base64.b64encode(raw).decode(), {"encoding": "base64",
                                                                                   "preflightCommitment": "confirmed"}], client)
        for _ in range(int(wait_seconds / 2)):
            statuses = await rpc("getSignatureStatuses", [[signature]], client)
            st = (statuses or {}).get("value", [None])[0]
            if st and st.get("err"):
                raise ExternalServiceError("Solana rejected the seal transaction", detail=str(st["err"])[:300])
            if st and st.get("confirmationStatus") in ("confirmed", "finalized"):
                return {"signature": signature, "slot": st.get("slot"), "status": "anchored"}
            await asyncio.sleep(2)
        return {"signature": signature, "slot": None, "status": "submitted"}
    finally:
        if owned:
            await client.aclose()


async def memo_of(signature: str, *, client: httpx.AsyncClient | None = None) -> dict[str, Any] | None:
    """The memo a confirmed transaction carries, with its slot and block time; None if not found yet."""
    tx = await rpc("getTransaction", [signature, {"encoding": "json", "commitment": "confirmed",
                                                  "maxSupportedTransactionVersion": 0}], client)
    if not tx:
        return None
    memo = None
    for line in (tx.get("meta") or {}).get("logMessages") or []:
        if m := _MEMO_LOG.search(line):
            memo = m.group(1).encode().decode("unicode_escape")
    return {"memo": memo, "slot": tx.get("slot"), "block_time": tx.get("blockTime"),
            "failed": bool((tx.get("meta") or {}).get("err"))}


async def balance(address: str, client: httpx.AsyncClient | None = None) -> float:
    lamports = (await rpc("getBalance", [address, {"commitment": "confirmed"}], client) or {}).get("value", 0)
    return lamports / 1_000_000_000

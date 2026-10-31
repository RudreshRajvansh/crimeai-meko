"""Chain of custody: Merkle roots, the memo transaction, and the Solana JSON-RPC exchange."""
import base64
import hashlib
import json

import httpx
import pytest

from app.core.config import settings
from app.integrations import solana
from app.services import custody


@pytest.fixture
def key(tmp_path, monkeypatch):
    from solders.keypair import Keypair

    kp = Keypair()
    path = tmp_path / "solana.json"
    path.write_text(json.dumps(list(bytes(kp))))
    monkeypatch.setattr(settings, "SOLANA_KEYPAIR_FILE", str(path))
    monkeypatch.setattr(settings, "SOLANA_RPC_URL", "https://rpc.test")
    return kp


def test_merkle_root_pairs_hashes_and_repeats_an_odd_one():
    a, b, c = (hashlib.sha256(x).hexdigest() for x in (b"a", b"b", b"c"))
    ab = hashlib.sha256(bytes.fromhex(a) + bytes.fromhex(b)).digest()
    cc = hashlib.sha256(bytes.fromhex(c) * 2).digest()
    assert custody.merkle_root([a]) == a
    assert custody.merkle_root([a, b]) == ab.hex()
    assert custody.merkle_root([a, b, c]) == hashlib.sha256(ab + cc).hexdigest()
    assert custody.merkle_root([a, b]) != custody.merkle_root([b, a]), "order is part of the seal"


def test_a_leaf_hash_changes_with_any_byte_of_the_document():
    doc = {"kind": "document", "id": "1", "title": "Seizure memo", "text": "Recovered DL 5S AB 1243."}
    assert custody.leaf_hash(doc) == custody.leaf_hash(dict(reversed(doc.items()))), "key order does not matter"
    assert custody.leaf_hash(doc) != custody.leaf_hash({**doc, "text": "Recovered DL 5S AB 1234."})


def test_the_memo_transaction_is_signed_by_the_deployment_key(key):
    from solders.transaction import Transaction

    memo = custody.memo_for("DLP:DL-1", "ab" * 32, 3)
    tx = Transaction.from_bytes(solana.memo_transaction(memo, "11111111111111111111111111111111"))
    assert tx.message.account_keys[0] == key.pubkey()
    assert str(tx.message.account_keys[1]) == solana.MEMO_PROGRAM
    assert tx.message.instructions[0].data == memo.encode()
    tx.verify()  # the signature checks out against the message


async def test_anchor_sends_the_transaction_and_waits_for_confirmation(key):
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body["method"])
        result = {
            "getLatestBlockhash": {"value": {"blockhash": "11111111111111111111111111111111", "lastValidBlockHeight": 9}},
            "sendTransaction": "5sig",
            "getSignatureStatuses": {"value": [{"slot": 42, "confirmationStatus": "confirmed", "err": None}]},
        }[body["method"]]
        if body["method"] == "sendTransaction":
            raw = base64.b64decode(body["params"][0])
            assert b"crimeai:seal:v1" in raw, "only the memo with the root is sent"
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": result})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        sent = await solana.anchor(custody.memo_for("DLP:DL-1", "cd" * 32, 2), client=client)
    assert sent == {"signature": "5sig", "slot": 42, "status": "anchored"}
    assert seen == ["getLatestBlockhash", "sendTransaction", "getSignatureStatuses"]


async def test_memo_is_read_back_from_the_transaction_logs(key):
    memo = custody.memo_for("DLP:DL-1", "ef" * 32, 2)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": {
            "slot": 7, "blockTime": 1793480000,
            "meta": {"err": None, "logMessages": [f'Program log: Memo (len {len(memo)}): "{memo}"']}}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        got = await solana.memo_of("5sig", client=client)
    assert got == {"memo": memo, "slot": 7, "block_time": 1793480000, "failed": False}


def test_explorer_link_names_the_cluster(monkeypatch):
    monkeypatch.setattr(settings, "SOLANA_CLUSTER", "devnet")
    assert solana.explorer_url("5sig") == "https://explorer.solana.com/tx/5sig?cluster=devnet"

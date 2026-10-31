"""S3-compatible storage (DigitalOcean Spaces, Vultr Object Storage): request signing and the store's requests."""
import hashlib
from datetime import UTC, datetime

import httpx

from app.services import storage


def test_signature_matches_the_aws_sigv4_example():
    # AWS's published example: GET Object with a Range header (docs, "Signature Calculations for the Authorization
    # Header: Example GET Object").
    headers = storage.sigv4_headers(
        "GET", "examplebucket.s3.amazonaws.com", "/test.txt", "us-east-1", "AKIAIOSFODNN7EXAMPLE",
        "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY", hashlib.sha256(b"").hexdigest(),
        datetime(2013, 5, 24, tzinfo=UTC), {"Range": "bytes=0-9"})
    assert headers["authorization"].endswith(
        "SignedHeaders=host;range;x-amz-content-sha256;x-amz-date, "
        "Signature=f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41")


async def test_put_and_get_go_path_style_to_the_bucket(monkeypatch):
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, str(request.url), request.headers.get("authorization", "")))
        return httpx.Response(200, content=b"pdf-bytes")

    real = httpx.AsyncClient
    monkeypatch.setattr(storage.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    store = storage.S3DocumentStore("https://blr1.digitaloceanspaces.com", "blr1", "crimeai-evidence", "AK", "SK")
    assert await store.put("fir/2026/10/x/a.pdf", b"pdf-bytes", "application/pdf") == "s3://fir/2026/10/x/a.pdf"
    assert await store.get("fir/2026/10/x/a.pdf") == b"pdf-bytes"
    assert [s[:2] for s in seen] == [
        ("PUT", "https://blr1.digitaloceanspaces.com/crimeai-evidence/fir/2026/10/x/a.pdf"),
        ("GET", "https://blr1.digitaloceanspaces.com/crimeai-evidence/fir/2026/10/x/a.pdf"),
    ]
    assert all("Credential=AK/" in s[2] and "/blr1/s3/aws4_request" in s[2] for s in seen)

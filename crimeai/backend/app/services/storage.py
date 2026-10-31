"""
Evidence document storage. Local disk for development; for deployments, Supabase Storage or any S3-compatible
object store (DigitalOcean Spaces, Vultr Object Storage), signed with AWS Signature Version 4.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from urllib.parse import quote, urlsplit

import httpx

from app.core.config import settings
from app.core.exceptions import StorageError


@dataclass(frozen=True, slots=True)
class StoredObject:
    key: str
    url: str
    sha256: str
    size: int


class DocumentStore(Protocol):
    async def put(self, key: str, data: bytes, content_type: str) -> str: ...
    async def get(self, key: str) -> bytes: ...


def safe_filename(name: str | None) -> str:
    stem = Path(name or "document").name
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", stem).strip("._") or "document"
    return cleaned[:120]


def object_key(fir_number: str, filename: str | None) -> str:
    today = datetime.now(UTC)
    return f"fir/{today:%Y/%m}/{safe_filename(fir_number)}/{uuid.uuid4().hex}-{safe_filename(filename)}"


class LocalDocumentStore:
    def __init__(self, root: str) -> None:
        self.root = Path(root).resolve()

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root not in path.parents:
            raise StorageError("Invalid storage key")
        return path

    async def put(self, key: str, data: bytes, content_type: str) -> str:
        path = self._path(key)
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, data)
        return f"local://{key}"

    async def get(self, key: str) -> bytes:
        return await asyncio.to_thread(self._path(key).read_bytes)


class SupabaseDocumentStore:
    def __init__(self, base_url: str, service_key: str, bucket: str) -> None:
        self.base = f"{base_url.rstrip('/')}/storage/v1/object/{bucket}"
        self.headers = {"Authorization": f"Bearer {service_key}", "apikey": service_key}

    async def put(self, key: str, data: bytes, content_type: str) -> str:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{self.base}/{key}", content=data,
                headers={**self.headers, "Content-Type": content_type, "x-upsert": "false"},
            )
        if response.status_code >= 300:
            raise StorageError("Document upload failed", detail={"status": response.status_code})
        return f"supabase://{key}"

    async def get(self, key: str) -> bytes:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(f"{self.base}/{key}", headers=self.headers)
        if response.status_code >= 300:
            raise StorageError("Document download failed", detail={"status": response.status_code})
        return response.content


def sigv4_headers(method: str, host: str, path: str, region: str, access_key: str, secret_key: str,
                  payload_hash: str, now: datetime, extra: dict[str, str] | None = None) -> dict[str, str]:
    """Headers for an AWS Signature Version 4 request to an S3-compatible service (no query string)."""
    amz_date, day = now.strftime("%Y%m%dT%H%M%SZ"), now.strftime("%Y%m%d")
    headers = {"host": host, "x-amz-content-sha256": payload_hash, "x-amz-date": amz_date,
               **{k.lower(): v for k, v in (extra or {}).items()}}
    signed = ";".join(sorted(headers))
    canonical = "\n".join([method, quote(path, safe="/-_.~"), "", *(f"{k}:{headers[k].strip()}" for k in sorted(headers)),
                           "", signed, payload_hash])
    scope = f"{day}/{region}/s3/aws4_request"
    to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canonical.encode()).hexdigest()])
    key = f"AWS4{secret_key}".encode()
    for part in (day, region, "s3", "aws4_request"):
        key = hmac.new(key, part.encode(), hashlib.sha256).digest()
    signature = hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()
    headers["authorization"] = (f"AWS4-HMAC-SHA256 Credential={access_key}/{scope}, SignedHeaders={signed}, "
                                f"Signature={signature}")
    return headers


class S3DocumentStore:
    """DigitalOcean Spaces, Vultr Object Storage or any S3-compatible bucket, addressed path-style."""

    def __init__(self, endpoint: str, region: str, bucket: str, access_key: str, secret_key: str) -> None:
        parts = urlsplit(endpoint if "://" in endpoint else f"https://{endpoint}")
        self.scheme, self.host = parts.scheme, parts.netloc
        self.region, self.bucket, self.access_key, self.secret_key = region, bucket, access_key, secret_key

    async def _request(self, method: str, key: str, data: bytes = b"", content_type: str | None = None) -> httpx.Response:
        path = f"/{self.bucket}/{key}"
        extra = {"content-type": content_type} if content_type else {}
        headers = sigv4_headers(method, self.host, path, self.region, self.access_key, self.secret_key,
                                hashlib.sha256(data).hexdigest(), datetime.now(UTC), extra)
        headers.pop("host")
        async with httpx.AsyncClient(timeout=30) as client:
            return await client.request(method, f"{self.scheme}://{self.host}{quote(path, safe='/-_.~')}",
                                        content=data or None, headers=headers)

    async def put(self, key: str, data: bytes, content_type: str) -> str:
        response = await self._request("PUT", key, data, content_type)
        if response.status_code >= 300:
            raise StorageError("Document upload failed", detail={"status": response.status_code})
        return f"s3://{key}"

    async def get(self, key: str) -> bytes:
        response = await self._request("GET", key)
        if response.status_code >= 300:
            raise StorageError("Document download failed", detail={"status": response.status_code})
        return response.content


def get_document_store() -> DocumentStore:
    if settings.STORAGE_BACKEND == "s3":
        return S3DocumentStore(settings.S3_ENDPOINT, settings.S3_REGION, settings.S3_BUCKET, settings.S3_ACCESS_KEY,
                               settings.S3_SECRET_KEY)
    if settings.STORAGE_BACKEND == "supabase":
        return SupabaseDocumentStore(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY, settings.SUPABASE_STORAGE_BUCKET)
    return LocalDocumentStore(settings.LOCAL_STORAGE_DIR)


async def store_document(fir_number: str, filename: str | None, data: bytes, content_type: str) -> StoredObject:
    key = object_key(fir_number, filename)
    url = await get_document_store().put(key, data, content_type)
    return StoredObject(key=key, url=url, sha256=hashlib.sha256(data).hexdigest(), size=len(data))


async def store_object(prefix: str, filename: str | None, data: bytes, content_type: str) -> StoredObject:
    """Store a non-FIR file (e.g. a profile-change proof) under its own prefix."""
    today = datetime.now(UTC)
    key = f"{prefix}/{today:%Y/%m}/{uuid.uuid4().hex}-{safe_filename(filename)}"
    url = await get_document_store().put(key, data, content_type)
    return StoredObject(key=key, url=url, sha256=hashlib.sha256(data).hexdigest(), size=len(data))


async def load_document(url: str) -> bytes:
    _, _, key = url.partition("://")
    return await get_document_store().get(key)

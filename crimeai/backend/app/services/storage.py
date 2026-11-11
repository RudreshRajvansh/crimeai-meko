"""Evidence document storage. Local disk for development, Supabase Storage (S3-compatible) for deployments."""
from __future__ import annotations

import asyncio
import hashlib
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

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


def get_document_store() -> DocumentStore:
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

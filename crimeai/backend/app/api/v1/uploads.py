"""Upload helpers shared by endpoints that accept files."""
from fastapi import HTTPException, UploadFile, status

_READ_CHUNK = 1024 * 1024


async def read_capped(upload: UploadFile, limit: int) -> bytes:
    """Stream the upload and stop as soon as it exceeds the limit, instead of buffering an unbounded body."""
    chunks, size = [], 0
    while chunk := await upload.read(_READ_CHUNK):
        size += len(chunk)
        if size > limit:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"File exceeds {limit // (1024 * 1024)} MB")
        chunks.append(chunk)
    return b"".join(chunks)

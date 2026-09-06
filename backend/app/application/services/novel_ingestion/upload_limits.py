from __future__ import annotations


MAX_UPLOAD_BYTES = 16 * 1024 * 1024


class UploadTooLarge(ValueError):
    code = "upload_too_large"


async def _read_upload_bytes(upload, *, limit: int = MAX_UPLOAD_BYTES, chunk_size: int = 1024 * 1024) -> bytes:
    parts: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(chunk_size)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise UploadTooLarge(f"uploaded file exceeds {limit} bytes")
        parts.append(chunk)
    return b"".join(parts)

"""Bounded streaming helpers for untrusted HTTP uploads."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class AsyncReadableUpload(Protocol):
    async def read(self, size: int = -1) -> bytes: ...


async def stream_upload_to_path(
    upload: AsyncReadableUpload,
    destination: Path,
    *,
    max_bytes: int,
    min_bytes: int = 0,
    chunk_bytes: int = 1024 * 1024,
) -> int:
    """Stream an upload to disk while enforcing byte limits incrementally."""
    if max_bytes < 1:
        raise ValueError("max_bytes must be positive")
    if min_bytes < 0 or min_bytes > max_bytes:
        raise ValueError("invalid min_bytes")
    if chunk_bytes < 1:
        raise ValueError("chunk_bytes must be positive")

    destination.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    try:
        with destination.open("wb") as fh:
            while True:
                chunk = await upload.read(min(chunk_bytes, max_bytes - total + 1))
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise ValueError("Upload exceeds configured size limit")
                fh.write(chunk)
        if total < min_bytes:
            raise ValueError("Upload is empty or too small")
        return total
    except Exception:
        destination.unlink(missing_ok=True)
        raise

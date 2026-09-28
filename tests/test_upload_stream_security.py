"""Bounded upload streaming security tests."""

from __future__ import annotations

import asyncio

import pytest

from web.backend.services.upload_stream import stream_upload_to_path


class FakeUpload:
    def __init__(self, payload: bytes):
        self.payload = payload
        self.offset = 0
        self.read_calls = 0

    async def read(self, size: int = -1) -> bytes:
        self.read_calls += 1
        if self.offset >= len(self.payload):
            return b""
        if size < 0:
            size = len(self.payload) - self.offset
        out = self.payload[self.offset : self.offset + size]
        self.offset += len(out)
        return out


def test_stream_upload_writes_incrementally(tmp_path):
    upload = FakeUpload(b"A" * 4096)
    dest = tmp_path / "upload.bin"
    total = asyncio.run(
        stream_upload_to_path(upload, dest, max_bytes=8192, min_bytes=1, chunk_bytes=1024)
    )
    assert total == 4096
    assert dest.read_bytes() == b"A" * 4096
    assert upload.read_calls > 1


def test_stream_upload_rejects_oversize_and_deletes_partial(tmp_path):
    upload = FakeUpload(b"B" * 8192)
    dest = tmp_path / "too-large.bin"
    with pytest.raises(ValueError, match="size limit"):
        asyncio.run(
            stream_upload_to_path(upload, dest, max_bytes=2048, min_bytes=1, chunk_bytes=1024)
        )
    assert not dest.exists()
    assert upload.offset <= 2049


def test_stream_upload_rejects_too_small_and_deletes_partial(tmp_path):
    upload = FakeUpload(b"x")
    dest = tmp_path / "tiny.bin"
    with pytest.raises(ValueError, match="too small"):
        asyncio.run(stream_upload_to_path(upload, dest, max_bytes=100, min_bytes=32))
    assert not dest.exists()

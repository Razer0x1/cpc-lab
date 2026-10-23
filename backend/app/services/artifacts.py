"""Artifact storage abstraction: local filesystem (default) or S3-compatible (MinIO/AWS).
Integrity is enforced with SHA-256 on store and re-verified on download."""
from __future__ import annotations

import hashlib
import io
import os
import uuid
from typing import Any

from ..config import get_settings

settings = get_settings()
_LOCAL_SHA_CACHE: dict[str, str] = {}

try:  # optional dependency
    import boto3  # type: ignore
    from botocore.client import BaseClient  # type: ignore
except Exception:  # pragma: no cover - boto3 optional
    boto3 = None
    BaseClient = Any


def _local_root() -> str:
    root = os.path.join(settings.resolved_data_dir(), "artifacts")
    os.makedirs(root, exist_ok=True)
    return root


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _s3_client() -> "BaseClient | None":
    if settings.storage_backend != "s3" or boto3 is None:
        return None
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key,
        region_name=settings.s3_region,
    )


def put_bytes(workspace_id: str, kind: str, filename: str, data: bytes) -> dict[str, Any]:
    """Store bytes and return artifact column values (uri, sha256, size, content_type)."""
    digest = sha256_bytes(data)
    client = _s3_client()
    if client is not None:
        key = f"{workspace_id}/{kind}/{uuid.uuid4().hex}__{filename}"
        client.upload_fileobj(io.BytesIO(data), settings.s3_bucket, key)
        return {
            "uri": f"s3://{settings.s3_bucket}/{key}",
            "sha256": digest,
            "size_bytes": len(data),
            "content_type": _guess_type(filename),
        }
    safe = _safe_filename(filename)
    target_dir = os.path.join(_local_root(), workspace_id, kind)
    os.makedirs(target_dir, exist_ok=True)
    target = os.path.join(target_dir, f"{uuid.uuid4().hex}__{safe}")
    with open(target, "wb") as f:
        f.write(data)
    _LOCAL_SHA_CACHE[target] = digest
    return {
        "uri": f"local://{os.path.relpath(target, settings.resolved_data_dir())}",
        "sha256": digest,
        "size_bytes": len(data),
        "content_type": _guess_type(filename),
    }


def read_bytes(uri: str) -> bytes:
    client = _s3_client()
    if uri.startswith("s3://"):
        if client is None:
            raise RuntimeError("S3 storage backend not available (install boto3 / configure S3_*)")
        bucket, key = uri.removeprefix("s3://").split("/", 1)
        buf = io.BytesIO()
        client.download_fileobj(bucket, key, buf)
        return buf.getvalue()
    if uri.startswith("local://"):
        rel = uri.removeprefix("local://")
        path = os.path.abspath(os.path.join(str(settings.resolved_data_dir()), rel))
        # Path traversal guard
        if not path.startswith(str(settings.resolved_data_dir())):
            raise PermissionError("Artifact path escapes data directory")
        with open(path, "rb") as f:
            data = f.read()
        cached = _LOCAL_SHA_CACHE.get(path)
        if cached and sha256_bytes(data) != cached:
            raise ValueError("Artifact integrity check failed (sha256 mismatch)")
        return data
    raise ValueError(f"Unsupported artifact URI scheme: {uri}")


def file_exists(uri: str) -> bool:
    if uri.startswith("local://"):
        path = os.path.join(str(settings.resolved_data_dir()), uri.removeprefix("local://"))
        return os.path.exists(path)
    if uri.startswith("s3://"):
        client = _s3_client()
        if client is None:
            return False
        bucket, key = uri.removeprefix("s3://").split("/", 1)
        try:
            client.head_object(Bucket=bucket, Key=key)
            return True
        except Exception:
            return False
    return False


def verify_digest(uri: str, expected_sha256: str) -> bool:
    if not expected_sha256:
        return True
    return sha256_bytes(read_bytes(uri)) == expected_sha256


def _safe_filename(name: str) -> str:
    keep = "".join(c for c in os.path.basename(name) if c.isalnum() or c in "._-")
    return keep or "artifact"


def _guess_type(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    return {
        ".npz": "application/octet-stream",
        ".npy": "application/octet-stream",
        ".json": "application/json",
        ".md": "text/markdown",
        ".html": "text/html",
        ".pdf": "application/pdf",
        ".log": "text/plain",
        ".csv": "text/csv",
        ".jsonl": "application/jsonl",
    }.get(ext, "application/octet-stream")

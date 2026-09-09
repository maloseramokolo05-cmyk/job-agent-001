from __future__ import annotations

import hashlib
import io
import os
from pathlib import Path

from backend.config import ROOT


class StorageError(RuntimeError):
    pass


class ObjectStorage:
    """Private object store. Local storage is deliberately restricted to development/tests."""

    def __init__(self) -> None:
        self.provider = os.getenv("STORAGE_PROVIDER", "local").lower()
        if os.getenv("APP_ENV") == "production" and self.provider != "s3":
            raise StorageError("Production requires STORAGE_PROVIDER=s3")

    def put(self, key: str, content: bytes, content_type: str) -> dict:
        clean = "/".join(p for p in key.split("/") if p not in {"", ".", ".."})
        digest = hashlib.sha256(content).hexdigest()
        if self.provider == "s3":
            import boto3

            bucket = os.environ["S3_BUCKET"]
            boto3.client("s3", endpoint_url=os.getenv("S3_ENDPOINT_URL") or None).put_object(
                Bucket=bucket, Key=clean, Body=content, ContentType=content_type,
                ServerSideEncryption=os.getenv("S3_SERVER_SIDE_ENCRYPTION", "AES256"),
            )
        else:
            path = ROOT / "data" / "private" / clean
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        return {"storage_key": clean, "sha256": digest, "size": len(content), "content_type": content_type}

    def get(self, key: str) -> tuple[io.BytesIO, str]:
        if self.provider == "s3":
            import boto3

            response = boto3.client("s3", endpoint_url=os.getenv("S3_ENDPOINT_URL") or None).get_object(
                Bucket=os.environ["S3_BUCKET"], Key=key
            )
            return io.BytesIO(response["Body"].read()), response.get("ContentType", "application/octet-stream")
        path = (ROOT / "data" / "private" / key).resolve()
        root = (ROOT / "data" / "private").resolve()
        if root not in path.parents:
            raise StorageError("Invalid object key")
        return io.BytesIO(path.read_bytes()), "application/octet-stream"

    def healthy(self) -> bool:
        if self.provider == "local":
            return os.getenv("APP_ENV") != "production"
        try:
            import boto3
            boto3.client("s3", endpoint_url=os.getenv("S3_ENDPOINT_URL") or None).head_bucket(Bucket=os.environ["S3_BUCKET"])
            return True
        except Exception:
            return False

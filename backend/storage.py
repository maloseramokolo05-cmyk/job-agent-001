from __future__ import annotations

import hashlib
import io
import os
from pathlib import Path

from backend.config import ROOT


class StorageError(RuntimeError):
    pass


class ObjectStorage:
    """Private object storage.

    Local files are for development/tests. Production can use the configured Neon/Postgres
    database (default when DATABASE_URL exists) or an S3-compatible private bucket.
    """

    def __init__(self) -> None:
        default = "database" if os.getenv("DATABASE_URL") else "local"
        self.provider = os.getenv("STORAGE_PROVIDER", default).lower()
        if os.getenv("APP_ENV") == "production" and self.provider not in {"database", "s3"}:
            raise StorageError("Production requires durable STORAGE_PROVIDER=database or s3")
        if self.provider == "database" and not os.getenv("DATABASE_URL"):
            raise StorageError("STORAGE_PROVIDER=database requires DATABASE_URL")

    @staticmethod
    def _clean(key: str) -> str:
        parts = [part for part in key.split("/") if part not in {"", ".", ".."}]
        if not parts:
            raise StorageError("Invalid object key")
        return "/".join(parts)

    @staticmethod
    def _content_type_for_key(key: str) -> str:
        suffix = Path(key).suffix.lower()
        return {
            ".pdf": "application/pdf",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".json": "application/json",
            ".txt": "text/plain",
        }.get(suffix, "application/octet-stream")

    def put(self, key: str, content: bytes, content_type: str) -> dict:
        clean = self._clean(key)
        digest = hashlib.sha256(content).hexdigest()
        if self.provider == "database":
            from backend.database import put_blob

            put_blob(clean, content_type, digest, content)
        elif self.provider == "s3":
            import boto3

            bucket = os.environ["S3_BUCKET"]
            boto3.client("s3", endpoint_url=os.getenv("S3_ENDPOINT_URL") or None).put_object(
                Bucket=bucket,
                Key=clean,
                Body=content,
                ContentType=content_type,
                ServerSideEncryption=os.getenv("S3_SERVER_SIDE_ENCRYPTION", "AES256"),
            )
        else:
            path = ROOT / "data" / "private" / clean
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        return {
            "storage_key": clean,
            "sha256": digest,
            "size": len(content),
            "content_type": content_type,
        }

    def get(self, key: str) -> tuple[io.BytesIO, str]:
        clean = self._clean(key)
        if self.provider == "database":
            from backend.database import get_blob

            item = get_blob(clean)
            if not item:
                raise StorageError("Object not found")
            return io.BytesIO(item["content"]), item["content_type"]
        if self.provider == "s3":
            import boto3

            response = boto3.client("s3", endpoint_url=os.getenv("S3_ENDPOINT_URL") or None).get_object(
                Bucket=os.environ["S3_BUCKET"], Key=clean
            )
            return io.BytesIO(response["Body"].read()), response.get("ContentType", "application/octet-stream")
        path = (ROOT / "data" / "private" / clean).resolve()
        root = (ROOT / "data" / "private").resolve()
        if root not in path.parents:
            raise StorageError("Invalid object key")
        return io.BytesIO(path.read_bytes()), self._content_type_for_key(clean)

    def healthy(self) -> bool:
        if self.provider == "database":
            try:
                from backend.database import row

                return bool(row("SELECT 1 AS ok"))
            except Exception:
                return False
        if self.provider == "local":
            return os.getenv("APP_ENV") != "production"
        try:
            import boto3

            boto3.client("s3", endpoint_url=os.getenv("S3_ENDPOINT_URL") or None).head_bucket(
                Bucket=os.environ["S3_BUCKET"]
            )
            return True
        except Exception:
            return False

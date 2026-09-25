"""Upload an already restored and verified PostgreSQL archive to a private S3 bucket."""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

import boto3
from botocore.config import Config


def upload(path: Path) -> str:
    root = Path("/backups").resolve()
    path = path.resolve()
    if not path.is_file() or root not in path.parents or not path.name.endswith(".dump"):
        raise ValueError("Expected a .dump file inside /backups")
    bucket = os.environ["BACKUP_S3_BUCKET"]
    client = boto3.client(
        "s3", endpoint_url=os.environ.get("BACKUP_S3_ENDPOINT", "https://storage.yandexcloud.net"),
        region_name="ru-central1", aws_access_key_id=os.environ["BACKUP_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["BACKUP_SECRET_ACCESS_KEY"],
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )
    hasher = hashlib.sha256()
    with path.open("rb") as archive:
        for chunk in iter(lambda: archive.read(1024 * 1024), b""):
            hasher.update(chunk)
    digest = hasher.hexdigest()
    key = f"postgres/{path.name}"
    client.upload_file(str(path), bucket, key, ExtraArgs={"Metadata": {"sha256": digest}})
    head = client.head_object(Bucket=bucket, Key=key)
    if head["ContentLength"] != path.stat().st_size or head["Metadata"].get("sha256") != digest:
        raise RuntimeError("Uploaded backup verification failed")
    return key


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python -m server.backup_upload /backups/file.dump")
    print(f"Uploaded backup: {upload(Path(sys.argv[1]))}")

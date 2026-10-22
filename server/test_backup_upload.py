"""Unit checks for the off-VPS PostgreSQL backup uploader."""

from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from server import backup_upload


def test_upload_rejects_paths_outside_backups(tmp_path, monkeypatch):
    monkeypatch.setattr(backup_upload, "BACKUPS_ROOT", tmp_path / "backups")
    (tmp_path / "backups").mkdir()
    outside = tmp_path / "elsewhere.dump"
    outside.write_bytes(b"x")
    with pytest.raises(ValueError, match="/backups"):
        backup_upload.upload(outside)


def test_upload_puts_object_and_verifies_size_and_sha(tmp_path, monkeypatch):
    backups = tmp_path / "backups"
    backups.mkdir()
    monkeypatch.setattr(backup_upload, "BACKUPS_ROOT", backups)
    archive = backups / "aiparser-20261022T120000Z-1.dump"
    payload = b"verified-pg-dump"
    archive.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()

    client = MagicMock()
    client.head_object.return_value = {"ContentLength": len(payload), "Metadata": {"sha256": digest}}
    monkeypatch.setenv("BACKUP_S3_BUCKET", "airate-db-backups")
    monkeypatch.setenv("BACKUP_ACCESS_KEY_ID", "key")
    monkeypatch.setenv("BACKUP_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setenv("BACKUP_S3_ENDPOINT", "https://storage.example.test")
    monkeypatch.setattr(backup_upload.boto3, "client", MagicMock(return_value=client))

    key = backup_upload.upload(archive)

    assert key == f"postgres/{archive.name}"
    client.upload_file.assert_called_once()
    args, kwargs = client.upload_file.call_args
    assert Path(args[0]) == archive.resolve()
    assert args[1:] == ("airate-db-backups", key)
    assert kwargs["ExtraArgs"]["Metadata"]["sha256"] == digest
    client.head_object.assert_called_once_with(Bucket="airate-db-backups", Key=key)


def test_upload_fails_when_remote_size_mismatches(tmp_path, monkeypatch):
    backups = tmp_path / "backups"
    backups.mkdir()
    monkeypatch.setattr(backup_upload, "BACKUPS_ROOT", backups)
    archive = backups / "aiparser-bad.dump"
    archive.write_bytes(b"abc")
    client = MagicMock()
    client.head_object.return_value = {"ContentLength": 1, "Metadata": {"sha256": "nope"}}
    monkeypatch.setenv("BACKUP_S3_BUCKET", "bucket")
    monkeypatch.setenv("BACKUP_ACCESS_KEY_ID", "key")
    monkeypatch.setenv("BACKUP_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setattr(backup_upload.boto3, "client", MagicMock(return_value=client))
    with pytest.raises(RuntimeError, match="verification failed"):
        backup_upload.upload(archive)

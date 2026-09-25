"""Private S3 storage for screenshots. Credentials exist only on the server."""

from __future__ import annotations

import os


class StorageError(RuntimeError):
    pass


class ScreenshotStorage:
    def __init__(self, bucket: str, access_key: str, secret_key: str,
                 endpoint: str = "https://storage.yandexcloud.net"):
        import boto3
        from botocore.config import Config

        self.bucket = bucket
        self.client = boto3.client(
            "s3", endpoint_url=endpoint, region_name="ru-central1",
            aws_access_key_id=access_key, aws_secret_access_key=secret_key,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

    @classmethod
    def from_env(cls) -> "ScreenshotStorage | None":
        bucket = os.environ.get("S3_SCREENSHOTS_BUCKET", "")
        access_key = os.environ.get("S3_ACCESS_KEY_ID", "")
        secret_key = os.environ.get("S3_SECRET_ACCESS_KEY", "")
        if not any((bucket, access_key, secret_key)):
            return None
        if not all((bucket, access_key, secret_key)):
            raise RuntimeError("Для S3 нужны бакет, access key и secret key")
        return cls(bucket, access_key, secret_key,
                   os.environ.get("S3_ENDPOINT", "https://storage.yandexcloud.net"))

    def put(self, key: str, data: bytes) -> None:
        try:
            self.client.put_object(Bucket=self.bucket, Key=key, Body=data,
                                   ContentType="image/webp")
        except Exception as exc:
            raise StorageError("Не удалось сохранить скриншот в Object Storage") from exc

    def download_url(self, key: str) -> str:
        try:
            return self.client.generate_presigned_url(
                "get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=300,
            )
        except Exception as exc:
            raise StorageError("Не удалось создать ссылку на скриншот") from exc

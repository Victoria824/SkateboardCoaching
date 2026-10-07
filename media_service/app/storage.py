import re
import mimetypes
from pathlib import Path
from typing import BinaryIO

from .config import settings


SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def safe_filename(filename: str) -> str:
    cleaned = SAFE_NAME.sub("-", Path(filename).name).strip(".-")
    return cleaned[:200] or "video"


class LocalStorage:
    def __init__(self, root: Path = settings.media_root):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def video_path(self, video_id: str, filename: str) -> Path:
        return self.root / "videos" / video_id / safe_filename(filename)

    def frame_directory(self, video_id: str) -> Path:
        return self.root / "frames" / video_id

    def sanitized_video_path(self, export_id: str) -> Path:
        return self.root / "sanitized" / export_id / "sanitized.mp4"

    def sanitized_manifest_path(self, export_id: str) -> Path:
        return self.root / "sanitized" / export_id / "manifest.json"

    def relative_path(self, path: Path) -> str:
        return path.resolve().relative_to(self.root).as_posix()

    def absolute_path(self, relative_path: str) -> Path:
        path = (self.root / relative_path).resolve()
        path.relative_to(self.root)
        return path

    def write_stream(self, destination: Path, source: BinaryIO, max_bytes: int) -> int:
        destination.parent.mkdir(parents=True, exist_ok=True)
        written = 0
        try:
            with destination.open("wb") as output:
                while True:
                    chunk = source.read(1024 * 1024)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > max_bytes:
                        raise UploadTooLarge(max_bytes)
                    output.write(chunk)
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        return written

    def persist(self, path: Path, content_type: str = None) -> str:
        return self.relative_path(path)

    def public_url(self, relative_path: str) -> str:
        return "{}/{}".format(settings.public_media_url, relative_path)


class S3ObjectStore:
    def __init__(self, client=None, presign_client=None):
        if client is None:
            try:
                import boto3
                from botocore.config import Config
            except ImportError as error:
                raise RuntimeError("Install boto3 to use MEDIA_STORAGE_BACKEND=s3") from error
            client_config = Config(signature_version="s3v4", s3={"addressing_style": "path"})
            client = boto3.client(
                "s3",
                endpoint_url=settings.s3_endpoint_url or None,
                aws_access_key_id=settings.s3_access_key or None,
                aws_secret_access_key=settings.s3_secret_key or None,
                region_name=settings.s3_region,
                config=client_config,
            )
            presign_client = boto3.client(
                "s3",
                endpoint_url=(
                    settings.s3_public_endpoint_url or settings.s3_endpoint_url or None
                ),
                aws_access_key_id=settings.s3_access_key or None,
                aws_secret_access_key=settings.s3_secret_key or None,
                region_name=settings.s3_region,
                config=client_config,
            )
        self.client = client
        self.presign_client = presign_client or client
        self.bucket = settings.s3_bucket

    def presign_put(
        self, key: str, content_type: str, sha256: str, expires_in: int = None
    ) -> str:
        return self.presign_client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": self.bucket,
                "Key": key,
                "ContentType": content_type,
                "Metadata": {"sha256": sha256},
            },
            ExpiresIn=expires_in or settings.s3_presign_ttl_seconds,
        )

    def presign_get(self, key: str, expires_in: int = None) -> str:
        return self.presign_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires_in or settings.s3_presign_get_ttl_seconds,
        )

    def head(self, key: str):
        return self.client.head_object(Bucket=self.bucket, Key=key)

    def upload(self, path: Path, key: str, content_type: str = None) -> None:
        extra = {"ContentType": content_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream"}
        self.client.upload_file(str(path), self.bucket, key, ExtraArgs=extra)

    def download(self, key: str, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.client.download_file(self.bucket, key, str(path))


class S3BackedStorage(LocalStorage):
    """Use local paths as worker staging while S3 remains the shared source of truth."""

    def __init__(self, root: Path = settings.media_root, object_store=None):
        super().__init__(root)
        self.object_store = object_store or S3ObjectStore()

    def absolute_path(self, relative_path: str) -> Path:
        path = super().absolute_path(relative_path)
        if not path.exists():
            self.object_store.download(relative_path, path)
        return path

    def persist(self, path: Path, content_type: str = None) -> str:
        key = self.relative_path(path)
        self.object_store.upload(path, key, content_type)
        return key

    def public_url(self, relative_path: str) -> str:
        return self.object_store.presign_get(relative_path)


def create_storage():
    if settings.storage_backend == "s3":
        return S3BackedStorage()
    if settings.storage_backend != "local":
        raise RuntimeError("MEDIA_STORAGE_BACKEND must be local or s3")
    return LocalStorage()


class UploadTooLarge(Exception):
    def __init__(self, max_bytes: int):
        self.max_bytes = max_bytes
        super().__init__("Upload exceeds {} bytes".format(max_bytes))

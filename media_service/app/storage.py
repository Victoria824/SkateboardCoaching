import re
from pathlib import Path
from typing import BinaryIO

from .config import settings


SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def safe_filename(filename: str) -> str:
    cleaned = SAFE_NAME.sub("-", Path(filename).name).strip(".-")
    return cleaned[:200] or "video"


class LocalStorage:
    def __init__(self, root: Path = settings.media_root):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def video_path(self, video_id: str, filename: str) -> Path:
        return self.root / "videos" / video_id / safe_filename(filename)

    def frame_directory(self, video_id: str) -> Path:
        return self.root / "frames" / video_id

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


class UploadTooLarge(Exception):
    def __init__(self, max_bytes: int):
        self.max_bytes = max_bytes
        super().__init__("Upload exceeds {} bytes".format(max_bytes))


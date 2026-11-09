import os
import tempfile
import time
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Optional

from .config import RESUME_TTL_MINUTES, UPLOAD_DIR
from .extraction import safe_filename


@dataclass
class StoredResume:
    resume_id: str
    path: Path
    original_name: str
    media_type: str
    created: float


class ResumeStore:
    def __init__(self) -> None:
        self._items: dict[str, StoredResume] = {}
        self._lock = Lock()
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    def save(self, data: bytes, ext: str, original_name: str, media_type: str) -> StoredResume:
        resume_id = uuid.uuid4().hex
        path = UPLOAD_DIR / f"{resume_id}{ext}"
        path.write_bytes(data)
        item = StoredResume(resume_id, path, original_name, media_type, time.time())
        with self._lock:
            self._items[resume_id] = item
        return item

    def get(self, resume_id: str) -> Optional[StoredResume]:
        with self._lock:
            item = self._items.get(resume_id)
        if item is None or not item.path.exists():
            return None
        return item

    def discard(self, resume_id: str) -> None:
        with self._lock:
            item = self._items.pop(resume_id, None)
        if item:
            item.path.unlink(missing_ok=True)

    def purge_expired(self) -> int:
        cutoff = time.time() - RESUME_TTL_MINUTES * 60
        with self._lock:
            expired = [i for i in self._items.values() if i.created < cutoff]
            for item in expired:
                self._items.pop(item.resume_id, None)
        for item in expired:
            item.path.unlink(missing_ok=True)
        return len(expired)


    def build_zip(self, items: list[StoredResume]) -> Path:
        fd, name = tempfile.mkstemp(suffix=".zip", dir=UPLOAD_DIR)
        os.close(fd)
        try:
            with zipfile.ZipFile(name, "w", zipfile.ZIP_DEFLATED) as archive:
                for position, item in enumerate(items, start=1):
                    archive.write(item.path, f"{position:02d}_{safe_filename(item.original_name)}")
        except Exception:
            Path(name).unlink(missing_ok=True)
            raise
        return Path(name)


store = ResumeStore()

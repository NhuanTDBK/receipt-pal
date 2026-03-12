import os

from rocksdict import Rdict

from app.config import settings


class PhotoStore:
    """RocksDB-backed store for receipt photo bytes, keyed by Telegram file_id."""

    _instance: "PhotoStore | None" = None

    def __init__(self) -> None:
        os.makedirs(settings.rocksdb_path, exist_ok=True)
        self._db = Rdict(settings.rocksdb_path)

    @classmethod
    def get_instance(cls) -> "PhotoStore":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def store(self, file_id: str, image_bytes: bytes) -> None:
        key = f"photo:{file_id}"
        self._db[key] = image_bytes

    def get(self, file_id: str) -> bytes | None:
        key = f"photo:{file_id}"
        try:
            return self._db[key]
        except KeyError:
            return None

    def close(self) -> None:
        self._db.close()
        PhotoStore._instance = None

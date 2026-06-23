from pathlib import Path
from typing import Any, Dict, Union

from chainlit.data.sql_alchemy import SQLAlchemyDataLayer
from chainlit.data.storage_clients.base import BaseStorageClient

DB_PATH = Path(__file__).parent / "chat_history.db"
DB_URL = f"sqlite+aiosqlite:///{DB_PATH}"

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    "id"         TEXT PRIMARY KEY,
    "identifier" TEXT NOT NULL UNIQUE,
    "createdAt"  TEXT,
    "metadata"   TEXT
);
CREATE TABLE IF NOT EXISTS threads (
    "id"             TEXT PRIMARY KEY,
    "createdAt"      TEXT,
    "name"           TEXT,
    "userId"         TEXT,
    "userIdentifier" TEXT,
    "tags"           TEXT,
    "metadata"       TEXT
);
CREATE TABLE IF NOT EXISTS steps (
    "id"            TEXT PRIMARY KEY,
    "name"          TEXT,
    "type"          TEXT,
    "threadId"      TEXT,
    "parentId"      TEXT,
    "streaming"     INTEGER,
    "waitForAnswer" INTEGER,
    "isError"       INTEGER,
    "metadata"      TEXT,
    "tags"          TEXT,
    "input"         TEXT,
    "output"        TEXT,
    "createdAt"     TEXT,
    "start"         TEXT,
    "end"           TEXT,
    "generation"    TEXT,
    "showInput"     TEXT,
    "language"      TEXT,
    "defaultOpen"   INTEGER,
    "autoCollapse"  INTEGER
);
CREATE TABLE IF NOT EXISTS feedbacks (
    "id"      TEXT PRIMARY KEY,
    "forId"   TEXT,
    "value"   INTEGER,
    "comment" TEXT
);
CREATE TABLE IF NOT EXISTS elements (
    "id"           TEXT PRIMARY KEY,
    "threadId"     TEXT,
    "type"         TEXT,
    "chainlitKey"  TEXT,
    "url"          TEXT,
    "objectKey"    TEXT,
    "name"         TEXT,
    "display"      TEXT,
    "size"         TEXT,
    "language"     TEXT,
    "page"         INTEGER,
    "forId"        TEXT,
    "mime"         TEXT,
    "props"        TEXT
);
"""


_MIGRATIONS = [
    'ALTER TABLE steps ADD COLUMN "defaultOpen" INTEGER',
    'ALTER TABLE steps ADD COLUMN "autoCollapse" INTEGER',
]


def init_database() -> None:
    import sqlite3
    conn = sqlite3.connect(str(DB_PATH))
    conn.executescript(_SCHEMA_SQL)
    existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(steps)")}
    for migration in _MIGRATIONS:
        col = migration.split('"')[1]
        if col not in existing_cols:
            conn.execute(migration)
    conn.commit()
    conn.close()


class _LocalStorageClient(BaseStorageClient):
    """Stores element files on the local filesystem under .files/."""

    def __init__(self, base_dir: Path) -> None:
        self._base = base_dir
        self._base.mkdir(exist_ok=True)

    async def upload_file(
        self,
        object_key: str,
        data: Union[bytes, str],
        mime: str = "application/octet-stream",
        overwrite: bool = True,
        content_disposition: str | None = None,
    ) -> Dict[str, Any]:
        dest = (self._base / object_key).resolve()
        if not dest.is_relative_to(self._base.resolve()):
            raise ValueError(f"Invalid object_key: {object_key!r}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        mode = "wb" if isinstance(data, bytes) else "w"
        with open(dest, mode) as f:
            f.write(data)
        return {"object_key": object_key, "url": f"/public/.files/{object_key}"}

    async def delete_file(self, object_key: str) -> bool:
        target = self._base / object_key
        if target.exists():
            target.unlink()
            return True
        return False

    async def get_read_url(self, object_key: str) -> str:
        return f"/public/.files/{object_key}"

    async def close(self) -> None:
        pass


_FILES_DIR = Path(__file__).parent / "public" / ".files"


def make_data_layer() -> SQLAlchemyDataLayer:
    return SQLAlchemyDataLayer(conninfo=DB_URL, storage_provider=_LocalStorageClient(_FILES_DIR))

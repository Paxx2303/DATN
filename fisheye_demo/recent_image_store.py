from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any


def _clamp_limit(value: int, *, minimum: int = 1, maximum: int = 1000) -> int:
    return max(minimum, min(maximum, int(value)))


class RecentImageStore:
    def __init__(self, db_path: Path, max_images: int = 100) -> None:
        self.db_path = Path(db_path)
        self.max_images = _clamp_limit(max_images)
        self._lock = threading.Lock()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._lock:
            with self._connect() as connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS recent_images (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        source_key TEXT NOT NULL UNIQUE,
                        source_result_id TEXT,
                        task TEXT NOT NULL,
                        media_type TEXT NOT NULL,
                        image_role TEXT NOT NULL,
                        filename TEXT NOT NULL,
                        mime_type TEXT NOT NULL,
                        width INTEGER NOT NULL,
                        height INTEGER NOT NULL,
                        created_at TEXT NOT NULL,
                        metadata_json TEXT NOT NULL,
                        image_blob BLOB NOT NULL
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_recent_images_created_at
                    ON recent_images(created_at DESC, id DESC)
                    """
                )
                connection.commit()

    def add_image(
        self,
        *,
        source_key: str,
        source_result_id: str | None,
        task: str,
        media_type: str,
        image_role: str,
        filename: str,
        mime_type: str,
        width: int,
        height: int,
        created_at: str,
        metadata: dict[str, Any] | None,
        image_bytes: bytes,
    ) -> int:
        metadata_json = json.dumps(metadata or {}, ensure_ascii=False)
        with self._lock:
            with self._connect() as connection:
                cursor = connection.execute(
                    """
                    INSERT INTO recent_images (
                        source_key,
                        source_result_id,
                        task,
                        media_type,
                        image_role,
                        filename,
                        mime_type,
                        width,
                        height,
                        created_at,
                        metadata_json,
                        image_blob
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source_key) DO UPDATE SET
                        source_result_id=excluded.source_result_id,
                        task=excluded.task,
                        media_type=excluded.media_type,
                        image_role=excluded.image_role,
                        filename=excluded.filename,
                        mime_type=excluded.mime_type,
                        width=excluded.width,
                        height=excluded.height,
                        created_at=excluded.created_at,
                        metadata_json=excluded.metadata_json,
                        image_blob=excluded.image_blob
                    """,
                    (
                        source_key,
                        source_result_id,
                        task,
                        media_type,
                        image_role,
                        filename,
                        mime_type,
                        width,
                        height,
                        created_at,
                        metadata_json,
                        image_bytes,
                    ),
                )
                self._prune_locked(connection)
                connection.commit()
                return int(cursor.lastrowid or 0)

    def _prune_locked(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            DELETE FROM recent_images
            WHERE id NOT IN (
                SELECT id
                FROM recent_images
                ORDER BY created_at DESC, id DESC
                LIMIT ?
            )
            """,
            (self.max_images,),
        )

    def list_recent(self, limit: int = 20) -> list[dict[str, Any]]:
        safe_limit = _clamp_limit(limit, maximum=self.max_images)
        with self._lock:
            with self._connect() as connection:
                rows = connection.execute(
                    """
                    SELECT
                        id,
                        source_key,
                        source_result_id,
                        task,
                        media_type,
                        image_role,
                        filename,
                        mime_type,
                        width,
                        height,
                        created_at,
                        metadata_json
                    FROM recent_images
                    ORDER BY created_at DESC, id DESC
                    LIMIT ?
                    """,
                    (safe_limit,),
                ).fetchall()

        items: list[dict[str, Any]] = []
        for row in rows:
            metadata_json = row["metadata_json"] or "{}"
            try:
                metadata = json.loads(metadata_json)
            except json.JSONDecodeError:
                metadata = {}

            items.append(
                {
                    "id": int(row["id"]),
                    "source_key": row["source_key"],
                    "source_result_id": row["source_result_id"],
                    "task": row["task"],
                    "media_type": row["media_type"],
                    "image_role": row["image_role"],
                    "filename": row["filename"],
                    "mime_type": row["mime_type"],
                    "width": int(row["width"]),
                    "height": int(row["height"]),
                    "created_at": row["created_at"],
                    "metadata": metadata,
                }
            )
        return items

    def get_image(self, image_id: int) -> dict[str, Any] | None:
        with self._lock:
            with self._connect() as connection:
                row = connection.execute(
                    """
                    SELECT
                        id,
                        filename,
                        mime_type,
                        width,
                        height,
                        created_at,
                        image_blob
                    FROM recent_images
                    WHERE id = ?
                    """,
                    (image_id,),
                ).fetchone()

        if row is None:
            return None

        return {
            "id": int(row["id"]),
            "filename": row["filename"],
            "mime_type": row["mime_type"],
            "width": int(row["width"]),
            "height": int(row["height"]),
            "created_at": row["created_at"],
            "image_bytes": row["image_blob"],
        }

    def stats(self) -> dict[str, Any]:
        with self._lock:
            with self._connect() as connection:
                count_row = connection.execute("SELECT COUNT(*) AS count FROM recent_images").fetchone()
        return {
            "db_path": str(self.db_path),
            "capacity": self.max_images,
            "stored_images": int(count_row["count"] if count_row is not None else 0),
        }

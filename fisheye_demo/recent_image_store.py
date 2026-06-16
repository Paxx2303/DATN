"""
recent_image_store.py — Fast Image Result Buffer

THIẾT KẾ:
- SQLite in-memory hoặc file riêng: recent_images.db
- Lưu tối đa RECENT_IMAGE_LIMIT bản ghi.
- Mỗi bản ghi chứa result_id + base64 thumbnail (JPEG 320px width).
- Thread-safe với threading.Lock.
"""

import sqlite3
import threading
import base64
import io
import logging
from PIL import Image
from config import Config

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_DB_PATH = str(Config.RECENT_IMAGE_DB)


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False, timeout=15.0)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS recent_images (
            result_id  TEXT PRIMARY KEY,
            thumbnail  TEXT,      -- base64 JPEG thumbnail
            media_type TEXT,      -- "image" | "video"
            filename   TEXT,
            summary    TEXT,      -- JSON string
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    return conn


def push_image(result_id: str, pil_image: Image.Image, 
               media_type: str, filename: str, summary: dict) -> None:
    """
    Thêm ảnh vào buffer. Nếu vượt quá LIMIT, xóa bản ghi cũ nhất.
    
    Parameters
    ----------
    pil_image : Ảnh PIL (sẽ resize và encode thành base64 thumbnail)
    """
    import json
    
    # Tạo thumbnail 320px width
    thumb = pil_image.copy()
    thumb.thumbnail((320, 240), Image.LANCZOS)
    buffer = io.BytesIO()
    thumb.save(buffer, format="JPEG", quality=75)
    thumb_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
    
    with _lock:
        conn = _get_conn()
        try:
            # Insert hoặc replace nếu trùng result_id
            conn.execute(
                """INSERT OR REPLACE INTO recent_images 
                   (result_id, thumbnail, media_type, filename, summary)
                   VALUES (?,?,?,?,?)
                """,
                (result_id, thumb_b64, media_type, filename, json.dumps(summary))
            )
            # Dọn dẹp: giữ tối đa LIMIT bản ghi
            conn.execute(
                """DELETE FROM recent_images WHERE result_id NOT IN (
                    SELECT result_id FROM recent_images 
                    ORDER BY created_at DESC LIMIT ?
                )""",
                (Config.RECENT_IMAGE_LIMIT,)
            )
            conn.commit()
        finally:
            conn.close()


def get_recent(limit: int = 20) -> list[dict]:
    """Lấy danh sách ảnh gần nhất, mới nhất trước."""
    import json
    conn = _get_conn()
    try:
        cur = conn.execute(
            """SELECT result_id, thumbnail, media_type, filename, summary, created_at
               FROM recent_images ORDER BY created_at DESC LIMIT ?
            """,
            (limit,)
        )
        rows = cur.fetchall()
        result = []
        for row in rows:
            d = {
                "result_id": row[0],
                "thumbnail": row[1],
                "media_type": row[2],
                "filename": row[3],
                "created_at": row[5],
            }
            try:
                d["summary"] = json.loads(row[4] or "{}")
            except (json.JSONDecodeError, TypeError):
                d["summary"] = {}
            result.append(d)
        return result
    finally:
        conn.close()

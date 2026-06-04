"""
db.py — Database Abstraction Layer

THIẾT KẾ:
- _DB_TYPE: "sqlite" | "postgresql" — quyết định khi init_db() chạy
- _pg_pool: psycopg2 SimpleConnectionPool (chỉ dùng khi PostgreSQL)
- _sqlite_path: path đến fisheye.db (chỉ dùng khi SQLite)
- Tất cả function dùng %s làm placeholder → _adapt_sql() tự chuyển thành ? cho SQLite
"""

import sqlite3
import json
import logging
import os
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

# Module-level state
_DB_TYPE: str = "sqlite"
_pg_pool = None           # psycopg2.pool.SimpleConnectionPool
_sqlite_path: str = ""


def init_db() -> str:
    """
    Khởi tạo database. Gọi một lần duy nhất từ create_app().
    Returns: "sqlite" hoặc "postgresql"
    """
    global _DB_TYPE, _pg_pool, _sqlite_path
    
    database_url = os.getenv("DATABASE_URL", "")
    
    if database_url.startswith("postgresql://") or database_url.startswith("postgres://"):
        # ── PostgreSQL path ──────────────────────────────────
        try:
            import psycopg2.pool
            _pg_pool = psycopg2.pool.SimpleConnectionPool(1, 10, database_url)
            _DB_TYPE = "postgresql"
            _create_tables_pg()
            logger.info("✅ PostgreSQL connected via connection pool")
            return "postgresql"
        except Exception as e:
            logger.error(f"❌ PostgreSQL connection failed: {e}. Falling back to SQLite.")
    
    # ── SQLite path (fallback) ───────────────────────────────
    from config import Config
    _sqlite_path = str(Config.DB_PATH)
    _DB_TYPE = "sqlite"
    conn = sqlite3.connect(_sqlite_path)
    _create_tables_sqlite(conn)
    conn.close()
    logger.info(f"✅ SQLite initialized at {_sqlite_path}")
    return "sqlite"


def _adapt_sql(sql: str) -> str:
    """
    Chuyển đổi placeholder:
    - PostgreSQL dùng %s
    - SQLite dùng ?
    Nếu đang dùng SQLite, replace %s → ?
    """
    if _DB_TYPE == "sqlite":
        return sql.replace("%s", "?")
    return sql


def _get_connection():
    """Lấy connection từ pool (PostgreSQL) hoặc mở mới (SQLite)."""
    if _DB_TYPE == "postgresql":
        return _pg_pool.getconn()
    return sqlite3.connect(_sqlite_path)


def _release_connection(conn) -> None:
    """Trả connection về pool (PostgreSQL) hoặc đóng (SQLite)."""
    if _DB_TYPE == "postgresql":
        _pg_pool.putconn(conn)
    else:
        conn.close()


def _execute(sql: str, params: tuple = (), fetch: str = "none") -> Any:
    """
    Thực thi SQL với auto-adapt placeholder và connection management.
    
    Parameters
    ----------
    sql    : SQL string dùng %s placeholder
    params : tuple các giá trị tham số
    fetch  : "none" | "one" | "all"
    """
    sql = _adapt_sql(sql)
    conn = _get_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        
        if fetch == "one":
            result = cur.fetchone()
        elif fetch == "all":
            result = cur.fetchall()
        else:
            result = None
        
        conn.commit()
        return result
    except Exception as e:
        conn.rollback()
        logger.error(f"DB error: {e} | SQL: {sql[:100]}")
        raise
    finally:
        _release_connection(conn)


# ── DDL: Tạo bảng ────────────────────────────────────────────

def _sqlite_migrate(cur) -> None:
    """Idempotent migration — adds columns that may be absent in older databases."""
    migrations = [
        ("detections", "summary",        "TEXT DEFAULT '{}'"),
        ("detections", "artifacts",      "TEXT DEFAULT '{}'"),
        ("detections", "gcs_urls",       "TEXT DEFAULT '{}'"),
        ("detections", "source_layout",  "TEXT DEFAULT 'normal'"),
        ("detections", "preprocessing",  "TEXT DEFAULT '{}'"),
        ("alerts",     "is_acknowledged","INTEGER DEFAULT 0"),
    ]
    for table, col, definition in migrations:
        try:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {definition}")
        except Exception:
            pass  # column already exists


def _create_tables_sqlite(conn: sqlite3.Connection) -> None:
    """Tạo toàn bộ schema cho SQLite."""
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS detections (
            id           TEXT PRIMARY KEY,
            filename     TEXT,
            task         TEXT,
            media_type   TEXT,
            source_layout TEXT,
            preprocessing TEXT,
            summary      TEXT,
            artifacts    TEXT,
            gcs_urls     TEXT,
            created_at   TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS alerts (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_type      TEXT,
            message         TEXT,
            camera_source   TEXT,
            actual_count    INTEGER,
            is_acknowledged INTEGER DEFAULT 0,
            created_at      TEXT DEFAULT (datetime('now'))
        );
        
        CREATE TABLE IF NOT EXISTS vehicle_speeds (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            detection_id TEXT,
            track_id     INTEGER,
            vehicle_type TEXT,
            speed_kmh    REAL,
            recorded_at  TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (detection_id) REFERENCES detections(id)
        );
        
        CREATE TABLE IF NOT EXISTS heatmap_data (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            camera_id   TEXT,
            grid_json   TEXT,
            recorded_at TEXT DEFAULT (datetime('now'))
        );
        
        CREATE TABLE IF NOT EXISTS incidents (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            camera_id   TEXT,
            incident_type TEXT,
            description TEXT,
            bbox_json   TEXT,
            track_id    INTEGER,
            occurred_at TEXT DEFAULT (datetime('now'))
        );
    """)
    _sqlite_migrate(cur)
    conn.commit()


def _create_tables_pg() -> None:
    """Tạo toàn bộ schema cho PostgreSQL."""
    sql = """
        CREATE TABLE IF NOT EXISTS detections (
            id            VARCHAR(64) PRIMARY KEY,
            filename      VARCHAR(255),
            task          VARCHAR(32),
            media_type    VARCHAR(32),
            source_layout VARCHAR(32),
            preprocessing TEXT,
            summary       TEXT,
            artifacts     TEXT,
            gcs_urls      TEXT,
            created_at    TIMESTAMP DEFAULT NOW()
        );
        
        CREATE TABLE IF NOT EXISTS alerts (
            id              SERIAL PRIMARY KEY,
            alert_type      VARCHAR(64),
            message         TEXT,
            camera_source   VARCHAR(128),
            actual_count    INTEGER,
            is_acknowledged BOOLEAN DEFAULT FALSE,
            created_at      TIMESTAMP DEFAULT NOW()
        );
        
        CREATE TABLE IF NOT EXISTS vehicle_speeds (
            id           SERIAL PRIMARY KEY,
            detection_id VARCHAR(64) REFERENCES detections(id),
            track_id     INTEGER,
            vehicle_type VARCHAR(64),
            speed_kmh    FLOAT,
            recorded_at  TIMESTAMP DEFAULT NOW()
        );
        
        CREATE TABLE IF NOT EXISTS heatmap_data (
            id          SERIAL PRIMARY KEY,
            camera_id   VARCHAR(128),
            grid_json   TEXT,
            recorded_at TIMESTAMP DEFAULT NOW()
        );
        
        CREATE TABLE IF NOT EXISTS incidents (
            id            SERIAL PRIMARY KEY,
            camera_id     VARCHAR(128),
            incident_type VARCHAR(64),
            description   TEXT,
            bbox_json     TEXT,
            track_id      INTEGER,
            occurred_at   TIMESTAMP DEFAULT NOW()
        );
    """
    _execute(sql)


# ── DML: Business operations ──────────────────────────────────

def insert_detection(record: dict[str, Any]) -> None:
    """
    Lưu kết quả một phiên nhận diện.
    record phải có keys: id, filename, task, media_type, source_layout,
                         preprocessing, summary, artifacts, gcs_urls
    """
    _execute(
        """INSERT INTO detections
           (id, filename, task, media_type, source_layout, preprocessing,
            summary, artifacts, gcs_urls, created_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            record["id"],
            record.get("filename", ""),
            record.get("task", "detect"),
            record.get("media_type", "image"),
            record.get("source_layout", "normal"),
            json.dumps(record.get("preprocessing", {})),
            json.dumps(record.get("summary", {})),
            json.dumps(record.get("artifacts", {})),
            json.dumps(record.get("gcs_urls", {})),
            datetime.utcnow().isoformat(),
        ),
    )


def get_detections(limit: int = 50, offset: int = 0) -> list[dict]:
    """Lấy danh sách kết quả nhận diện, mới nhất trước."""
    rows = _execute(
        """SELECT id, filename, task, media_type, source_layout, 
                  summary, artifacts, created_at
           FROM detections ORDER BY created_at DESC LIMIT %s OFFSET %s
        """,
        (limit, offset),
        fetch="all",
    )
    if not rows:
        return []
    cols = ["id", "filename", "task", "media_type", "source_layout",
            "summary", "artifacts", "created_at"]
    result = []
    for row in rows:
        d = dict(zip(cols, row))
        # Parse JSON fields
        for field in ("summary", "artifacts"):
            try:
                d[field] = json.loads(d[field] or "{}")
            except (json.JSONDecodeError, TypeError):
                d[field] = {}
        result.append(d)
    return result


def get_detection_by_id(detection_id: str) -> dict | None:
    """Lấy chi tiết một phiên nhận diện theo ID."""
    row = _execute(
        "SELECT * FROM detections WHERE id = %s",
        (detection_id,),
        fetch="one",
    )
    if not row:
        return None
    cols = ["id", "filename", "task", "media_type", "source_layout",
            "preprocessing", "summary", "artifacts", "gcs_urls", "created_at"]
    d = dict(zip(cols, row))
    for field in ("preprocessing", "summary", "artifacts", "gcs_urls"):
        try:
            d[field] = json.loads(d[field] or "{}")
        except (json.JSONDecodeError, TypeError):
            d[field] = {}
    return d


def insert_alert(alert_type: str, message: str, camera_source: str, count: int) -> None:
    """Lưu một cảnh báo mật độ/ùn tắc."""
    _execute(
        """INSERT INTO alerts (alert_type, message, camera_source, actual_count)
           VALUES (%s, %s, %s, %s)
        """,
        (alert_type, message, camera_source, count),
    )


def get_recent_alerts(limit: int = 20) -> list[dict]:
    """Lấy các cảnh báo gần nhất."""
    rows = _execute(
        """SELECT id, alert_type, message, camera_source, actual_count, 
                  is_acknowledged, created_at
           FROM alerts ORDER BY created_at DESC LIMIT %s
        """,
        (limit,),
        fetch="all",
    )
    if not rows:
        return []
    cols = ["id", "alert_type", "message", "camera_source", 
            "actual_count", "is_acknowledged", "created_at"]
    return [dict(zip(cols, row)) for row in rows]


def insert_vehicle_speed(detection_id: str, track_id: int, 
                          vehicle_type: str, speed_kmh: float) -> None:
    """Lưu bản ghi tốc độ của một xe theo track_id."""
    _execute(
        """INSERT INTO vehicle_speeds (detection_id, track_id, vehicle_type, speed_kmh)
           VALUES (%s, %s, %s, %s)
        """,
        (detection_id, track_id, vehicle_type, speed_kmh),
    )


def insert_incident(camera_id: str, incident_type: str, description: str,
                     bbox: list, track_id: int) -> None:
    """Lưu sự cố phát hiện (đỗ sai, ngược chiều...)."""
    _execute(
        """INSERT INTO incidents (camera_id, incident_type, description, bbox_json, track_id)
           VALUES (%s, %s, %s, %s, %s)
        """,
        (camera_id, incident_type, description, json.dumps(bbox), track_id),
    )

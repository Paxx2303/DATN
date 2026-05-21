"""
db.py — PostgreSQL database layer cho fisheye_demo (GCP Cloud SQL)

Hỗ trợ 2 chế độ:
- PostgreSQL (production / GCP Cloud SQL) khi có DATABASE_URL
- SQLite fallback (local dev) khi không có DATABASE_URL

Schema:
  detections       — mỗi lần detect ảnh/video/camera
  live_sessions    — phiên live stream
  traffic_counts   — đếm xe theo giờ (aggregated)
  cloud_snapshots  — metadata ảnh đã upload lên GCS
  alerts           — lịch sử cảnh báo mật độ
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Generator

logger = logging.getLogger("fisheye_demo.db")

# ── Lazy import psycopg2 / sqlite3 ──────────────────────────────────────────

_db_lock = threading.Lock()
_pool: Any = None          # psycopg2 SimpleConnectionPool hoặc None
_sqlite_path: str | None = None
_backend: str = "none"     # "postgres" | "sqlite"


def _get_database_url() -> str | None:
    return (
        os.getenv("DATABASE_URL")
        or os.getenv("FISHEYE_DATABASE_URL")
        or os.getenv("CLOUD_SQL_DATABASE_URL")
    )


def _get_sqlite_fallback_path() -> str:
    # Try relative path first, then absolute path
    default_path = os.getenv("FISHEYE_SQLITE_DB", "fisheye.db")
    if not os.path.exists(default_path) and not default_path.startswith("/"):
        # Try with fisheye_demo prefix
        alt_path = f"fisheye_demo/{default_path}"
        if os.path.exists(alt_path):
            return alt_path
    return default_path


def init_db(*, force: bool = False) -> str:
    """Khởi tạo kết nối DB. Trả về backend đang dùng: 'postgres' | 'sqlite'."""
    global _pool, _sqlite_path, _backend

    with _db_lock:
        if _backend != "none" and not force:
            return _backend

        database_url = _get_database_url()

        if database_url:
            try:
                import psycopg2
                from psycopg2 import pool as pg_pool

                _pool = pg_pool.ThreadedConnectionPool(
                    minconn=1,
                    maxconn=10,
                    dsn=database_url,
                    connect_timeout=10,
                )
                _backend = "postgres"
                logger.info("DB backend: PostgreSQL (Cloud SQL)")
            except Exception as exc:
                logger.warning("PostgreSQL init failed (%s), falling back to SQLite", exc)
                _pool = None
                _backend = "sqlite"
                _sqlite_path = _get_sqlite_fallback_path()
        else:
            _backend = "sqlite"
            _sqlite_path = _get_sqlite_fallback_path()
            logger.info("DB backend: SQLite (%s)", _sqlite_path)

        _create_schema()
        return _backend


@contextmanager
def get_conn() -> Generator:
    """Context manager trả về connection. Tự commit/rollback."""
    global _pool, _sqlite_path, _backend

    if _backend == "none":
        init_db()

    if _backend == "postgres" and _pool is not None:
        conn = _pool.getconn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            _pool.putconn(conn)
    else:
        import sqlite3
        path = _sqlite_path or _get_sqlite_fallback_path()
        conn = sqlite3.connect(path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def _placeholder(backend: str) -> str:
    """Trả về placeholder phù hợp: %s (postgres) hoặc ? (sqlite)."""
    return "%s" if backend == "postgres" else "?"


def _adapt_sql(sql: str) -> str:
    """Chuyển %s → ? nếu đang dùng SQLite."""
    if _backend == "sqlite":
        return sql.replace("%s", "?")
    return sql


# ── Schema creation ──────────────────────────────────────────────────────────

_SCHEMA_POSTGRES = """
CREATE TABLE IF NOT EXISTS detections (
    id              TEXT PRIMARY KEY,
    task            TEXT NOT NULL,
    media_type      TEXT NOT NULL,
    filename        TEXT,
    source_layout   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    conf_threshold  REAL,
    iou_threshold   REAL,
    total_objects   INTEGER DEFAULT 0,
    inference_ms    REAL,
    class_counts    JSONB,
    model_name      TEXT,
    device          TEXT,
    preprocessing   JSONB,
    artifacts       JSONB,
    gcs_urls        JSONB
);

CREATE INDEX IF NOT EXISTS idx_detections_created_at ON detections(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_detections_task ON detections(task);
CREATE INDEX IF NOT EXISTS idx_detections_media_type ON detections(media_type);

CREATE TABLE IF NOT EXISTS live_sessions (
    id              TEXT PRIMARY KEY,
    source_url      TEXT,
    source_mode     TEXT,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at        TIMESTAMPTZ,
    cycle_count     INTEGER DEFAULT 0,
    total_objects   INTEGER DEFAULT 0,
    class_counts    JSONB,
    conf_threshold  REAL,
    iou_threshold   REAL,
    status          TEXT DEFAULT 'active'
);

CREATE INDEX IF NOT EXISTS idx_live_sessions_started_at ON live_sessions(started_at DESC);

CREATE TABLE IF NOT EXISTS traffic_counts (
    id              BIGSERIAL PRIMARY KEY,
    hour_bucket     TIMESTAMPTZ NOT NULL,
    camera_source   TEXT NOT NULL DEFAULT 'upload',
    class_name      TEXT NOT NULL,
    count           INTEGER NOT NULL DEFAULT 0,
    UNIQUE(hour_bucket, camera_source, class_name)
);

CREATE INDEX IF NOT EXISTS idx_traffic_counts_hour ON traffic_counts(hour_bucket DESC);
CREATE INDEX IF NOT EXISTS idx_traffic_counts_source ON traffic_counts(camera_source);

CREATE TABLE IF NOT EXISTS cloud_snapshots (
    id              BIGSERIAL PRIMARY KEY,
    detection_id    TEXT REFERENCES detections(id) ON DELETE CASCADE,
    gcs_bucket      TEXT NOT NULL,
    gcs_object_name TEXT NOT NULL UNIQUE,
    gcs_public_url  TEXT,
    image_role      TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ,
    deleted         BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_cloud_snapshots_created_at ON cloud_snapshots(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_cloud_snapshots_expires_at ON cloud_snapshots(expires_at);
CREATE INDEX IF NOT EXISTS idx_cloud_snapshots_deleted ON cloud_snapshots(deleted);

CREATE TABLE IF NOT EXISTS alerts (
    id              BIGSERIAL PRIMARY KEY,
    alert_type      TEXT NOT NULL,
    camera_source   TEXT,
    class_name      TEXT,
    threshold       INTEGER,
    actual_count    INTEGER,
    message         TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    acknowledged    BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_alerts_created_at ON alerts(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_acknowledged ON alerts(acknowledged);

CREATE TABLE IF NOT EXISTS incidents (
    id              TEXT PRIMARY KEY,
    type            TEXT NOT NULL,
    severity        TEXT NOT NULL,
    confidence      REAL NOT NULL,
    camera_id       TEXT NOT NULL,
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    location        JSONB,
    state           TEXT NOT NULL DEFAULT 'active',
    duration        REAL DEFAULT 0.0,
    metadata        JSONB,
    video_url       TEXT,
    thumbnail_url   TEXT
);

CREATE INDEX IF NOT EXISTS idx_incidents_timestamp ON incidents(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_incidents_camera_id ON incidents(camera_id);
CREATE INDEX IF NOT EXISTS idx_incidents_type ON incidents(type);
CREATE INDEX IF NOT EXISTS idx_incidents_severity ON incidents(severity);

CREATE TABLE IF NOT EXISTS incident_configs (
    camera_id       TEXT NOT NULL DEFAULT 'default',
    configs         JSONB NOT NULL,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    user_id         TEXT,
    PRIMARY KEY (camera_id)
);
"""

_SCHEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS detections (
    id              TEXT PRIMARY KEY,
    task            TEXT NOT NULL,
    media_type      TEXT NOT NULL,
    filename        TEXT,
    source_layout   TEXT,
    created_at      TEXT NOT NULL,
    conf_threshold  REAL,
    iou_threshold   REAL,
    total_objects   INTEGER DEFAULT 0,
    inference_ms    REAL,
    class_counts    TEXT,
    model_name      TEXT,
    device          TEXT,
    preprocessing   TEXT,
    artifacts       TEXT,
    gcs_urls        TEXT
);

CREATE INDEX IF NOT EXISTS idx_detections_created_at ON detections(created_at DESC);

CREATE TABLE IF NOT EXISTS live_sessions (
    id              TEXT PRIMARY KEY,
    source_url      TEXT,
    source_mode     TEXT,
    started_at      TEXT NOT NULL,
    ended_at        TEXT,
    cycle_count     INTEGER DEFAULT 0,
    total_objects   INTEGER DEFAULT 0,
    class_counts    TEXT,
    conf_threshold  REAL,
    iou_threshold   REAL,
    status          TEXT DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS traffic_counts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    hour_bucket     TEXT NOT NULL,
    camera_source   TEXT NOT NULL DEFAULT 'upload',
    class_name      TEXT NOT NULL,
    count           INTEGER NOT NULL DEFAULT 0,
    UNIQUE(hour_bucket, camera_source, class_name)
);

CREATE INDEX IF NOT EXISTS idx_traffic_counts_hour ON traffic_counts(hour_bucket DESC);

CREATE TABLE IF NOT EXISTS cloud_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    detection_id    TEXT,
    gcs_bucket      TEXT NOT NULL,
    gcs_object_name TEXT NOT NULL UNIQUE,
    gcs_public_url  TEXT,
    image_role      TEXT,
    created_at      TEXT NOT NULL,
    expires_at      TEXT,
    deleted         INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS alerts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_type      TEXT NOT NULL,
    camera_source   TEXT,
    class_name      TEXT,
    threshold       INTEGER,
    actual_count    INTEGER,
    message         TEXT,
    created_at      TEXT NOT NULL,
    acknowledged    INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_alerts_created_at ON alerts(created_at DESC);

CREATE TABLE IF NOT EXISTS incidents (
    id              TEXT PRIMARY KEY,
    type            TEXT NOT NULL,
    severity        TEXT NOT NULL,
    confidence      REAL NOT NULL,
    camera_id       TEXT NOT NULL,
    timestamp       TEXT NOT NULL,
    location        TEXT,
    state           TEXT NOT NULL DEFAULT 'active',
    duration        REAL DEFAULT 0.0,
    metadata        TEXT,
    video_url       TEXT,
    thumbnail_url   TEXT
);

CREATE INDEX IF NOT EXISTS idx_incidents_timestamp ON incidents(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_incidents_camera_id ON incidents(camera_id);

CREATE TABLE IF NOT EXISTS incident_configs (
    camera_id       TEXT NOT NULL DEFAULT 'default',
    configs         TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    user_id         TEXT,
    PRIMARY KEY (camera_id)
);
"""


def _create_schema() -> None:
    schema = _SCHEMA_POSTGRES if _backend == "postgres" else _SCHEMA_SQLITE
    with get_conn() as conn:
        cur = conn.cursor()
        # Tách từng statement và chạy riêng
        for stmt in schema.split(";"):
            stmt = stmt.strip()
            if stmt:
                try:
                    cur.execute(stmt)
                except Exception as exc:
                    logger.debug("Schema stmt skipped: %s — %s", stmt[:60], exc)
    logger.info("DB schema ready (backend=%s)", _backend)


# ── Detection CRUD ───────────────────────────────────────────────────────────

def insert_detection(record: dict[str, Any], gcs_urls: dict[str, str] | None = None) -> None:
    """Lưu một detection record vào DB."""
    summary = record.get("summary") or {}
    model = record.get("model") or {}
    sql = _adapt_sql("""
        INSERT INTO detections
            (id, task, media_type, filename, source_layout, created_at,
             conf_threshold, iou_threshold, total_objects, inference_ms,
             class_counts, model_name, device, preprocessing, artifacts, gcs_urls)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT(id) DO NOTHING
    """)
    params = (
        record.get("id"),
        record.get("task"),
        record.get("media_type"),
        record.get("filename"),
        record.get("source_layout"),
        record.get("created_at"),
        record.get("parameters", {}).get("confidence_threshold"),
        record.get("parameters", {}).get("iou_threshold"),
        summary.get("total_objects", 0),
        summary.get("inference_ms"),
        json.dumps(summary.get("class_counts") or {}),
        model.get("loaded_from_name"),
        model.get("device"),
        json.dumps(record.get("preprocessing") or {}),
        json.dumps(record.get("artifacts") or {}),
        json.dumps(gcs_urls or {}),
    )
    with get_conn() as conn:
        conn.cursor().execute(sql, params)


def list_detections(limit: int = 50, offset: int = 0, task: str | None = None) -> list[dict[str, Any]]:
    """Lấy danh sách detections gần nhất."""
    if task:
        sql = _adapt_sql(
            "SELECT * FROM detections WHERE task=%s ORDER BY created_at DESC LIMIT %s OFFSET %s"
        )
        params: tuple = (task, limit, offset)
    else:
        sql = _adapt_sql(
            "SELECT * FROM detections ORDER BY created_at DESC LIMIT %s OFFSET %s"
        )
        params = (limit, offset)

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        rows = cur.fetchall()

    return [_row_to_dict(row) for row in rows]


def get_detection(detection_id: str) -> dict[str, Any] | None:
    sql = _adapt_sql("SELECT * FROM detections WHERE id=%s")
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql, (detection_id,))
        row = cur.fetchone()
    return _row_to_dict(row) if row else None


def count_detections(task: str | None = None) -> int:
    if task:
        sql = _adapt_sql("SELECT COUNT(*) FROM detections WHERE task=%s")
        params: tuple = (task,)
    else:
        sql = "SELECT COUNT(*) FROM detections"
        params = ()
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        row = cur.fetchone()
    return int(row[0]) if row else 0


# ── Traffic counts ───────────────────────────────────────────────────────────

def upsert_traffic_counts(
    class_counts: dict[str, int],
    camera_source: str = "upload",
    hour_bucket: str | None = None,
) -> None:
    """Cộng dồn số lượng xe vào bảng traffic_counts theo giờ."""
    if not class_counts:
        return

    if hour_bucket is None:
        now = datetime.now(timezone.utc)
        hour_bucket = now.strftime("%Y-%m-%dT%H:00:00Z")

    if _backend == "postgres":
        sql = """
            INSERT INTO traffic_counts (hour_bucket, camera_source, class_name, count)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (hour_bucket, camera_source, class_name)
            DO UPDATE SET count = traffic_counts.count + EXCLUDED.count
        """
    else:
        sql = """
            INSERT INTO traffic_counts (hour_bucket, camera_source, class_name, count)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (hour_bucket, camera_source, class_name)
            DO UPDATE SET count = traffic_counts.count + excluded.count
        """

    with get_conn() as conn:
        cur = conn.cursor()
        for class_name, count in class_counts.items():
            if count > 0:
                cur.execute(sql, (hour_bucket, camera_source, class_name, count))


def get_traffic_counts_by_hour(
    hours: int = 24,
    camera_source: str | None = None,
) -> list[dict[str, Any]]:
    """Lấy thống kê đếm xe theo giờ trong N giờ gần nhất."""
    if _backend == "postgres":
        if camera_source:
            sql = """
                SELECT hour_bucket, camera_source, class_name, count
                FROM traffic_counts
                WHERE hour_bucket >= NOW() - INTERVAL '%s hours'
                  AND camera_source = %s
                ORDER BY hour_bucket DESC, class_name
            """
            params: tuple = (hours, camera_source)
        else:
            sql = """
                SELECT hour_bucket, camera_source, class_name, count
                FROM traffic_counts
                WHERE hour_bucket >= NOW() - INTERVAL '%s hours'
                ORDER BY hour_bucket DESC, class_name
            """
            params = (hours,)
    else:
        # SQLite: tính cutoff thủ công
        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
        if camera_source:
            sql = "SELECT hour_bucket, camera_source, class_name, count FROM traffic_counts WHERE hour_bucket >= ? AND camera_source = ? ORDER BY hour_bucket DESC, class_name"
            params = (cutoff, camera_source)
        else:
            sql = "SELECT hour_bucket, camera_source, class_name, count FROM traffic_counts WHERE hour_bucket >= ? ORDER BY hour_bucket DESC, class_name"
            params = (cutoff,)

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        rows = cur.fetchall()

    return [_row_to_dict(row) for row in rows]


def get_class_distribution(hours: int = 24) -> dict[str, int]:
    """Tổng số xe theo class trong N giờ gần nhất."""
    rows = get_traffic_counts_by_hour(hours=hours)
    totals: dict[str, int] = {}
    for row in rows:
        cls = row.get("class_name", "")
        totals[cls] = totals.get(cls, 0) + int(row.get("count", 0))
    return totals


# ── Live sessions ────────────────────────────────────────────────────────────

def insert_live_session(session_id: str, source_url: str, source_mode: str,
                        conf: float, iou: float) -> None:
    sql = _adapt_sql("""
        INSERT INTO live_sessions (id, source_url, source_mode, started_at, conf_threshold, iou_threshold)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT(id) DO NOTHING
    """)
    with get_conn() as conn:
        conn.cursor().execute(sql, (
            session_id,
            source_url,
            source_mode,
            datetime.now(timezone.utc).isoformat(),
            conf,
            iou,
        ))


def update_live_session(session_id: str, *, cycle_count: int, total_objects: int,
                        class_counts: dict[str, int], status: str = "active") -> None:
    sql = _adapt_sql("""
        UPDATE live_sessions
        SET cycle_count=%s, total_objects=%s, class_counts=%s, status=%s
        WHERE id=%s
    """)
    with get_conn() as conn:
        conn.cursor().execute(sql, (
            cycle_count,
            total_objects,
            json.dumps(class_counts),
            status,
            session_id,
        ))


def close_live_session(session_id: str) -> None:
    sql = _adapt_sql("""
        UPDATE live_sessions SET ended_at=%s, status='ended' WHERE id=%s
    """)
    with get_conn() as conn:
        conn.cursor().execute(sql, (
            datetime.now(timezone.utc).isoformat(),
            session_id,
        ))


def list_live_sessions(limit: int = 20) -> list[dict[str, Any]]:
    sql = _adapt_sql(
        "SELECT * FROM live_sessions ORDER BY started_at DESC LIMIT %s"
    )
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql, (limit,))
        rows = cur.fetchall()
    return [_row_to_dict(row) for row in rows]


# ── Cloud snapshots ──────────────────────────────────────────────────────────

def insert_cloud_snapshot(
    detection_id: str | None,
    gcs_bucket: str,
    gcs_object_name: str,
    gcs_public_url: str,
    image_role: str,
    expires_at: str,
) -> int:
    sql = _adapt_sql("""
        INSERT INTO cloud_snapshots
            (detection_id, gcs_bucket, gcs_object_name, gcs_public_url, image_role, created_at, expires_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT(gcs_object_name) DO NOTHING
    """)
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql, (
            detection_id,
            gcs_bucket,
            gcs_object_name,
            gcs_public_url,
            image_role,
            datetime.now(timezone.utc).isoformat(),
            expires_at,
        ))
        if _backend == "postgres":
            cur.execute("SELECT id FROM cloud_snapshots WHERE gcs_object_name=%s", (gcs_object_name,))
            row = cur.fetchone()
            return int(row[0]) if row else 0
        return cur.lastrowid or 0


def list_cloud_snapshots(limit: int = 50, include_deleted: bool = False) -> list[dict[str, Any]]:
    if include_deleted:
        sql = _adapt_sql(
            "SELECT * FROM cloud_snapshots ORDER BY created_at DESC LIMIT %s"
        )
        params: tuple = (limit,)
    else:
        deleted_val = "FALSE" if _backend == "postgres" else "0"
        sql = _adapt_sql(
            f"SELECT * FROM cloud_snapshots WHERE deleted={deleted_val} ORDER BY created_at DESC LIMIT %s"
        )
        params = (limit,)

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        rows = cur.fetchall()
    return [_row_to_dict(row) for row in rows]


def list_expired_cloud_snapshots() -> list[dict[str, Any]]:
    """Lấy danh sách ảnh đã hết hạn (> 6h) chưa bị xóa."""
    if _backend == "postgres":
        sql = """
            SELECT * FROM cloud_snapshots
            WHERE expires_at < NOW() AND deleted = FALSE
            ORDER BY expires_at ASC
        """
        params: tuple = ()
    else:
        now_str = datetime.now(timezone.utc).isoformat()
        sql = "SELECT * FROM cloud_snapshots WHERE expires_at < ? AND deleted = 0 ORDER BY expires_at ASC"
        params = (now_str,)

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        rows = cur.fetchall()
    return [_row_to_dict(row) for row in rows]


def mark_cloud_snapshot_deleted(snapshot_id: int) -> None:
    deleted_val = "TRUE" if _backend == "postgres" else "1"
    sql = _adapt_sql(f"UPDATE cloud_snapshots SET deleted={deleted_val} WHERE id=%s")
    with get_conn() as conn:
        conn.cursor().execute(sql, (snapshot_id,))


# ── Alerts ───────────────────────────────────────────────────────────────────

def insert_alert(
    alert_type: str,
    message: str,
    camera_source: str | None = None,
    class_name: str | None = None,
    threshold: int | None = None,
    actual_count: int | None = None,
) -> int:
    sql = _adapt_sql("""
        INSERT INTO alerts (alert_type, camera_source, class_name, threshold, actual_count, message, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """)
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql, (
            alert_type,
            camera_source,
            class_name,
            threshold,
            actual_count,
            message,
            datetime.now(timezone.utc).isoformat(),
        ))
        if _backend == "postgres":
            cur.execute("SELECT lastval()")
            row = cur.fetchone()
            return int(row[0]) if row else 0
        return cur.lastrowid or 0


def list_alerts(limit: int = 50, unacknowledged_only: bool = False) -> list[dict[str, Any]]:
    if unacknowledged_only:
        ack_val = "FALSE" if _backend == "postgres" else "0"
        sql = _adapt_sql(
            f"SELECT * FROM alerts WHERE acknowledged={ack_val} ORDER BY created_at DESC LIMIT %s"
        )
    else:
        sql = _adapt_sql("SELECT * FROM alerts ORDER BY created_at DESC LIMIT %s")
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql, (limit,))
        rows = cur.fetchall()
    return [_row_to_dict(row) for row in rows]


def acknowledge_alert(alert_id: int) -> None:
    ack_val = "TRUE" if _backend == "postgres" else "1"
    sql = _adapt_sql(f"UPDATE alerts SET acknowledged={ack_val} WHERE id=%s")
    with get_conn() as conn:
        conn.cursor().execute(sql, (alert_id,))


# ── Incidents & Incident Configs ──────────────────────────────────────────────

def insert_incident(record: dict[str, Any]) -> None:
    """Lưu một incident record vào DB."""
    # Ensure database is initialized
    if _backend == "none":
        init_db()
    
    sql = _adapt_sql("""
        INSERT INTO incidents
            (id, type, severity, confidence, camera_id, timestamp,
             location, state, duration, metadata, video_url, thumbnail_url)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT(id) DO NOTHING
    """)
    params = (
        record.get("id"),
        record.get("type"),
        record.get("severity"),
        record.get("confidence"),
        record.get("camera_id"),
        record.get("timestamp") or datetime.now(timezone.utc).isoformat(),
        json.dumps(record.get("location") or {}),
        record.get("state", "active"),
        record.get("duration", 0.0),
        json.dumps(record.get("metadata") or {}),
        record.get("video_url"),
        record.get("thumbnail_url"),
    )
    with get_conn() as conn:
        conn.cursor().execute(sql, params)


def update_incident_state(
    incident_id: str,
    state: str,
    duration: float = 0.0,
    video_url: str | None = None,
    thumbnail_url: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Cập nhật state và duration, metadata của một incident."""
    # Ensure database is initialized
    if _backend == "none":
        init_db()
        
    if metadata is not None:
        sql = _adapt_sql("""
            UPDATE incidents
            SET state=%s, duration=%s, video_url=COALESCE(%s, video_url), thumbnail_url=COALESCE(%s, thumbnail_url), metadata=%s
            WHERE id=%s
        """)
        params = (state, duration, video_url, thumbnail_url, json.dumps(metadata), incident_id)
    else:
        sql = _adapt_sql("""
            UPDATE incidents
            SET state=%s, duration=%s, video_url=COALESCE(%s, video_url), thumbnail_url=COALESCE(%s, thumbnail_url)
            WHERE id=%s
        """)
        params = (state, duration, video_url, thumbnail_url, incident_id)
    with get_conn() as conn:
        conn.cursor().execute(sql, params)


def get_incident(incident_id: str) -> dict[str, Any] | None:
    # Ensure database is initialized
    if _backend == "none":
        init_db()
        
    sql = _adapt_sql("SELECT * FROM incidents WHERE id=%s")
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql, (incident_id,))
        row = cur.fetchone()
    return _row_to_dict(row) if row else None


def list_incidents(
    limit: int = 50,
    offset: int = 0,
    camera_id: str | None = None,
    type: str | None = None,
    severity: str | None = None,
    state: str | None = None,
    time_start: str | None = None,
    time_end: str | None = None,
) -> list[dict[str, Any]]:
    """Lấy danh sách incidents có lọc."""
    conditions = []
    params = []

    if camera_id:
        conditions.append("camera_id = %s")
        params.append(camera_id)
    if type:
        conditions.append("type = %s")
        params.append(type)
    if severity:
        conditions.append("severity = %s")
        params.append(severity)
    if state:
        conditions.append("state = %s")
        params.append(state)
    if time_start:
        conditions.append("timestamp >= %s")
        params.append(time_start)
    if time_end:
        conditions.append("timestamp <= %s")
        params.append(time_end)

    where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
    sql = _adapt_sql(
        f"SELECT * FROM incidents{where_clause} ORDER BY timestamp DESC LIMIT %s OFFSET %s"
    )
    params.extend([limit, offset])

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql, tuple(params))
        rows = cur.fetchall()
    return [_row_to_dict(row) for row in rows]


def count_incidents(
    camera_id: str | None = None,
    type: str | None = None,
    severity: str | None = None,
    state: str | None = None,
    time_start: str | None = None,
    time_end: str | None = None,
) -> int:
    conditions = []
    params = []

    if camera_id:
        conditions.append("camera_id = %s")
        params.append(camera_id)
    if type:
        conditions.append("type = %s")
        params.append(type)
    if severity:
        conditions.append("severity = %s")
        params.append(severity)
    if state:
        conditions.append("state = %s")
        params.append(state)
    if time_start:
        conditions.append("timestamp >= %s")
        params.append(time_start)
    if time_end:
        conditions.append("timestamp <= %s")
        params.append(time_end)

    where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
    sql = _adapt_sql(f"SELECT COUNT(*) FROM incidents{where_clause}")

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql, tuple(params))
        row = cur.fetchone()
    return int(row[0]) if row else 0


def get_incident_stats(hours: int = 24) -> dict[str, Any]:
    """Thống kê chi tiết về các sự cố."""
    if _backend == "postgres":
        cutoff = f"NOW() - INTERVAL '{hours} hours'"
        sql_total = f"SELECT COUNT(*) FROM incidents WHERE timestamp >= {cutoff}"
        sql_by_type = f"SELECT type, COUNT(*) FROM incidents WHERE timestamp >= {cutoff} GROUP BY type"
        sql_by_severity = f"SELECT severity, COUNT(*) FROM incidents WHERE timestamp >= {cutoff} GROUP BY severity"
        sql_by_state = f"SELECT state, COUNT(*) FROM incidents WHERE timestamp >= {cutoff} GROUP BY state"
        params = ()
    else:
        from datetime import timedelta
        cutoff_str = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        sql_total = "SELECT COUNT(*) FROM incidents WHERE timestamp >= ?"
        sql_by_type = "SELECT type, COUNT(*) FROM incidents WHERE timestamp >= ? GROUP BY type"
        sql_by_severity = "SELECT severity, COUNT(*) FROM incidents WHERE timestamp >= ? GROUP BY severity"
        sql_by_state = "SELECT state, COUNT(*) FROM incidents WHERE timestamp >= ? GROUP BY state"
        params = (cutoff_str,)

    with get_conn() as conn:
        cur = conn.cursor()
        
        cur.execute(sql_total, params)
        row = cur.fetchone()
        total = int(row[0]) if row else 0

        cur.execute(sql_by_type, params)
        type_counts = {r[0]: r[1] for r in cur.fetchall()}

        cur.execute(sql_by_severity, params)
        severity_counts = {r[0]: r[1] for r in cur.fetchall()}

        cur.execute(sql_by_state, params)
        state_counts = {r[0]: r[1] for r in cur.fetchall()}

    return {
        "total": total,
        "by_type": type_counts,
        "by_severity": severity_counts,
        "by_state": state_counts,
        "hours_window": hours,
    }


def insert_incident_config(camera_id: str, configs: dict[str, Any], user_id: str | None = None) -> None:
    """Lưu hoặc cập nhật config độ nhạy cho camera."""
    if _backend == "postgres":
        sql = """
            INSERT INTO incident_configs (camera_id, configs, updated_at, user_id)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (camera_id)
            DO UPDATE SET configs = EXCLUDED.configs, updated_at = EXCLUDED.updated_at, user_id = EXCLUDED.user_id
        """
    else:
        sql = """
            INSERT INTO incident_configs (camera_id, configs, updated_at, user_id)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (camera_id)
            DO UPDATE SET configs = excluded.configs, updated_at = excluded.updated_at, user_id = excluded.user_id
        """
    params = (
        camera_id,
        json.dumps(configs),
        datetime.now(timezone.utc).isoformat(),
        user_id,
    )
    with get_conn() as conn:
        conn.cursor().execute(sql, params)


def get_incident_config(camera_id: str) -> dict[str, Any] | None:
    """Lấy config độ nhạy của một camera. Fallback về 'default' nếu không có."""
    # Ensure database is initialized
    if _backend == "none":
        init_db()
        
    sql = _adapt_sql("SELECT configs FROM incident_configs WHERE camera_id=%s")
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql, (camera_id,))
        row = cur.fetchone()
        if not row and camera_id != "default":
            cur.execute(sql, ("default",))
            row = cur.fetchone()
    if row:
        val = row[0]
        if isinstance(val, str):
            try:
                return json.loads(val)
            except json.JSONDecodeError:
                return None
        return val
    return None


# ── Analytics queries ────────────────────────────────────────────────────────

def get_dashboard_stats(hours: int = 24) -> dict[str, Any]:
    """Tổng hợp stats cho dashboard."""
    total = count_detections()
    detect_count = count_detections(task="detect")
    convert_count = count_detections(task="convert")
    class_dist = get_class_distribution(hours=hours)
    unack_alerts = len(list_alerts(limit=100, unacknowledged_only=True))

    # Avg inference ms từ detections gần nhất
    sql = _adapt_sql(
        "SELECT AVG(inference_ms) FROM detections WHERE inference_ms IS NOT NULL AND task='detect' AND created_at >= %s"
    )
    if _backend == "postgres":
        cutoff = f"NOW() - INTERVAL '{hours} hours'"
        sql_avg = f"SELECT AVG(inference_ms) FROM detections WHERE inference_ms IS NOT NULL AND task='detect' AND created_at >= {cutoff}"
        params: tuple = ()
    else:
        from datetime import timedelta
        cutoff_str = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        sql_avg = "SELECT AVG(inference_ms) FROM detections WHERE inference_ms IS NOT NULL AND task='detect' AND created_at >= ?"
        params = (cutoff_str,)

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql_avg, params)
        row = cur.fetchone()
        avg_ms = float(row[0]) if row and row[0] else 0.0

    return {
        "total_runs": total,
        "detect_runs": detect_count,
        "convert_runs": convert_count,
        "class_distribution": class_dist,
        "avg_inference_ms": round(avg_ms, 2),
        "unacknowledged_alerts": unack_alerts,
        "hours_window": hours,
    }


def get_hourly_traffic_chart(hours: int = 24, camera_source: str | None = None) -> list[dict[str, Any]]:
    """Dữ liệu biểu đồ traffic theo giờ, gom theo class."""
    rows = get_traffic_counts_by_hour(hours=hours, camera_source=camera_source)

    # Group by hour_bucket
    buckets: dict[str, dict[str, int]] = {}
    for row in rows:
        bucket = str(row.get("hour_bucket", ""))[:16]  # "2026-05-11T14:00"
        cls = str(row.get("class_name", ""))
        cnt = int(row.get("count", 0))
        if bucket not in buckets:
            buckets[bucket] = {}
        buckets[bucket][cls] = buckets[bucket].get(cls, 0) + cnt

    return [
        {"hour": hour, "counts": counts}
        for hour, counts in sorted(buckets.items())
    ]


# ── Helpers ──────────────────────────────────────────────────────────────────

def _row_to_dict(row: Any) -> dict[str, Any]:
    if row is None:
        return {}
    if hasattr(row, "_asdict"):
        d = row._asdict()
    elif hasattr(row, "keys"):
        d = dict(row)
    else:
        return dict(row)

    # Parse JSON fields
    for key in ("class_counts", "preprocessing", "artifacts", "gcs_urls", "location", "metadata", "configs"):
        if key in d and isinstance(d[key], str):
            try:
                d[key] = json.loads(d[key])
            except (json.JSONDecodeError, TypeError):
                pass

    # Normalize boolean fields
    for key in ("deleted", "acknowledged"):
        if key in d:
            d[key] = bool(d[key])

    return d


def health_check() -> dict[str, Any]:
    """Kiểm tra kết nối DB."""
    try:
        with get_conn() as conn:
            cur = conn.cursor()
            if _backend == "postgres":
                cur.execute("SELECT 1")
            else:
                cur.execute("SELECT 1")
        return {"status": "ok", "backend": _backend}
    except Exception as exc:
        return {"status": "error", "backend": _backend, "error": str(exc)}

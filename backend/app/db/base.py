# backend/app/db/base.py
"""
Database layer supporting PostgreSQL (production) and SQLite (fallback).
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

logger = logging.getLogger("backend.db")

_db_lock = threading.Lock()
_pool: Any = None          # psycopg2 SimpleConnectionPool or None
_sqlite_path: str | None = None
_backend: str = "none"     # "postgres" | "sqlite"


def _get_database_url() -> str | None:
    return (
        os.getenv("DATABASE_URL")
        or os.getenv("FISHEYE_DATABASE_URL")
        or os.getenv("CLOUD_SQL_DATABASE_URL")
    )


def _get_sqlite_fallback_path() -> str:
    # Use environment variable, default to 'data/recent_images.sqlite3' inside project dir
    return os.getenv("FISHEYE_SQLITE_DB", "data/recent_images.sqlite3")


def init_db(*, force: bool = False) -> str:
    """Initializes DB connection pool. Returns 'postgres' or 'sqlite'."""
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
                    maxconn=20,
                    dsn=database_url,
                    connect_timeout=10,
                )
                _backend = "postgres"
                logger.info("Database initialized with PostgreSQL backend")
            except Exception as exc:
                logger.warning("PostgreSQL connection failed (%s), falling back to SQLite", exc)
                _pool = None
                _backend = "sqlite"
                _sqlite_path = _get_sqlite_fallback_path()
        else:
            _backend = "sqlite"
            _sqlite_path = _get_sqlite_fallback_path()
            logger.info("Database initialized with SQLite fallback (%s)", _sqlite_path)

        _create_schema()
        return _backend


@contextmanager
def get_conn() -> Generator[Any, None, None]:
    """Context manager that yields a database connection. Handles commits/rollbacks."""
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
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
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


def _placeholder() -> str:
    """Returns DB-specific parameter placeholder: %s (postgres) or ? (sqlite)."""
    return "%s" if _backend == "postgres" else "?"


def _adapt_sql(sql: str) -> str:
    """Replaces PostgreSQL %s placeholders with SQLite ? if SQLite is active."""
    if _backend == "sqlite":
        return sql.replace("%s", "?")
    return sql


# ── SQLite Fallback Schema Definition ─────────────────────────────────────────

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

CREATE TABLE IF NOT EXISTS vehicle_speeds (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id        TEXT NOT NULL,
    camera_source   TEXT NOT NULL,
    class_name      TEXT NOT NULL,
    speed_kmh       REAL NOT NULL,
    is_overspeed    INTEGER DEFAULT 0,
    cx              REAL,
    cy              REAL,
    timestamp       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_vehicle_speeds_timestamp ON vehicle_speeds(timestamp DESC);

CREATE TABLE IF NOT EXISTS congestion_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    roi_name        TEXT NOT NULL,
    camera_source   TEXT NOT NULL,
    actual_count    INTEGER NOT NULL,
    capacity        INTEGER NOT NULL,
    congestion_ratio REAL NOT NULL,
    state           TEXT NOT NULL,
    timestamp       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_congestion_logs_timestamp ON congestion_logs(timestamp DESC);
"""


def _create_schema() -> None:
    if _backend == "postgres":
        # Schema creation for Postgres in Cloud SQL is pre-executed via migrations/SQL file,
        # but we can also execute standard tables if missing.
        try:
            # Lazy import postgres schema
            with open("database/postgres_schema.sql", "r", encoding="utf-8") as f:
                schema = f.read()
        except Exception:
            # Fallback inlinepostgres schema
            logger.warning("Could not read database/postgres_schema.sql, skipping automatic schema creation")
            return
    else:
        schema = _SCHEMA_SQLITE

    _IGNORABLE_ERRORS = ("already exists",)
    with get_conn() as conn:
        cur = conn.cursor()
        for stmt in schema.split(";"):
            stmt = stmt.strip()
            if not stmt:
                continue
            try:
                cur.execute(stmt)
            except Exception as exc:
                exc_msg = str(exc).lower()
                if any(token in exc_msg for token in _IGNORABLE_ERRORS):
                    logger.debug("Schema stmt skipped: %s", stmt[:60])
                else:
                    logger.warning("Schema stmt failed: %s — %s", stmt[:80], exc)
    logger.info("Database schema applied successfully (backend=%s)", _backend)


# ── Helper converter ──────────────────────────────────────────────────────────

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
    for key in ("deleted", "acknowledged", "is_overspeed"):
        if key in d:
            d[key] = bool(d[key])

    return d


# ── Health check ──────────────────────────────────────────────────────────────

def health_check() -> dict[str, Any]:
    try:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.fetchone()
        return {"status": "ok", "backend": _backend}
    except Exception as exc:
        return {"status": "error", "backend": _backend, "error": str(exc)}


# ── DB CRUD Operations ────────────────────────────────────────────────────────

def insert_detection(record: dict[str, Any], gcs_urls: dict[str, str] | None = None) -> None:
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


def upsert_traffic_counts(
    class_counts: dict[str, int],
    camera_source: str = "upload",
    hour_bucket: str | None = None,
) -> None:
    if not class_counts:
        return

    if hour_bucket is None:
        now = datetime.now(timezone.utc)
        hour_bucket = now.strftime("%Y-%m-%dT%H:00:00Z")

    sql = _adapt_sql("""
        INSERT INTO traffic_counts (hour_bucket, camera_source, class_name, count)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (hour_bucket, camera_source, class_name)
        DO UPDATE SET count = traffic_counts.count + EXCLUDED.count
    """)

    with get_conn() as conn:
        cur = conn.cursor()
        for class_name, count in class_counts.items():
            if count > 0:
                cur.execute(sql, (hour_bucket, camera_source, class_name, count))


def get_traffic_counts_by_hour(
    hours: int = 24,
    camera_source: str | None = None,
) -> list[dict[str, Any]]:
    from datetime import timedelta
    cutoff_str = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

    if camera_source:
        sql = _adapt_sql("""
            SELECT hour_bucket, camera_source, class_name, count
            FROM traffic_counts
            WHERE hour_bucket >= %s
              AND camera_source = %s
            ORDER BY hour_bucket DESC, class_name
        """)
        params: tuple = (cutoff_str, camera_source)
    else:
        sql = _adapt_sql("""
            SELECT hour_bucket, camera_source, class_name, count
            FROM traffic_counts
            WHERE hour_bucket >= %s
            ORDER BY hour_bucket DESC, class_name
        """)
        params = (cutoff_str,)

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        rows = cur.fetchall()

    return [_row_to_dict(row) for row in rows]


def get_class_distribution(hours: int = 24) -> dict[str, int]:
    rows = get_traffic_counts_by_hour(hours=hours)
    totals: dict[str, int] = {}
    for row in rows:
        cls = row.get("class_name", "")
        totals[cls] = totals.get(cls, 0) + int(row.get("count", 0))
    return totals


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
    else:
        deleted_val = "FALSE" if _backend == "postgres" else "0"
        sql = _adapt_sql(
            f"SELECT * FROM cloud_snapshots WHERE deleted={deleted_val} ORDER BY created_at DESC LIMIT %s"
        )

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql, (limit,))
        rows = cur.fetchall()
    return [_row_to_dict(row) for row in rows]


def list_expired_cloud_snapshots() -> list[dict[str, Any]]:
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
            cur.execute("SELECT id FROM alerts ORDER BY id DESC LIMIT 1")
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


def insert_incident(record: dict[str, Any]) -> None:
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
    from datetime import timedelta
    cutoff_str = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

    sql_total = _adapt_sql("SELECT COUNT(*) FROM incidents WHERE timestamp >= %s")
    sql_by_type = _adapt_sql("SELECT type, COUNT(*) FROM incidents WHERE timestamp >= %s GROUP BY type")
    sql_by_severity = _adapt_sql("SELECT severity, COUNT(*) FROM incidents WHERE timestamp >= %s GROUP BY severity")
    sql_by_state = _adapt_sql("SELECT state, COUNT(*) FROM incidents WHERE timestamp >= %s GROUP BY state")
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
    sql = _adapt_sql("""
        INSERT INTO incident_configs (camera_id, configs, updated_at, user_id)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (camera_id)
        DO UPDATE SET configs = EXCLUDED.configs, updated_at = EXCLUDED.updated_at, user_id = EXCLUDED.user_id
    """)
    params = (
        camera_id,
        json.dumps(configs),
        datetime.now(timezone.utc).isoformat(),
        user_id,
    )
    with get_conn() as conn:
        conn.cursor().execute(sql, params)


def get_incident_config(camera_id: str) -> dict[str, Any] | None:
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


def get_dashboard_stats(hours: int = 24) -> dict[str, Any]:
    total = count_detections()
    detect_count = count_detections(task="detect")
    convert_count = count_detections(task="convert")
    class_dist = get_class_distribution(hours=hours)
    unack_alerts = len(list_alerts(limit=100, unacknowledged_only=True))

    from datetime import timedelta
    cutoff_str = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    sql_avg = _adapt_sql(
        "SELECT AVG(inference_ms) FROM detections WHERE inference_ms IS NOT NULL AND task='detect' AND created_at >= %s"
    )
    params: tuple = (cutoff_str,)

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
    rows = get_traffic_counts_by_hour(hours=hours, camera_source=camera_source)

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


def insert_vehicle_speed(
    track_id: str,
    camera_source: str,
    class_name: str,
    speed_kmh: float,
    is_overspeed: bool | int,
    cx: float | None = None,
    cy: float | None = None,
    timestamp: str | None = None,
) -> None:
    sql = _adapt_sql("""
        INSERT INTO vehicle_speeds (track_id, camera_source, class_name, speed_kmh, is_overspeed, cx, cy, timestamp)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """)
    
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).isoformat()
    if isinstance(is_overspeed, bool):
        is_overspeed = 1 if is_overspeed else 0

    params = (track_id, camera_source, class_name, speed_kmh, is_overspeed, cx, cy, timestamp)
    with get_conn() as conn:
        conn.cursor().execute(sql, params)


def list_vehicle_speeds(limit: int = 100, overspeed_only: bool = False) -> list[dict[str, Any]]:
    if overspeed_only:
        overspeed_val = "TRUE" if _backend == "postgres" else "1"
        sql = _adapt_sql(
            f"SELECT * FROM vehicle_speeds WHERE is_overspeed={overspeed_val} ORDER BY timestamp DESC LIMIT %s"
        )
    else:
        sql = _adapt_sql("SELECT * FROM vehicle_speeds ORDER BY timestamp DESC LIMIT %s")

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql, (limit,))
        rows = cur.fetchall()
    return [_row_to_dict(row) for row in rows]


def insert_congestion_log(
    roi_name: str,
    camera_source: str,
    actual_count: int,
    capacity: int,
    congestion_ratio: float,
    state: str,
    timestamp: str | None = None,
) -> None:
    sql = _adapt_sql("""
        INSERT INTO congestion_logs (roi_name, camera_source, actual_count, capacity, congestion_ratio, state, timestamp)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """)
    
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).isoformat()

    params = (roi_name, camera_source, actual_count, capacity, congestion_ratio, state, timestamp)
    with get_conn() as conn:
        conn.cursor().execute(sql, params)


def list_congestion_logs(limit: int = 100, roi_name: str | None = None) -> list[dict[str, Any]]:
    if roi_name:
        sql = _adapt_sql(
            "SELECT * FROM congestion_logs WHERE roi_name=%s ORDER BY timestamp DESC LIMIT %s"
        )
        params: tuple = (roi_name, limit)
    else:
        sql = _adapt_sql("SELECT * FROM congestion_logs ORDER BY timestamp DESC LIMIT %s")
        params = (limit,)

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        rows = cur.fetchall()
    return [_row_to_dict(row) for row in rows]

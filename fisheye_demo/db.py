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
    conn = sqlite3.connect(_sqlite_path, timeout=30.0)
    # WAL: cho phép đọc/ghi đồng thời tốt hơn (job queue + camera monitor)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
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
    # timeout=30s tránh "database is locked" khi nhiều worker/thread ghi song song
    conn = sqlite3.connect(_sqlite_path, timeout=30.0)
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


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
        # incidents table — existing DB may use 'type' column, add missing cols
        ("incidents",  "vehicle_type",   "TEXT DEFAULT 'unknown'"),
        ("incidents",  "severity",       "TEXT DEFAULT 'medium'"),
        ("incidents",  "acknowledged",   "INTEGER DEFAULT 0"),
        ("incidents",  "evidence_path",  "TEXT DEFAULT ''"),
        ("incidents",  "incident_type",  "TEXT DEFAULT ''"),
        ("incidents",  "description",    "TEXT DEFAULT ''"),
        ("incidents",  "bbox_json",      "TEXT DEFAULT '[]'"),
        ("incidents",  "track_id",       "INTEGER DEFAULT 0"),
        ("incidents",  "occurred_at",    "TEXT DEFAULT (datetime('now'))"),
        # traffic_counts — add direction column if missing
        ("traffic_counts", "direction",  "TEXT DEFAULT 'unknown'"),
        ("traffic_counts", "camera_id",  "TEXT DEFAULT ''"),
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
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            camera_id     TEXT,
            incident_type TEXT,
            description   TEXT,
            bbox_json     TEXT,
            track_id      INTEGER,
            vehicle_type  TEXT DEFAULT 'unknown',
            severity      TEXT DEFAULT 'medium',
            acknowledged  INTEGER DEFAULT 0,
            evidence_path TEXT DEFAULT '',
            occurred_at   TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS traffic_counts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            camera_id   TEXT,
            direction   TEXT,
            class_name  TEXT,
            count       INTEGER DEFAULT 0,
            hour_bucket TEXT,
            created_at  TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS speed_violations (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            camera_id     TEXT,
            track_id      INTEGER,
            vehicle_type  TEXT,
            speed_kmh     REAL,
            limit_kmh     REAL,
            evidence_path TEXT DEFAULT '',
            created_at    TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS license_plates (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            plate_text   TEXT,
            confidence   REAL,
            vehicle_type TEXT DEFAULT 'unknown',
            camera_id    TEXT DEFAULT '',
            detection_id TEXT DEFAULT '',
            bbox_json    TEXT DEFAULT '[]',
            created_at   TEXT DEFAULT (datetime('now'))
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
            vehicle_type  VARCHAR(64) DEFAULT 'unknown',
            severity      VARCHAR(32) DEFAULT 'medium',
            acknowledged  BOOLEAN DEFAULT FALSE,
            evidence_path TEXT DEFAULT '',
            occurred_at   TIMESTAMP DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS traffic_counts (
            id          SERIAL PRIMARY KEY,
            camera_id   VARCHAR(128),
            direction   VARCHAR(32) DEFAULT 'unknown',
            class_name  VARCHAR(64),
            count       INTEGER DEFAULT 0,
            hour_bucket VARCHAR(32),
            created_at  TIMESTAMP DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS speed_violations (
            id            SERIAL PRIMARY KEY,
            camera_id     VARCHAR(128),
            track_id      INTEGER,
            vehicle_type  VARCHAR(64),
            speed_kmh     FLOAT,
            limit_kmh     FLOAT,
            evidence_path TEXT DEFAULT '',
            created_at    TIMESTAMP DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS license_plates (
            id           SERIAL PRIMARY KEY,
            plate_text   VARCHAR(32),
            confidence   FLOAT,
            vehicle_type VARCHAR(64) DEFAULT 'unknown',
            camera_id    VARCHAR(128) DEFAULT '',
            detection_id VARCHAR(64) DEFAULT '',
            bbox_json    TEXT DEFAULT '[]',
            created_at   TIMESTAMP DEFAULT NOW()
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
        """SELECT id, filename, task, media_type, source_layout,
                  preprocessing, summary, artifacts, gcs_urls, created_at
           FROM detections WHERE id = %s""",
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
        """INSERT INTO alerts (alert_type, message, camera_source, actual_count, created_at)
           VALUES (%s, %s, %s, %s, datetime('now'))
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


# ── Additional helper functions ───────────────────────────────

def health_check() -> dict:
    """Kiểm tra kết nối DB. Trả về {"status": "ok"} nếu thành công."""
    try:
        _execute("SELECT 1", fetch="one")
        return {"status": "ok"}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def list_alerts(limit: int = 50, unacknowledged_only: bool = False) -> list[dict]:
    """Lấy danh sách alerts với filter tuỳ chọn."""
    if unacknowledged_only:
        rows = _execute(
            """SELECT id, alert_type, message, camera_source, actual_count,
                      is_acknowledged, created_at
               FROM alerts WHERE is_acknowledged = 0
               ORDER BY created_at DESC LIMIT %s
            """,
            (limit,),
            fetch="all",
        )
    else:
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


def acknowledge_alert(alert_id: int) -> None:
    """Đánh dấu alert đã được xử lý."""
    _execute(
        "UPDATE alerts SET is_acknowledged = 1 WHERE id = %s",
        (alert_id,),
    )


def list_cloud_snapshots(limit: int = 50, include_deleted: bool = False) -> list[dict]:
    """Lấy danh sách cloud snapshots. Trả list rỗng nếu bảng chưa tồn tại."""
    try:
        rows = _execute(
            """SELECT id, filename, gcs_url, created_at
               FROM cloud_snapshots ORDER BY created_at DESC LIMIT %s
            """,
            (limit,),
            fetch="all",
        )
        if not rows:
            return []
        cols = ["id", "filename", "gcs_url", "created_at"]
        return [dict(zip(cols, row)) for row in rows]
    except Exception:
        return []


def list_detections(limit: int = 50, offset: int = 0, task: str = None) -> list[dict]:
    """Lấy danh sách detections với filter theo task."""
    if task:
        rows = _execute(
            """SELECT id, filename, task, media_type, source_layout,
                      summary, artifacts, created_at
               FROM detections WHERE task = %s
               ORDER BY created_at DESC LIMIT %s OFFSET %s
            """,
            (task, limit, offset),
            fetch="all",
        )
    else:
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
        for field in ("summary", "artifacts"):
            try:
                d[field] = json.loads(d[field] or "{}")
            except (json.JSONDecodeError, TypeError):
                d[field] = {}
        result.append(d)
    return result


def count_detections(task: str = None) -> int:
    """Đếm tổng số detections."""
    if task:
        row = _execute(
            "SELECT COUNT(*) FROM detections WHERE task = %s",
            (task,),
            fetch="one",
        )
    else:
        row = _execute("SELECT COUNT(*) FROM detections", fetch="one")
    return row[0] if row else 0


def get_detection(detection_id: str) -> dict | None:
    """Alias cho get_detection_by_id."""
    return get_detection_by_id(detection_id)


def list_live_sessions(limit: int = 20) -> list[dict]:
    """Lấy danh sách live sessions. Trả list rỗng nếu bảng chưa tồn tại."""
    try:
        rows = _execute(
            """SELECT id, camera_source, started_at, ended_at, frame_count
               FROM live_sessions ORDER BY started_at DESC LIMIT %s
            """,
            (limit,),
            fetch="all",
        )
        if not rows:
            return []
        cols = ["id", "camera_source", "started_at", "ended_at", "frame_count"]
        return [dict(zip(cols, row)) for row in rows]
    except Exception:
        return []


def get_hourly_traffic_chart(hours: int = 24, camera_source: str = None) -> list[dict]:
    """
    Trả về thống kê traffic theo từng giờ cho biểu đồ.

    Returns
    -------
    list[{"hour": "YYYY-MM-DD HH:00", "counts": {class: N}}]
    """
    try:
        if camera_source:
            rows = _execute(
                """SELECT strftime('%Y-%m-%d %H:00', created_at) as hour,
                          summary
                   FROM detections
                   WHERE created_at >= datetime('now', %s)
                     AND source_layout = %s
                   ORDER BY hour
                """,
                (f"-{hours} hours", camera_source),
                fetch="all",
            ) or []
        else:
            rows = _execute(
                """SELECT strftime('%Y-%m-%d %H:00', created_at) as hour,
                          summary
                   FROM detections
                   WHERE created_at >= datetime('now', %s)
                   ORDER BY hour
                """,
                (f"-{hours} hours",),
                fetch="all",
            ) or []

        # Aggregate counts per hour
        from collections import defaultdict
        hourly: dict[str, dict] = defaultdict(lambda: defaultdict(int))
        for row in rows:
            hour = row[0] or "unknown"
            try:
                summary = json.loads(row[1] or "{}")
                counts = summary.get("counts", {})
                for cls, cnt in counts.items():
                    hourly[hour][cls] += cnt
            except Exception:
                pass

        return [
            {"hour": h, "counts": dict(c)}
            for h, c in sorted(hourly.items())
        ]
    except Exception as exc:
        logger.warning("get_hourly_traffic_chart error: %s", exc)
        return []


# ── Incidents ────────────────────────────────────────────────────────────────

def _get_incident_columns() -> list:
    """Detect thực tế tên cột trong bảng incidents."""
    try:
        rows = _execute("PRAGMA table_info(incidents)", fetch="all") or []
        return [row[1] for row in rows]
    except Exception:
        return []


def save_incident(incident: dict) -> int:
    """Lưu sự cố giao thông vào DB. Returns id."""
    cols = _get_incident_columns()
    time_col = "occurred_at" if "occurred_at" in cols else "timestamp"

    inc_type = incident.get("incident_type", "UNKNOWN")
    desc = incident.get("description", "")
    bbox_str = json.dumps(incident.get("bbox", []))
    track_id = incident.get("track_id", 0)
    cam_id = incident.get("camera_id", "default")
    vtype = incident.get("vehicle_type", "unknown")
    sev = incident.get("severity", "medium")
    ev_path = incident.get("evidence_path", "")
    now = datetime.utcnow().isoformat()

    # Always write to NOT NULL columns that may exist in old schema
    insert_cols = ["camera_id", "vehicle_type", "severity", time_col]
    insert_vals: list = [cam_id, vtype, sev, now]

    # 'type' column (old schema, NOT NULL)
    if "type" in cols:
        insert_cols.append("type")
        insert_vals.append(inc_type)
    # 'incident_type' column (new, nullable)
    if "incident_type" in cols:
        insert_cols.append("incident_type")
        insert_vals.append(inc_type)
    # Other NOT NULL columns from old schema with safe defaults
    if "confidence" in cols:
        insert_cols.append("confidence")
        insert_vals.append(0.0)
    if "state" in cols:
        insert_cols.append("state")
        insert_vals.append("active")
    # Optional new columns
    if "description" in cols:
        insert_cols.append("description")
        insert_vals.append(desc)
    if "bbox_json" in cols:
        insert_cols.append("bbox_json")
        insert_vals.append(bbox_str)
    if "track_id" in cols:
        insert_cols.append("track_id")
        insert_vals.append(track_id)
    if "evidence_path" in cols:
        insert_cols.append("evidence_path")
        insert_vals.append(ev_path)
    if "acknowledged" in cols:
        insert_cols.append("acknowledged")
        insert_vals.append(0)

    placeholders = ", ".join(["%s"] * len(insert_cols))
    col_str = ", ".join(insert_cols)
    _execute(
        f"INSERT INTO incidents ({col_str}) VALUES ({placeholders})",
        tuple(insert_vals),
    )
    row = _execute("SELECT last_insert_rowid()", fetch="one")
    return row[0] if row else -1


def get_incidents(hours: int = 24, acknowledged: bool = None,
                  incident_type: str = None) -> list[dict]:
    """Lấy danh sách sự cố."""
    cols = _get_incident_columns()
    type_col = "incident_type" if "incident_type" in cols else "type"
    time_col = "occurred_at" if "occurred_at" in cols else "timestamp"

    filters = [f"{time_col} >= datetime('now', %s)"]
    params: list = [f"-{hours} hours"]
    if acknowledged is not None:
        filters.append("acknowledged = %s")
        params.append(1 if acknowledged else 0)
    if incident_type:
        filters.append(f"{type_col} = %s")
        params.append(incident_type)
    where = " AND ".join(filters)

    # Select available columns
    sel_cols = ["id", "camera_id", type_col, "vehicle_type", "severity", "acknowledged", time_col]
    if "description" in cols:
        sel_cols.append("description")
    if "bbox_json" in cols:
        sel_cols.append("bbox_json")
    if "track_id" in cols:
        sel_cols.append("track_id")

    sel_str = ", ".join(sel_cols)
    rows = _execute(
        f"SELECT {sel_str} FROM incidents WHERE {where} ORDER BY {time_col} DESC LIMIT 200",
        tuple(params),
        fetch="all",
    ) or []

    result = []
    for row in rows:
        d = dict(zip(sel_cols, row))
        # Normalize column names
        if type_col != "incident_type":
            d["incident_type"] = d.pop(type_col, "")
        if time_col != "occurred_at":
            d["occurred_at"] = d.pop(time_col, "")
        # Parse bbox_json
        bbox_raw = d.pop("bbox_json", "[]")
        try:
            d["bbox"] = json.loads(bbox_raw or "[]")
        except Exception:
            d["bbox"] = []
        result.append(d)
    return result


def acknowledge_incident(incident_id: int) -> None:
    _execute(
        "UPDATE incidents SET acknowledged = 1 WHERE id = %s",
        (incident_id,),
    )


def count_incidents(hours: int = 24, acknowledged: bool = None) -> dict:
    """Đếm incidents theo loại trong khoảng hours gần nhất."""
    cols = _get_incident_columns()
    type_col = "incident_type" if "incident_type" in cols else "type"
    time_col = "occurred_at" if "occurred_at" in cols else "timestamp"

    params = [f"-{hours} hours"]
    extra = ""
    if acknowledged is not None:
        extra = "AND acknowledged = %s"
        params.append(1 if acknowledged else 0)
    rows = _execute(
        f"""SELECT {type_col}, COUNT(*) as cnt
            FROM incidents
            WHERE {time_col} >= datetime('now', %s) {extra}
            GROUP BY {type_col}
        """,
        tuple(params),
        fetch="all",
    ) or []
    return {row[0]: row[1] for row in rows}


# ── Traffic Counts (line counter) ─────────────────────────────────────────────

def _get_traffic_count_columns() -> list:
    try:
        rows = _execute("PRAGMA table_info(traffic_counts)", fetch="all") or []
        return [row[1] for row in rows]
    except Exception:
        return []


def save_traffic_count(camera_id: str, direction: str,
                        class_name: str, hour_bucket: str, count: int = 1) -> None:
    """Upsert traffic count cho (camera, direction, class, hour)."""
    tc_cols = _get_traffic_count_columns()
    has_direction = "direction" in tc_cols
    has_camera_id = "camera_id" in tc_cols
    cam_col = "camera_id" if has_camera_id else "camera_source"

    if has_direction:
        existing = _execute(
            f"""SELECT id FROM traffic_counts
               WHERE {cam_col} = %s AND direction = %s AND class_name = %s AND hour_bucket = %s
            """,
            (camera_id, direction, class_name, hour_bucket),
            fetch="one",
        )
        if existing:
            _execute("UPDATE traffic_counts SET count = count + %s WHERE id = %s",
                     (count, existing[0]))
        else:
            _execute(
                f"INSERT INTO traffic_counts ({cam_col}, direction, class_name, hour_bucket, count) VALUES (%s, %s, %s, %s, %s)",
                (camera_id, direction, class_name, hour_bucket, count),
            )
    else:
        # Old schema without direction
        existing = _execute(
            f"SELECT id FROM traffic_counts WHERE {cam_col} = %s AND class_name = %s AND hour_bucket = %s",
            (camera_id, class_name, hour_bucket),
            fetch="one",
        )
        if existing:
            _execute("UPDATE traffic_counts SET count = count + %s WHERE id = %s",
                     (count, existing[0]))
        else:
            _execute(
                f"INSERT INTO traffic_counts ({cam_col}, class_name, hour_bucket, count) VALUES (%s, %s, %s, %s)",
                (camera_id, class_name, hour_bucket, count),
            )


def get_traffic_counts(hours: int = 24, camera_id: str = None) -> list[dict]:
    """Lấy traffic counts theo giờ."""
    tc_cols = _get_traffic_count_columns()
    has_direction = "direction" in tc_cols
    cam_col = "camera_id" if "camera_id" in tc_cols else "camera_source"
    has_created = "created_at" in tc_cols

    if has_created:
        time_filter = f"WHERE created_at >= datetime('now', %s)"
        params = [f"-{hours} hours"]
    else:
        time_filter = "WHERE 1=1"
        params = []

    cam_filter = ""
    if camera_id:
        cam_filter = f"AND {cam_col} = %s"
        params.append(camera_id)

    if has_direction:
        rows = _execute(
            f"""SELECT {cam_col}, direction, class_name, hour_bucket, SUM(count) as total
                FROM traffic_counts {time_filter} {cam_filter}
                GROUP BY {cam_col}, direction, class_name, hour_bucket
                ORDER BY hour_bucket
            """,
            tuple(params),
            fetch="all",
        ) or []
        return [{"camera_id": r[0], "direction": r[1], "class_name": r[2],
                 "hour_bucket": r[3], "count": r[4]} for r in rows]
    else:
        rows = _execute(
            f"""SELECT {cam_col}, class_name, hour_bucket, SUM(count) as total
                FROM traffic_counts {time_filter} {cam_filter}
                GROUP BY {cam_col}, class_name, hour_bucket
                ORDER BY hour_bucket
            """,
            tuple(params),
            fetch="all",
        ) or []
        return [{"camera_id": r[0], "direction": "unknown", "class_name": r[1],
                 "hour_bucket": r[2], "count": r[3]} for r in rows]


def get_traffic_by_direction(hours: int = 24, camera_id: str = None) -> dict:
    """Tổng hợp traffic theo direction."""
    rows = get_traffic_counts(hours=hours, camera_id=camera_id)
    result: dict = {}
    for row in rows:
        d = row.get("direction", "unknown")
        if d not in result:
            result[d] = {}
        cls = row["class_name"]
        result[d][cls] = result[d].get(cls, 0) + row["count"]
    for d in result:
        result[d]["total"] = sum(v for k, v in result[d].items() if k != "total")
    return result


# ── Speed Violations ──────────────────────────────────────────────────────────

def save_speed_violation(camera_id: str, track_id: int, vehicle_type: str,
                          speed_kmh: float, limit_kmh: float,
                          evidence_path: str = "") -> None:
    _execute(
        """INSERT INTO speed_violations
           (camera_id, track_id, vehicle_type, speed_kmh, limit_kmh, evidence_path)
           VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (camera_id, track_id, vehicle_type, speed_kmh, limit_kmh, evidence_path),
    )


def get_speed_violations(hours: int = 24, camera_id: str = None) -> list[dict]:
    params = [f"-{hours} hours"]
    extra = ""
    if camera_id:
        extra = "AND camera_id = %s"
        params.append(camera_id)
    rows = _execute(
        f"""SELECT id, camera_id, track_id, vehicle_type, speed_kmh, limit_kmh,
                   evidence_path, created_at
            FROM speed_violations
            WHERE created_at >= datetime('now', %s) {extra}
            ORDER BY created_at DESC LIMIT 200
        """,
        tuple(params),
        fetch="all",
    ) or []
    cols = ["id", "camera_id", "track_id", "vehicle_type", "speed_kmh",
            "limit_kmh", "evidence_path", "created_at"]
    return [dict(zip(cols, row)) for row in rows]


def count_speed_violations(hours: int = 24) -> int:
    row = _execute(
        "SELECT COUNT(*) FROM speed_violations WHERE created_at >= datetime('now', %s)",
        (f"-{hours} hours",),
        fetch="one",
    )
    return row[0] if row else 0


# ── License Plates (ALPR) ─────────────────────────────────────────────────────

def save_license_plate(plate_text: str, confidence: float,
                       vehicle_type: str = "unknown", camera_id: str = "",
                       detection_id: str = "", bbox: list = None) -> int:
    """Lưu một biển số nhận diện được. Trả id."""
    _execute(
        """INSERT INTO license_plates
           (plate_text, confidence, vehicle_type, camera_id, detection_id, bbox_json)
           VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (plate_text, float(confidence), vehicle_type, camera_id,
         detection_id, json.dumps(bbox or [])),
    )
    row = _execute("SELECT last_insert_rowid()", fetch="one")
    return row[0] if row else -1


def get_license_plates(hours: int = 24, query: str = None,
                       limit: int = 200) -> list[dict]:
    """Lấy danh sách biển số gần nhất, lọc theo chuỗi (LIKE) nếu có query."""
    filters = ["created_at >= datetime('now', %s)"]
    params: list = [f"-{hours} hours"]
    if query:
        filters.append("UPPER(plate_text) LIKE %s")
        params.append(f"%{query.upper()}%")
    where = " AND ".join(filters)
    rows = _execute(
        f"""SELECT id, plate_text, confidence, vehicle_type, camera_id,
                   detection_id, bbox_json, created_at
            FROM license_plates WHERE {where}
            ORDER BY created_at DESC LIMIT %s
        """,
        tuple(params + [limit]),
        fetch="all",
    ) or []
    cols = ["id", "plate_text", "confidence", "vehicle_type", "camera_id",
            "detection_id", "bbox_json", "created_at"]
    result = []
    for row in rows:
        d = dict(zip(cols, row))
        try:
            d["bbox"] = json.loads(d.pop("bbox_json") or "[]")
        except Exception:
            d["bbox"] = []
        result.append(d)
    return result


def count_license_plates(hours: int = 24) -> int:
    row = _execute(
        "SELECT COUNT(*) FROM license_plates WHERE created_at >= datetime('now', %s)",
        (f"-{hours} hours",),
        fetch="one",
    )
    return row[0] if row else 0


def get_class_distribution(hours: int = 24) -> dict:
    """
    Trả về tổng số lượng theo từng class trong khoảng hours gần nhất.
    """
    try:
        rows = _execute(
            """SELECT summary FROM detections
               WHERE created_at >= datetime('now', %s)
            """,
            (f"-{hours} hours",),
            fetch="all",
        ) or []

        from collections import defaultdict
        totals: dict = defaultdict(int)
        for row in rows:
            try:
                summary = json.loads(row[0] or "{}")
                counts = summary.get("counts", {})
                for cls, cnt in counts.items():
                    totals[cls] += cnt
            except Exception:
                pass
        return dict(totals)
    except Exception as exc:
        logger.warning("get_class_distribution error: %s", exc)
        return {}

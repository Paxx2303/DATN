-- postgres_schema.sql
-- Database schema for Graduation Thesis (DATN) Fisheye Traffic Monitoring System

-- 1. Table detections — Stores metadata of every image, video, or camera run
CREATE TABLE IF NOT EXISTS detections (
    id              VARCHAR(64) PRIMARY KEY,
    task            VARCHAR(32) NOT NULL,
    media_type      VARCHAR(16) NOT NULL,
    filename        VARCHAR(256),
    source_layout   VARCHAR(16),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    conf_threshold  REAL,
    iou_threshold   REAL,
    total_objects   INTEGER DEFAULT 0,
    inference_ms    REAL,
    class_counts    JSONB,
    model_name      VARCHAR(64),
    device          VARCHAR(16),
    preprocessing   JSONB,
    artifacts       JSONB,
    gcs_urls        JSONB
);

CREATE INDEX IF NOT EXISTS idx_detections_created_at ON detections(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_detections_task ON detections(task);
CREATE INDEX IF NOT EXISTS idx_detections_media_type ON detections(media_type);

-- 2. Table live_sessions — Stores stats for active or historical camera live streaming sessions
CREATE TABLE IF NOT EXISTS live_sessions (
    id              VARCHAR(64) PRIMARY KEY,
    source_url      TEXT,
    source_mode     VARCHAR(16),
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at        TIMESTAMPTZ,
    cycle_count     INTEGER DEFAULT 0,
    total_objects   INTEGER DEFAULT 0,
    class_counts    JSONB,
    conf_threshold  REAL,
    iou_threshold   REAL,
    status          VARCHAR(16) DEFAULT 'active'
);

CREATE INDEX IF NOT EXISTS idx_live_sessions_started_at ON live_sessions(started_at DESC);

-- 3. Table traffic_counts — Aggregates class counts per hour bucket per camera
CREATE TABLE IF NOT EXISTS traffic_counts (
    id              BIGSERIAL PRIMARY KEY,
    hour_bucket     TIMESTAMPTZ NOT NULL,
    camera_source   VARCHAR(128) NOT NULL DEFAULT 'upload',
    class_name      VARCHAR(32) NOT NULL,
    count           INTEGER NOT NULL DEFAULT 0,
    UNIQUE(hour_bucket, camera_source, class_name)
);

CREATE INDEX IF NOT EXISTS idx_traffic_counts_hour ON traffic_counts(hour_bucket DESC);
CREATE INDEX IF NOT EXISTS idx_traffic_counts_source ON traffic_counts(camera_source);

-- 4. Table cloud_snapshots — Tracks GCS-hosted images and their retention policies
CREATE TABLE IF NOT EXISTS cloud_snapshots (
    id              BIGSERIAL PRIMARY KEY,
    detection_id    VARCHAR(64) REFERENCES detections(id) ON DELETE CASCADE,
    gcs_bucket      VARCHAR(128) NOT NULL,
    gcs_object_name VARCHAR(512) NOT NULL UNIQUE,
    gcs_public_url  TEXT,
    image_role      VARCHAR(32),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ,
    deleted         BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_cloud_snapshots_created_at ON cloud_snapshots(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_cloud_snapshots_expires_at ON cloud_snapshots(expires_at);
CREATE INDEX IF NOT EXISTS idx_cloud_snapshots_deleted ON cloud_snapshots(deleted);

-- 5. Table alerts — Records active and past warning events
CREATE TABLE IF NOT EXISTS alerts (
    id              BIGSERIAL PRIMARY KEY,
    alert_type      VARCHAR(32) NOT NULL,
    camera_source   VARCHAR(128),
    class_name      VARCHAR(32),
    threshold       INTEGER,
    actual_count    INTEGER,
    message         TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    acknowledged    BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_alerts_created_at ON alerts(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_acknowledged ON alerts(acknowledged);

-- 6. Table incidents — Log of special events like wrong way, speed violation, stalling
CREATE TABLE IF NOT EXISTS incidents (
    id              VARCHAR(64) PRIMARY KEY,
    type            VARCHAR(32) NOT NULL,
    severity        VARCHAR(16) NOT NULL,
    confidence      REAL NOT NULL,
    camera_id       VARCHAR(128) NOT NULL,
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    location        JSONB,
    state           VARCHAR(16) NOT NULL DEFAULT 'active',
    duration        REAL DEFAULT 0.0,
    metadata        JSONB,
    video_url       TEXT,
    thumbnail_url   TEXT
);

CREATE INDEX IF NOT EXISTS idx_incidents_timestamp ON incidents(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_incidents_camera_id ON incidents(camera_id);
CREATE INDEX IF NOT EXISTS idx_incidents_type ON incidents(type);
CREATE INDEX IF NOT EXISTS idx_incidents_severity ON incidents(severity);

-- 7. Table incident_configs — Configuration for incident triggers per camera
CREATE TABLE IF NOT EXISTS incident_configs (
    camera_id       VARCHAR(128) NOT NULL DEFAULT 'default',
    configs         JSONB NOT NULL,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    user_id         VARCHAR(64),
    PRIMARY KEY (camera_id)
);

-- 8. Table vehicle_speeds — Continuous logging of tracked vehicle speed records
CREATE TABLE IF NOT EXISTS vehicle_speeds (
    id              BIGSERIAL PRIMARY KEY,
    track_id        VARCHAR(64) NOT NULL,
    camera_source   VARCHAR(128) NOT NULL,
    class_name      VARCHAR(32) NOT NULL,
    speed_kmh       REAL NOT NULL,
    is_overspeed    BOOLEAN DEFAULT FALSE,
    cx              REAL,
    cy              REAL,
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_vehicle_speeds_timestamp ON vehicle_speeds(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_vehicle_speeds_overspeed ON vehicle_speeds(is_overspeed);

-- 9. Table congestion_logs — Records regional density statistics over time
CREATE TABLE IF NOT EXISTS congestion_logs (
    id              BIGSERIAL PRIMARY KEY,
    roi_name        VARCHAR(64) NOT NULL,
    camera_source   VARCHAR(128) NOT NULL,
    actual_count    INTEGER NOT NULL,
    capacity        INTEGER NOT NULL,
    congestion_ratio REAL NOT NULL,
    state           VARCHAR(16) NOT NULL,
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_congestion_logs_timestamp ON congestion_logs(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_congestion_logs_roi ON congestion_logs(roi_name);

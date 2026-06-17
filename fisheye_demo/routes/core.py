"""
routes/core.py — Core Routes Blueprint

Endpoints:
  GET  /                     → Render SPA (index.html)
  GET  /api/health           → System health check
  GET  /api/logs             → Tail system logs (cho UI log terminal)
  GET  /api/config           → Config hiển thị (models available, device, etc.)
  GET  /api/analytics/stats  → Traffic statistics hiện tại
"""

import logging
from flask import Blueprint, render_template, jsonify, current_app
from services.model_registry import get_available_models
from analytics import heatmap, density_analyzer
from config import Config
import db as database

logger = logging.getLogger(__name__)

# Log buffer để UI có thể poll
_log_buffer: list[dict] = []
_MAX_LOG_BUFFER = 200

core_bp = Blueprint("core", __name__)


class UILogHandler(logging.Handler):
    """
    Custom logging handler: append log records vào _log_buffer.
    UI polling /api/logs để hiển thị real-time logs.
    """
    def emit(self, record: logging.LogRecord) -> None:
        from datetime import datetime
        _log_buffer.append({
            "level":     record.levelname,
            "message":   record.getMessage(),
            "time":      record.created,
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "module":    record.module,
            "logger":    record.name,
        })
        # Trim buffer
        if len(_log_buffer) > _MAX_LOG_BUFFER:
            _log_buffer.pop(0)


def register_ui_log_handler() -> None:
    """Đăng ký UILogHandler vào root logger. Gọi từ create_app()."""
    handler = UILogHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logging.getLogger().addHandler(handler)


@core_bp.route("/")
def index():
    """Serve SPA with all required template variables."""
    from services.model_registry import get_available_models
    models = get_available_models()
    selectable_models = [
        {"key": k, "name": f"YOLO {k.capitalize()}"}
        for k, v in models.items() if v["exists"]
    ]
    
    class_names = list(Config.VEHICLE_NAME_MAP.values())
    class_colors = {
        "Car": "#00e676",
        "Truck": "#ff9100",
        "Bus": "#00b0ff",
        "Motorbike": "#d500f9",
        "Pedestrian": "#ffd600",
        "Bicycle": "#00e5ff",
    }
    fisheye_effect_choices = [
        ("standard", "Chuẩn (Standard)"),
        ("extreme", "Mạnh (Extreme)"),
        ("subtle", "Nhẹ (Subtle)")
    ]
    
    return render_template(
        "index.html",
        class_names=class_names,
        class_colors=class_colors,
        default_conf=Config.DEFAULT_CONF,
        default_iou=Config.DEFAULT_IOU,
        default_fisheye_strength=Config.FISHEYE_STRENGTH,
        default_fisheye_radius=Config.FISHEYE_RADIUS,
        default_fisheye_effect=Config.FISHEYE_EFFECT,
        fisheye_effect_choices=fisheye_effect_choices,
        selectable_models=selectable_models,
        default_model_key=Config.DEFAULT_MODEL_KEY,
        external_camera_url="https://camera.0511.vn/camera.html",
        external_camera_live_interval_seconds=Config.EXT_CAM_INTERVAL,
    )


@core_bp.route("/api/health")
def health():
    """
    Health check endpoint.
    Returns: status, db_type, models available, current config.
    """
    models = get_available_models()
    active_key = Config.DEFAULT_MODEL_KEY
    active_model = models.get(active_key, {})
    # Trạng thái GPU thực tế (để chẩn đoán "GPU chậm" = có đang chạy CPU không)
    gpu_info = {"available": False, "name": None}
    try:
        import torch
        if torch.cuda.is_available():
            gpu_info = {"available": True, "name": torch.cuda.get_device_name(0)}
    except Exception:
        pass

    return jsonify({
        "status":  "ok",
        "db_type": database._DB_TYPE,
        "models":  models,
        "device":  Config.DEFAULT_DEVICE,
        "gpu":     gpu_info,
        "version": "1.0.0",
        "model": {
            "loaded_from_name": f"YOLO {active_key.capitalize()}",
            "loaded_from":      active_model.get("path", ""),
            "source":           active_key,
            "device":           Config.DEFAULT_DEVICE,
            "loaded":           active_model.get("loaded", False),
            "candidate":        active_model.get("path", ""),
        },
        "storage": {
            "results_dir": str(Config.RESULTS_FOLDER),
            "upload_dir":  str(Config.UPLOAD_FOLDER),
        },
    })


@core_bp.route("/api/logs")
def get_logs():
    """
    Trả về log buffer hiện tại với hỗ trợ lọc theo level, keyword, limit.
    UI polling endpoint mỗi 2 giây.
    """
    from flask import request
    since_idx    = int(request.args.get("since", 0))
    level_filter = request.args.get("level", "").strip().upper()
    q_filter     = request.args.get("q", "").strip().lower()
    limit        = min(int(request.args.get("limit", 100)), 500)

    logs = list(_log_buffer[since_idx:])

    if level_filter:
        logs = [l for l in logs if l.get("level") == level_filter]
    if q_filter:
        logs = [l for l in logs if q_filter in l.get("message", "").lower()]

    # Return last `limit` matching entries
    logs = logs[-limit:]

    return jsonify({
        "logs":  logs,
        "total": len(_log_buffer),
        "from":  since_idx,
    })


@core_bp.route("/api/config")
def get_config():
    """Config hiển thị trên UI — không expose secrets."""
    models = get_available_models()
    return jsonify({
        "default_model":    Config.DEFAULT_MODEL_KEY,
        "available_models": {
            k: {"exists": v["exists"], "loaded": v["loaded"]}
            for k, v in models.items()
        },
        "default_device":   Config.DEFAULT_DEVICE,
        "fisheye_defaults": {
            "strength": Config.FISHEYE_STRENGTH,
            "radius":   Config.FISHEYE_RADIUS,
            "effect":   Config.FISHEYE_EFFECT,
        },
        "alert_threshold":  Config.ALERT_HIGH_DENSITY,
        "job_max_workers":  Config.JOB_MAX_WORKERS,
        "vehicle_classes":  list(Config.VEHICLE_CLASSES),
    })


@core_bp.route("/api/stats")
@core_bp.route("/api/analytics/stats")
def analytics_stats():
    """Traffic analytics statistics cho Dashboard."""
    try:
        detections = database.get_detections(limit=1000)
    except Exception:
        detections = []

    total_runs    = len(detections)
    total_detect  = sum(1 for d in detections if d.get("task") == "detect")
    total_convert = sum(1 for d in detections if d.get("task") == "convert")

    class_totals: dict = {}
    inference_times: list = []
    for d in detections:
        summary = d.get("summary") or {}
        counts  = summary.get("counts") or {}
        for cls, cnt in counts.items():
            class_totals[cls] = class_totals.get(cls, 0) + cnt
        dur = summary.get("duration_s")
        if dur:
            inference_times.append(dur * 1000)

    avg_inference_ms = int(sum(inference_times) / len(inference_times)) if inference_times else 0

    try:
        recent_alerts = database.get_recent_alerts(limit=10)
    except Exception:
        recent_alerts = []

    return jsonify({
        "total_runs":       total_runs,
        "total_detect":     total_detect,
        "total_convert":    total_convert,
        "avg_inference_ms": avg_inference_ms,
        "class_totals":     class_totals,
        "density":          density_analyzer.get_stats(),
        "recent_alerts":    recent_alerts,
        "heatmap_ready":    heatmap._total_updates > 0,
    })

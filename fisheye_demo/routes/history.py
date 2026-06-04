"""
routes/history.py — History & Results API

Endpoints:
  GET /api/history                    → Danh sách kết quả gần nhất
  GET /api/results/<result_id>        → Chi tiết một kết quả
  GET /api/results/<result_id>/file/<filename>  → Serve file artifact
  GET /api/recent-images              → Buffer ảnh kết quả nhanh
  GET /api/alerts                     → Danh sách cảnh báo
"""

import logging
from flask import Blueprint, jsonify, send_file, abort, request
from config import Config
import db as database
import recent_image_store

logger = logging.getLogger(__name__)
history_bp = Blueprint("history", __name__, url_prefix="/api")


def inject_artifact_urls(record: dict) -> dict:
    """Injects artifact_urls into a detection record based on its artifacts dictionary."""
    if not record:
        return record
    
    result_id = record["id"]
    artifacts = record.get("artifacts", {}) or {}
    
    artifact_urls = {}
    for key, filename in artifacts.items():
        artifact_urls[key] = f"/api/results/{result_id}/file/{filename}"
    
    # Also add metadata json URL
    artifact_urls["metadata"] = f"/api/results/{result_id}/file/meta.json"
    
    # Let's ensure specialized keys are set to satisfy SPA expectations:
    if record.get("media_type") == "video":
        if "annotated" in artifacts:
            artifact_urls["annotated_video"] = f"/api/results/{result_id}/file/{artifacts['annotated']}"
            artifact_urls["fisheye_video"] = f"/api/results/{result_id}/file/{artifacts['annotated']}"
        if "preview" in artifacts:
            artifact_urls["preview_annotated"] = f"/api/results/{result_id}/file/{artifacts['preview']}"
    
    record["artifact_urls"] = artifact_urls
    return record


@history_bp.route("/history")
def get_history():
    """Danh sách kết quả nhận diện, phân trang."""
    limit  = int(request.args.get("limit", 20))
    offset = int(request.args.get("offset", 0))

    try:
        detections = database.get_detections(limit=limit, offset=offset)
    except Exception as e:
        logger.warning(f"Failed to load history: {e}")
        detections = []

    for d in detections:
        inject_artifact_urls(d)

    return jsonify({
        "detections": detections,
        "items":      detections,   # alias — frontend uses data.items
        "limit":      limit,
        "offset":     offset,
        "total":      len(detections),
    })


@history_bp.route("/results/<result_id>")
def get_result_detail(result_id: str):
    """Chi tiết đầy đủ của một phiên nhận diện."""
    # Validate result_id (chỉ cho phép hex chars)
    if not all(c in "0123456789abcdef" for c in result_id):
        return jsonify({"error": "Invalid result_id"}), 400
    
    record = database.get_detection_by_id(result_id)
    if record is None:
        return jsonify({"error": "Result not found"}), 404
        
    inject_artifact_urls(record)
    
    # Kiểm tra files tồn tại
    result_dir = Config.RESULTS_FOLDER / result_id
    artifacts = record.get("artifacts", {})
    available_files = {}
    for key, filename in artifacts.items():
        file_path = result_dir / filename
        available_files[key] = {
            "filename":  filename,
            "exists":    file_path.exists(),
            "url":       f"/api/results/{result_id}/file/{filename}",
        }
    
    return jsonify({
        **record,
        "available_files": available_files,
    })


@history_bp.route("/results/<result_id>/file/<path:filename>")
def serve_result_file(result_id: str, filename: str):
    """Serve file artifact (video, image, JSON) từ thư mục result."""
    # Security: chặn path traversal
    if ".." in filename or filename.startswith("/"):
        abort(403)
    
    file_path = Config.RESULTS_FOLDER / result_id / filename
    
    if not file_path.exists():
        abort(404)
    if not file_path.is_relative_to(Config.RESULTS_FOLDER):
        abort(403)
    
    return send_file(str(file_path))


@history_bp.route("/recent-images")
def get_recent_images():
    """Buffer ảnh kết quả gần nhất cho UI dashboard."""
    limit = int(request.args.get("limit", 10))
    images = recent_image_store.get_recent(limit=limit)
    return jsonify({"images": images, "total": len(images)})


@history_bp.route("/alerts")
def get_alerts():
    """Danh sách cảnh báo gần nhất."""
    limit = int(request.args.get("limit", 20))
    alerts = database.get_recent_alerts(limit=limit)
    return jsonify({"alerts": alerts, "total": len(alerts)})

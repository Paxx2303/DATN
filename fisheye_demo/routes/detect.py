"""
routes/detect.py — Detection API

Endpoints:
  POST /api/detect           → Image/Video detection
  GET  /api/jobs/<job_id>    → Poll job status
  GET  /api/jobs             → List all jobs
"""

import time
import json
import logging
from pathlib import Path
from flask import Blueprint, request, jsonify, current_app
from werkzeug.utils import secure_filename

from config import Config
from utils.helpers import (
    generate_result_id, read_uploaded_image, apply_preprocessing,
    pil_to_base64, draw_detections_on_image, ensure_result_dir,
    allowed_media_file,
)
from services.inference import run_inference
from services.model_registry import load_model
from analytics import heatmap, density_analyzer
from alert_manager import alert_manager
from job_queue import video_job_queue
import db as database
import recent_image_store

logger = logging.getLogger(__name__)
detect_bp = Blueprint("detect", __name__, url_prefix="/api")


@detect_bp.route("/detect", methods=["POST"])
def detect():
    """
    Unified detection endpoint cho cả image và video.
    
    Form data:
      file          : Media file (image hoặc video)
      task          : "detect" | "convert" (default: detect)
      model_key     : Key của YOLO model
      conf          : Confidence threshold (float)
      iou           : IOU threshold (float)
      device        : "cpu" | "cuda:0" | "mps"
      fisheye       : "true" | "false" — bật fisheye preprocessing
      fisheye_strength: float
      fisheye_radius  : float
      fisheye_effect  : "standard" | "extreme" | "subtle"
      fisheye_cx      : float [0-1]
      fisheye_cy      : float [0-1]
    
    Returns:
      Image: 200 với full JSON result + base64 annotated image
      Video: 202 với job_id để poll status
    """
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    
    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "Empty filename"}), 400
    
    # ── Parse parameters ──────────────────────────────────────
    task      = request.form.get("task", "detect")
    model_key = request.form.get("model_key", Config.DEFAULT_MODEL_KEY)
    conf      = float(request.form.get("conf", Config.DEFAULT_CONF))
    iou       = float(request.form.get("iou", Config.DEFAULT_IOU))
    device    = request.form.get("device", Config.DEFAULT_DEVICE)
    
    fisheye_raw      = request.form.get("fisheye") or request.form.get("apply_fisheye", "false")
    fisheye_enabled  = fisheye_raw.lower() == "true"
    fisheye_strength = float(request.form.get("fisheye_strength", Config.FISHEYE_STRENGTH))
    fisheye_radius   = float(request.form.get("fisheye_radius", Config.FISHEYE_RADIUS))
    fisheye_effect   = request.form.get("fisheye_effect", Config.FISHEYE_EFFECT)
    fisheye_cx       = float(request.form.get("fisheye_cx", 0.5))
    fisheye_cy       = float(request.form.get("fisheye_cy", 0.5))
    
    filename = secure_filename(file.filename)
    
    # ── Xác định loại media ───────────────────────────────────
    is_video = allowed_media_file(filename, "video")
    is_image = allowed_media_file(filename, "image")
    
    if not is_video and not is_image:
        return jsonify({"error": f"Unsupported file type: {filename}"}), 400
    
    preprocessing_config = {
        "enabled":  fisheye_enabled,
        "strength": fisheye_strength,
        "radius":   fisheye_radius,
        "effect":   fisheye_effect,
        "center_x": fisheye_cx,
        "center_y": fisheye_cy,
    }
    
    # ── XỬ LÝ ẢNH: đồng bộ ───────────────────────────────────
    if is_image:
        return _handle_image_detect(
            file, filename, task, model_key, conf, iou, device, preprocessing_config
        )
    
    # ── XỬ LÝ VIDEO: đồng bộ ──────────────────────────────────
    if is_video:
        return _handle_video_detect_sync(
            file, filename, task, model_key, conf, iou, device, preprocessing_config
        )


def _handle_image_detect(file, filename, task, model_key, conf, iou, device, prep):
    """Xử lý ảnh tĩnh đồng bộ. Returns 200 với kết quả đầy đủ."""
    t_start = time.time()
    result_id = generate_result_id()
    
    # 1. Đọc ảnh
    image = read_uploaded_image(file)
    if image is None:
        return jsonify({"error": "Cannot decode image"}), 400
    
    original_size = (image.width, image.height)
    
    # 2. Áp dụng fisheye preprocessing
    preprocessed = apply_preprocessing(
        image,
        enabled=prep["enabled"],
        strength=prep["strength"],
        radius=prep["radius"],
        effect=prep["effect"],
        center_x=prep["center_x"],
        center_y=prep["center_y"],
    )
    
    # 3. YOLO inference
    inference_result = run_inference(
        image=preprocessed,
        model_key=model_key,
        conf=conf, iou=iou, device=device,
    )
    
    # 4. Vẽ annotations
    annotated = draw_detections_on_image(preprocessed, inference_result["detections"])
    
    # 5. Lưu kết quả ra disk
    result_dir = ensure_result_dir(result_id)
    annotated_path = result_dir / "annotated.jpg"
    preprocessed_path = result_dir / "preprocessed.jpg"
    
    annotated.save(annotated_path, "JPEG", quality=90)
    if prep["enabled"]:
        preprocessed.save(preprocessed_path, "JPEG", quality=90)
    
    # 6. Lưu metadata JSON
    duration = time.time() - t_start
    summary = {
        "counts":        inference_result["counts"],
        "total":         inference_result["total"],
        "avg_speed":     0.0,   # N/A cho ảnh tĩnh
        "duration_s":    round(duration, 3),
        "model_key":     model_key,
        "original_size": original_size,
    }
    artifacts = {
        "annotated": "annotated.jpg",
        **({"preprocessed": "preprocessed.jpg"} if prep["enabled"] else {}),
    }
    
    meta = {
        "result_id":    result_id,
        "filename":     filename,
        "summary":      summary,
        "artifacts":    artifacts,
        "preprocessing": prep,
        "detections":   inference_result["detections"],
    }
    with open(result_dir / "meta.json", "w") as f:
        json.dump(meta, f, indent=2)
    
    # 7. Lưu DB
    record_data = {
        "id":            result_id,
        "filename":      filename,
        "task":          task,
        "media_type":    "image",
        "source_layout": "fisheye" if prep["enabled"] else "normal",
        "preprocessing": prep,
        "summary":       summary,
        "artifacts":     artifacts,
        "gcs_urls":      {},
    }
    database.insert_detection(record_data)
    
    # 8. Cache recent image
    recent_image_store.push_image(
        result_id=result_id,
        pil_image=annotated,
        media_type="image",
        filename=filename,
        summary=summary,
    )
    
    # 9. Cập nhật analytics
    heatmap.update(inference_result["detections"], annotated.width, annotated.height)
    density_analyzer.record(inference_result["total"])
    alert_manager.check_and_alert(inference_result["total"], camera_source="upload")
    
    # Inject artifact_urls
    from routes.history import inject_artifact_urls
    record_with_urls = inject_artifact_urls(record_data)
    
    from services.model_registry import get_available_models
    avail_models = get_available_models()
    model_name = avail_models.get(model_key, {}).get("name", f"YOLO {model_key.capitalize()}")
    
    # 10. Trả response khớp hoàn hảo với SPA index.html
    return jsonify({
        "record":        record_with_urls,
        "request_id":    result_id,
        "media_type":    "image",
        "inference_ms":  int(duration * 1000),
        "preprocessed":  f"data:image/jpeg;base64,{pil_to_base64(preprocessed)}",
        "result":        f"data:image/jpeg;base64,{pil_to_base64(annotated)}",
        "total_objects": inference_result["total"],
        "detections":    inference_result["detections"],
        "class_counts":  inference_result["counts"],
        "preprocessing": {
            "enabled":       prep["enabled"],
            "source_layout": "fisheye" if prep["enabled"] else "normal",
        },
        "model": {
            "loaded_from_name": model_name,
        }
    }), 200


def _handle_video_submit(file, filename, task, model_key, conf, iou, device, prep):
    """Submit video job vào queue. Returns 202 với job_id."""
    result_id = generate_result_id()
    
    # Lưu video lên disk trước
    upload_path = Config.UPLOAD_FOLDER / f"{result_id}_{filename}"
    file.save(str(upload_path))
    
    # Tạo thư mục output
    result_dir = ensure_result_dir(result_id)
    output_path = result_dir / "annotated.mp4"
    preview_path = result_dir / "preview.jpg"
    
    # Params cho worker
    params = {
        "result_id":     result_id,
        "input_path":    str(upload_path),
        "output_path":   str(output_path),
        "preview_path":  str(preview_path),
        "filename":      filename,
        "task":          task,
        "model_key":     model_key,
        "conf":          conf,
        "iou":           iou,
        "device":        device,
        "preprocessing": prep,
    }
    
    # Submit vào job queue
    job_id = video_job_queue.submit_job(_video_worker_fn, params)
    
    return jsonify({
        "job_id":    job_id,
        "result_id": result_id,
        "status":    "pending",
        "filename":  filename,
        "message":   "Video submitted for processing. Poll /api/jobs/{job_id} for status.",
    }), 202


def _video_worker_fn(job_id: str, params: dict, progress_cb) -> str:
    """
    Worker function chạy trong thread pool.
    
    Returns result_id khi hoàn thành.
    """
    import time
    from services.model_registry import load_model
    from video_detect import run_video_detect
    import db as database
    import recent_image_store
    from PIL import Image
    import cloud_storage
    
    result_id  = params["result_id"]
    model_key  = params["model_key"]
    device     = params["device"]
    prep       = params["preprocessing"]
    filename   = params["filename"]
    
    logger.info(f"Video worker started: job={job_id}, result={result_id}")
    
    # Load model
    model = load_model(model_key, device)
    
    # Khởi tạo incident detector - Đã tắt theo yêu cầu người dùng
    inc_detector = None
    
    # Chạy video processing
    stats = run_video_detect(
        input_path=params["input_path"],
        output_path=params["output_path"],
        model=model,
        conf=params["conf"],
        iou=params["iou"],
        device=device,
        apply_fisheye_transform=prep["enabled"],
        fisheye_strength=prep.get("strength", 0.6),
        fisheye_radius=prep.get("radius", 0.85),
        fisheye_effect=prep.get("effect", "standard"),
        fisheye_center_x=prep.get("center_x", 0.5),
        fisheye_center_y=prep.get("center_y", 0.5),
        preview_path=params.get("preview_path"),
        name_map=Config.VEHICLE_NAME_MAP,
        allowed_classes=Config.VEHICLE_CLASSES,
        filter_allowed_classes=True,
        incident_detector_inst=inc_detector,
        incident_camera_id=result_id,
        progress_cb=progress_cb,
    )
    
    progress_cb(95.0)
    
    # Upload GCS nếu cấu hình
    result_dir = Config.RESULTS_FOLDER / result_id
    gcs_urls = cloud_storage.upload_result_folder(result_id, result_dir)
    
    # Lưu DB
    summary = {
        "counts":     stats["counts"],
        "avg_speed":  stats["avg_speed"],
        "duration_s": stats["duration_s"],
        "frame_count": stats["frame_count"],
        "incidents":  len(stats.get("incidents", [])),
        "model_key":  model_key,
    }
    artifacts = {
        "annotated": "annotated.mp4",
        "preview":   "preview.jpg",
    }
    database.insert_detection({
        "id":            result_id,
        "filename":      filename,
        "task":          params.get("task", "detect"),
        "media_type":    "video",
        "source_layout": "fisheye" if prep["enabled"] else "normal",
        "preprocessing": prep,
        "summary":       summary,
        "artifacts":     artifacts,
        "gcs_urls":      gcs_urls,
    })
    
    # Cache preview image
    preview_path = Path(params.get("preview_path", ""))
    if preview_path.exists():
        from PIL import Image
        preview_img = Image.open(preview_path).convert("RGB")
        recent_image_store.push_image(
            result_id=result_id,
            pil_image=preview_img,
            media_type="video",
            filename=filename,
            summary=summary,
        )
    
    # Dọn dẹp file upload tạm
    try:
        Path(params["input_path"]).unlink(missing_ok=True)
    except Exception:
        pass
    
    progress_cb(100.0)
    logger.info(f"Video worker done: result={result_id}")
    return result_id


def _handle_video_detect_sync(file, filename, task, model_key, conf, iou, device, prep):
    """
    Xử lý video đồng bộ trong request thread.
    Phù hợp cho video ngắn / demo. Gọi worker function trực tiếp.
    """
    result_id   = generate_result_id()
    upload_path = Config.UPLOAD_FOLDER / f"{result_id}_{filename}"
    result_dir  = ensure_result_dir(result_id)
    output_path = result_dir / "annotated.mp4"
    preview_path = result_dir / "preview.jpg"

    file.save(str(upload_path))

    params = {
        "result_id":    result_id,
        "input_path":   str(upload_path),
        "output_path":  str(output_path),
        "preview_path": str(preview_path),
        "filename":     filename,
        "task":         task,
        "model_key":    model_key,
        "conf":         conf,
        "iou":          iou,
        "device":       device,
        "preprocessing": prep,
    }

    try:
        _video_worker_fn("sync", params, lambda pct: None)
    except Exception as exc:
        logger.error(f"Sync video processing failed: {exc}", exc_info=True)
        return jsonify({"error": str(exc)}), 500

    record = database.get_detection_by_id(result_id)
    if record is None:
        return jsonify({"error": "Video processing completed but record not found"}), 500

    from routes.history import inject_artifact_urls
    record = inject_artifact_urls(record)

    summary_db = record.get("summary", {}) or {}
    frame_count = summary_db.get("frame_count", 0)
    duration_s  = summary_db.get("duration_s", 0) or 1

    from services.model_registry import get_available_models
    avail = get_available_models()
    model_name = avail.get(model_key, {}).get("name", f"YOLO {model_key.capitalize()}")

    return jsonify({
        "record":      record,
        "request_id":  result_id,
        "media_type":  "video",
        "summary": {
            "total_frames":      frame_count,
            "fps_original":      round(frame_count / duration_s, 1),
            "inference_ms_avg":  round(duration_s * 1000 / max(frame_count, 1), 1),
            "class_counts":      summary_db.get("counts", {}),
            "total_detections":  sum(summary_db.get("counts", {}).values()),
            "resolution":        summary_db.get("resolution", "unknown"),
            "processing_fps":    summary_db.get("processing_fps", None),
            "detection_stride":  summary_db.get("detection_stride", 1),
            "target_detect_fps": summary_db.get("target_detect_fps", None),
        },
        "preprocessing": {
            "enabled":       prep["enabled"],
            "source_layout": "fisheye" if prep["enabled"] else "normal",
        },
        "model": {"loaded_from_name": model_name},
    }), 200


def _handle_image_convert(file, filename, prep):
    """Áp dụng fisheye preprocessing lên ảnh và trả về kết quả."""
    import time as _time
    t_start = _time.time()
    result_id = generate_result_id()

    image = read_uploaded_image(file)
    if image is None:
        return jsonify({"error": "Cannot decode image"}), 400

    converted = apply_preprocessing(
        image,
        enabled=True,
        strength=prep["strength"],
        radius=prep["radius"],
        effect=prep["effect"],
        center_x=prep["center_x"],
        center_y=prep["center_y"],
    )

    result_dir     = ensure_result_dir(result_id)
    converted_path = result_dir / "fisheye_image.jpg"
    converted.save(converted_path, "JPEG", quality=90)

    duration = _time.time() - t_start
    summary = {
        "output_kind":   "fisheye_image",
        "duration_s":    round(duration, 3),
        "original_size": (image.width, image.height),
    }
    artifacts = {"fisheye_image": "fisheye_image.jpg"}

    with open(result_dir / "meta.json", "w") as f:
        json.dump({
            "result_id":    result_id,
            "filename":     filename,
            "summary":      summary,
            "artifacts":    artifacts,
            "preprocessing": prep,
        }, f, indent=2)

    record_data = {
        "id":            result_id,
        "filename":      filename,
        "task":          "convert",
        "media_type":    "image",
        "source_layout": prep.get("source_layout", "normal"),
        "preprocessing": prep,
        "summary":       summary,
        "artifacts":     artifacts,
        "gcs_urls":      {},
    }
    database.insert_detection(record_data)
    recent_image_store.push_image(
        result_id=result_id,
        pil_image=converted,
        media_type="image",
        filename=filename,
        summary=summary,
    )

    from routes.history import inject_artifact_urls
    record_with_urls = inject_artifact_urls(record_data)

    return jsonify({
        "record":      record_with_urls,
        "request_id":  result_id,
        "media_type":  "image",
        "preprocessing": {
            "enabled":       True,
            "source_layout": prep.get("source_layout", "normal"),
            "effect":        prep["effect"],
            "strength":      prep["strength"],
            "radius":        prep["radius"],
        },
        "result": f"data:image/jpeg;base64,{pil_to_base64(converted)}",
    }), 200


@detect_bp.route("/convert", methods=["POST"])
def convert():
    """
    Áp dụng fisheye preprocessing lên ảnh/video.

    Form data:
      media         : Media file (image hoặc video)
      fisheye_*     : Fisheye config params (strength, radius, effect, cx, cy)
      source_layout : "fisheye" | "normal"
    """
    if "media" not in request.files:
        return jsonify({"error": "No media file uploaded (field: media)"}), 400

    file = request.files["media"]
    if not file.filename:
        return jsonify({"error": "Empty filename"}), 400

    filename = secure_filename(file.filename)
    is_image = allowed_media_file(filename, "image")
    is_video = allowed_media_file(filename, "video")

    if not is_image and not is_video:
        return jsonify({"error": f"Unsupported file type: {filename}"}), 400

    fisheye_strength = float(request.form.get("fisheye_strength", Config.FISHEYE_STRENGTH))
    fisheye_radius   = float(request.form.get("fisheye_radius",   Config.FISHEYE_RADIUS))
    fisheye_effect   = request.form.get("fisheye_effect", Config.FISHEYE_EFFECT)
    fisheye_cx       = float(request.form.get("fisheye_cx", 0.5))
    fisheye_cy       = float(request.form.get("fisheye_cy", 0.5))
    source_layout    = request.form.get("source_layout", "normal")

    prep = {
        "enabled":       True,
        "strength":      fisheye_strength,
        "radius":        fisheye_radius,
        "effect":        fisheye_effect,
        "center_x":      fisheye_cx,
        "center_y":      fisheye_cy,
        "source_layout": source_layout,
    }

    if is_image:
        return _handle_image_convert(file, filename, prep)

    if is_video:
        return _handle_video_detect_sync(
            file, filename, "convert",
            Config.DEFAULT_MODEL_KEY, Config.DEFAULT_CONF, Config.DEFAULT_IOU,
            Config.DEFAULT_DEVICE, prep,
        )


@detect_bp.route("/jobs/<job_id>", methods=["GET"])
def get_job_status(job_id: str):
    """Poll trạng thái một job."""
    status = video_job_queue.get_status(job_id)
    if status is None:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(status), 200


@detect_bp.route("/jobs", methods=["GET"])
def list_jobs():
    """Danh sách tất cả jobs."""
    jobs = video_job_queue.get_all_jobs()
    return jsonify({"jobs": jobs, "total": len(jobs)}), 200

"""
routes/external_camera.py — External Camera Live Monitor API

Endpoints:
  POST /api/external-camera/start         → Bắt đầu live monitoring
  POST /api/external-camera/stop          → Dừng live monitoring
  GET  /api/external-camera/status        → Trạng thái monitor
  GET  /api/external-camera/live/stream   → MJPEG stream (multipart)
  GET  /api/external-camera/snapshot/<idx> → Ảnh tĩnh của camera idx
"""

import logging
from flask import Blueprint, request, jsonify, Response, stream_with_context
from services.camera_monitor import camera_monitor
from config import Config

logger = logging.getLogger(__name__)
ext_cam_bp = Blueprint("external_camera", __name__, url_prefix="/api/external-camera")


@ext_cam_bp.route("/source", methods=["GET"])
def get_camera_source():
    """
    Resolve camera URL into embed_url, source_mode, title, youtube_id.
    This matches the SPA's expectations.
    """
    url = request.args.get("external_camera_url", "").strip()
    if not url:
        return jsonify({"error": "No URL provided"}), 400

    import urllib.parse as urlparse
    parsed = urlparse.urlparse(url)
    
    source_mode = "snapshot"
    embed_url = url
    title = "External Camera"
    youtube_id = ""

    # Check for youtube
    if "youtube.com" in parsed.netloc or "youtu.be" in parsed.netloc:
        if "youtu.be" in parsed.netloc:
            youtube_id = parsed.path.lstrip("/")
        else:
            query = urlparse.parse_qs(parsed.query)
            youtube_id = query.get("v", [""])[0]
        
        embed_url = f"https://www.youtube.com/embed/{youtube_id}"
        title = "YouTube Live Traffic Camera"
    elif any(parsed.path.lower().endswith(ext) for ext in (".m3u8", ".mp4", ".ts", ".mjpeg")) or parsed.scheme in ("rtsp", "rtmp"):
        source_mode = "stream"
        title = "Direct Live Stream Source"
    elif "webcam.vn" in parsed.netloc:
        title = "Webcam.vn Traffic Portal"
        source_mode = "snapshot"
    else:
        title = parsed.netloc or "Traffic Webcam Website"
        source_mode = "snapshot"

    return jsonify({
        "source_mode": source_mode,
        "embed_url": embed_url,
        "title": title,
        "youtube_id": youtube_id,
    }), 200


@ext_cam_bp.route("/detect", methods=["POST"])
def detect_external_camera():
    """
    Singleshot detect: thu thập một snapshot từ camera ngoài và chạy YOLO.

    Form data:
      external_camera_url : URL nguồn camera
      camera_limit        : số camera tối đa (default 1)
      model_key, conf, iou, source_layout
      fisheye_strength, fisheye_radius, fisheye_effect, apply_fisheye
    """
    import time
    import json
    from utils.helpers import (
        generate_result_id, apply_preprocessing,
        pil_to_base64, draw_detections_on_image, ensure_result_dir,
    )
    from services.inference import run_inference
    from services.model_registry import get_available_models, load_model
    from analytics import heatmap, density_analyzer
    from alert_manager import alert_manager
    import db as database
    import recent_image_store
    from external_camera_detector import (
        extract_camera_entries, fetch_snapshots_parallel,
        capture_stream_frame, build_camera_collage, CameraEntry,
    )
    from PIL import Image
    import io as _io

    url          = request.form.get("external_camera_url", Config.EXT_CAM_SOURCE_URL).strip()
    camera_limit = int(request.form.get("camera_limit", 1))
    model_key    = request.form.get("model_key", Config.DEFAULT_MODEL_KEY)
    conf         = float(request.form.get("conf", Config.DEFAULT_CONF))
    iou          = float(request.form.get("iou", Config.DEFAULT_IOU))
    source_layout = request.form.get("source_layout", "normal")
    apply_fish_raw = request.form.get("apply_fisheye", "false").lower()
    fisheye_enabled = apply_fish_raw == "true"
    fisheye_strength = float(request.form.get("fisheye_strength", Config.FISHEYE_STRENGTH))
    fisheye_radius   = float(request.form.get("fisheye_radius",   Config.FISHEYE_RADIUS))
    fisheye_effect   = request.form.get("fisheye_effect", Config.FISHEYE_EFFECT)

    if not url:
        return jsonify({"error": "No external_camera_url provided"}), 400

    t_start   = time.time()
    result_id = generate_result_id()

    # ── Determine source_mode and fetch entries ────────────────
    import urllib.parse as _urlparse
    parsed = _urlparse.urlparse(url)
    is_stream = (
        any(url.lower().endswith(ext) for ext in (".m3u8", ".mp4", ".ts", ".mjpeg"))
        or parsed.scheme in ("rtsp", "rtmp")
    )

    entries = []
    try:
        if is_stream:
            frame = capture_stream_frame(url)
            if frame:
                e = CameraEntry(url=url, name="Live Stream", camera_index=0)
                e.snapshot = frame
                entries = [e]
        else:
            raw_entries = extract_camera_entries(url, limit=camera_limit)
            entries = fetch_snapshots_parallel(raw_entries, max_workers=4)
    except Exception as exc:
        logger.warning(f"External camera snapshot failed: {exc}")

    # Fallback to a solid placeholder if nothing was captured
    if not entries:
        ph = Image.new("RGB", (640, 480), (20, 30, 50))
        e = CameraEntry(url=url, name="Camera 1", camera_index=0)
        e.snapshot = ph
        entries = [e]

    # ── Run inference on each entry ────────────────────────────
    camera_results = []
    all_counts: dict = {}

    for entry in entries:
        if entry.snapshot is None:
            continue

        img = entry.snapshot
        if fisheye_enabled:
            img = apply_preprocessing(
                img, enabled=True,
                strength=fisheye_strength, radius=fisheye_radius,
                effect=fisheye_effect,
            )
            entry.snapshot = img

        result = run_inference(image=img, model_key=model_key, conf=conf, iou=iou,
                               device=Config.DEFAULT_DEVICE)
        annotated = draw_detections_on_image(img, result["detections"])
        entry.snapshot = annotated

        for cls, cnt in result["counts"].items():
            all_counts[cls] = all_counts.get(cls, 0) + cnt

        camera_results.append({
            "title":         entry.name,
            "total_objects": result["total"],
            "annotated":     f"data:image/jpeg;base64,{pil_to_base64(annotated)}",
            "youtube_id":    "",
        })

        # Update analytics
        density_analyzer.record(result["total"])
        alert_manager.check_and_alert(result["total"], camera_source=entry.name)

    # ── Build collage overview ─────────────────────────────────
    camera_labels = {e.camera_index: f"{e.name}: {r['total_objects']}"
                     for e, r in zip(entries, camera_results) if e.snapshot is not None}
    collage = build_camera_collage(entries, cell_width=320, cell_height=240, cols=2,
                                   labels=camera_labels)
    overview_b64 = f"data:image/jpeg;base64,{pil_to_base64(collage)}"

    # ── Save to disk + DB ──────────────────────────────────────
    result_dir = ensure_result_dir(result_id)
    collage.save(result_dir / "overview_annotated.jpg", "JPEG", quality=85)
    total_objects = sum(r["total_objects"] for r in camera_results)
    inference_ms  = int((time.time() - t_start) * 1000)
    summary = {
        "class_counts":  all_counts,
        "total_objects": total_objects,
        "inference_ms":  inference_ms,
        "camera_count":  len(camera_results),
        "counts":        all_counts,
    }
    artifacts = {"overview_annotated": "overview_annotated.jpg"}
    with open(result_dir / "meta.json", "w") as f:
        json.dump({"result_id": result_id, "summary": summary,
                   "artifacts": artifacts}, f, indent=2)

    record_data = {
        "id":            result_id,
        "filename":      f"external_camera_{len(camera_results)}cam",
        "task":          "detect",
        "media_type":    "image",
        "source_layout": "fisheye" if fisheye_enabled else "normal",
        "preprocessing": {"enabled": fisheye_enabled},
        "summary":       summary,
        "artifacts":     artifacts,
        "gcs_urls":      {},
    }
    try:
        database.insert_detection(record_data)
    except Exception as exc:
        logger.warning(f"Failed to save external camera detection: {exc}")

    from routes.history import inject_artifact_urls
    record_with_urls = inject_artifact_urls(record_data)

    avail = get_available_models()
    model_name = avail.get(model_key, {}).get("name", f"YOLO {model_key.capitalize()}")

    return jsonify({
        "record":       record_with_urls,
        "request_id":   result_id,
        "camera_count": len(camera_results),
        "overview":     overview_b64,
        "cameras":      camera_results,
        "summary":      summary,
        "preprocessing": {
            "enabled":       fisheye_enabled,
            "source_layout": "fisheye" if fisheye_enabled else source_layout,
        },
        "model": {"loaded_from_name": model_name},
    }), 200


@ext_cam_bp.route("/start", methods=["POST"])
def start_monitor():
    """
    Kích hoạt live monitoring.
    
    JSON body:
      source_mode    : "snapshot" | "stream"
      source_url     : URL của trang camera (snapshot mode)
      stream_url     : URL HLS/RTSP (stream mode)
      camera_limit   : số camera tối đa
      interval       : polling interval (giây)
      model_key      : YOLO model key
      conf           : confidence threshold
      iou            : IOU threshold
      device         : "cpu" | "cuda:0"
      fisheye        : bool — bật fisheye
      fisheye_strength, fisheye_radius, fisheye_effect : float/str
    """
    # Accept both JSON body and multipart/form-data (sent by frontend FormData)
    if request.content_type and "application/json" in request.content_type:
        data = request.get_json(silent=True) or {}
    else:
        data = {k: v for k, v in request.form.items()}
    
    # Field aliases — frontend FormData uses different keys than the JSON API
    source_url = data.get("source_url") or data.get("external_camera_url", "") or Config.EXT_CAM_SOURCE_URL
    interval   = float(data.get("interval") or data.get("interval_seconds") or Config.EXT_CAM_INTERVAL)
    device     = data.get("device") or data.get("compute_mode") or Config.DEFAULT_DEVICE
    fisheye_on = data.get("fisheye", data.get("apply_fisheye", "false"))
    fisheye_on = str(fisheye_on).lower() in ("true", "1", "yes")

    # Parse fisheye config
    fisheye_config = {}
    if fisheye_on:
        fisheye_config = {
            "enabled":  True,
            "strength": float(data.get("fisheye_strength", Config.FISHEYE_STRENGTH)),
            "radius":   float(data.get("fisheye_radius", Config.FISHEYE_RADIUS)),
            "effect":   data.get("fisheye_effect", Config.FISHEYE_EFFECT),
        }

    status = camera_monitor.start(
        source_mode    = data.get("source_mode", "snapshot"),
        source_url     = source_url,
        stream_url     = data.get("stream_url", ""),
        camera_limit   = int(data.get("camera_limit", Config.EXT_CAM_LIMIT)),
        preprocessing  = fisheye_config,
        conf_threshold = float(data.get("conf", Config.DEFAULT_CONF)),
        iou_threshold  = float(data.get("iou", Config.DEFAULT_IOU)),
        model_key      = data.get("model_key", Config.DEFAULT_MODEL_KEY),
        interval_seconds = interval,
        compute_mode   = device,
    )
    
    return jsonify({"message": "Monitor started", "status": status}), 200


@ext_cam_bp.route("/stop", methods=["POST"])
def stop_monitor():
    """Dừng live monitoring."""
    camera_monitor.stop()
    status = camera_monitor.get_status()
    status["message"] = "Monitor stopped"
    return jsonify(status), 200


@ext_cam_bp.route("/status")
def get_status():
    """Trạng thái hiện tại của monitor."""
    return jsonify(camera_monitor.get_status())


@ext_cam_bp.route("/live/stream")
def live_stream():
    """
    MJPEG stream endpoint.
    
    Query params:
      view : "overview" | "camera_0" | "camera_1" | ... (default: overview)
    
    Response: multipart/x-mixed-replace;boundary=frame
    Browsers render này trực tiếp với <img src="/api/external-camera/live/stream">
    """
    view = request.args.get("view", "overview")
    
    def generate():
        yield from camera_monitor.mjpeg_stream(view=view)
    
    return Response(
        stream_with_context(generate()),
        mimetype="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Connection": "keep-alive",
        }
    )


@ext_cam_bp.route("/snapshot/overview")
def get_overview_snapshot():
    """Trả về JPEG snapshot của collage overview."""
    from services.camera_monitor import _placeholder_jpeg
    frame_bytes = camera_monitor.get_frame("overview") or _placeholder_jpeg()
    return Response(frame_bytes, mimetype="image/jpeg",
                    headers={"Cache-Control": "no-cache, no-store"})


@ext_cam_bp.route("/snapshot/<int:camera_idx>")
def get_camera_snapshot(camera_idx: int):
    """Trả về JPEG snapshot của camera cụ thể."""
    from services.camera_monitor import _placeholder_jpeg
    frame_bytes = camera_monitor.get_frame(f"camera_{camera_idx}") or _placeholder_jpeg()
    return Response(frame_bytes, mimetype="image/jpeg",
                    headers={"Cache-Control": "no-cache, no-store"})

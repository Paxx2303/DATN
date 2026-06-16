"""
services/camera_monitor.py — External Camera Live Monitor

THIẾT KẾ:
- GPU mode  : fetch 4 cameras, run YOLO inference in parallel (ThreadPoolExecutor).
- CPU mode  : fetch only the first camera, run inference sequentially frame-by-frame.
- Per cycle : centroid tracking → SpeedEstimator → CongestionDetector → AlertManager.
- Singleton ExternalCameraLiveMonitor; start() is idempotent (restarts on new config).
- _stream_frames: dict[str, bytes] — "overview", "camera_0", ... — JPEG bytes per view.
"""

import io
import time
import threading
import logging
import numpy as np
from PIL import Image
from typing import Optional, Generator
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import Config
from external_camera_detector import (
    extract_camera_entries,
    fetch_snapshots_parallel,
    capture_stream_frame,
    build_camera_collage,
    CameraEntry,
)
from analytics import heatmap, density_analyzer
from alert_manager import alert_manager

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Simple centroid tracker — assigns consistent IDs across monitor cycles
# ─────────────────────────────────────────────────────────────────────────────

class _CentroidTracker:
    """Nearest-centroid matching for cross-cycle vehicle identity."""

    MAX_DIST_PX = 80

    def __init__(self) -> None:
        self._next_id = 0
        self._centroids: dict[int, tuple] = {}  # id → (cx, cy)

    def update(self, detections: list[dict]) -> tuple[dict[int, tuple], dict[int, int]]:
        """
        Match new detections to existing tracks.

        Returns
        -------
        tracks : {track_id: (cx, cy)}
        det_assignments : {detection_index: track_id}
        """
        new_pts = [tuple(d["center"]) for d in detections if "center" in d]

        if not self._centroids:
            result: dict[int, tuple] = {}
            assignments: dict[int, int] = {}
            for det_idx, (cx, cy) in enumerate(new_pts):
                self._centroids[self._next_id] = (cx, cy)
                result[self._next_id] = (cx, cy)
                assignments[det_idx] = self._next_id
                self._next_id += 1
            return result, assignments

        if not new_pts:
            self._centroids.clear()
            return {}, {}

        matched_new: dict[int, int] = {}  # new_idx → existing track_id
        used_ids: set[int] = set()

        for new_idx, (nx, ny) in enumerate(new_pts):
            best_id, best_d = -1, float(self.MAX_DIST_PX)
            for eid, (ex, ey) in self._centroids.items():
                if eid in used_ids:
                    continue
                d = ((nx - ex) ** 2 + (ny - ey) ** 2) ** 0.5
                if d < best_d:
                    best_d, best_id = d, eid
            if best_id >= 0:
                matched_new[new_idx] = best_id
                used_ids.add(best_id)

        new_centroids: dict[int, tuple] = {}
        result: dict[int, tuple] = {}
        assignments: dict[int, int] = {}
        for new_idx, (nx, ny) in enumerate(new_pts):
            tid = matched_new.get(new_idx)
            if tid is None:
                tid = self._next_id
                self._next_id += 1
            new_centroids[tid] = (nx, ny)
            result[tid] = (nx, ny)
            assignments[new_idx] = tid

        self._centroids = new_centroids
        return result, assignments


# ─────────────────────────────────────────────────────────────────────────────
# Monitor
# ─────────────────────────────────────────────────────────────────────────────

class ExternalCameraLiveMonitor:
    """
    Background thread for live external-camera monitoring.

    GPU mode  → 4 cameras, parallel YOLO inference.
    CPU mode  → 1 camera, sequential frame-by-frame inference.
    """

    def __init__(self) -> None:
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        # Frame buffer: key → JPEG bytes
        self._stream_frames: dict[str, bytes] = {}

        # Active config (set by start())
        self._config: dict = {}

        # Aggregate counters
        self._last_counts: dict[str, int] = {}
        self._total_vehicles: int = 0

        # Status fields reported to the UI via get_status()
        self._cycle_count: int = 0
        self._last_updated_at: Optional[str] = None
        self._last_cycle_duration_ms: Optional[float] = None
        self._actual_cycle_fps: Optional[float] = None
        self._last_error: Optional[str] = None
        self._last_result: Optional[dict] = None

        # Per-camera analytics state (reset on start())
        self._camera_trackers: dict[str, _CentroidTracker] = {}
        self._camera_speed_estimators: dict = {}       # cam_key → SpeedEstimator
        self._camera_congestion_detectors: dict = {}   # cam_key → CongestionDetector
        self._camera_congestion: dict[str, dict] = {}  # cam_key → last congestion result
        self._camera_incident_detectors: dict = {}     # cam_key → IncidentDetector

        # ALPR (license plate) state on live feed
        self._live_plates: list[dict] = []             # rolling recent plates (newest last)
        self._alpr_seen: dict[str, int] = {}           # "cam|plate" → last cycle saved (dedup)
        self._alpr_total: int = 0                      # total plates saved this session

    # ── Public API ──────────────────────────────────────────────────────────

    def start(
        self,
        source_mode: str = "snapshot",
        source_url: str = "",
        stream_url: str = "",
        camera_limit: int = None,
        preprocessing: dict = None,
        conf_threshold: float = None,
        iou_threshold: float = None,
        model_key: str = None,
        interval_seconds: float = None,
        compute_mode: str = None,
        alpr_enabled: bool = None,
        alpr_every: int = None,
    ) -> dict:
        """Start (or restart) live monitoring with the given config."""
        with self._lock:
            if self._running:
                logger.info("Monitor already running — restarting with new config")
                self._running = False
                if self._thread and self._thread.is_alive():
                    self._thread.join(timeout=5.0)

            device = compute_mode or Config.DEFAULT_DEVICE
            is_gpu  = device != "cpu"

            # Auto-select camera limit based on device if not supplied
            auto_limit = Config.EXT_CAM_LIMIT_GPU if is_gpu else Config.EXT_CAM_LIMIT_CPU
            resolved_limit = camera_limit or auto_limit

            # Default source to camera.0511.vn when not supplied
            resolved_url = source_url or Config.EXT_CAM_SOURCE_URL

            self._config = {
                "source_mode":    source_mode,
                "source_url":     resolved_url,
                "stream_url":     stream_url,
                "camera_limit":   resolved_limit,
                "source_layout":  (preprocessing or {}).get("source_layout", "normal"),
                "preprocessing":  preprocessing or {},
                "conf":           conf_threshold or Config.DEFAULT_CONF,
                "iou":            iou_threshold  or Config.DEFAULT_IOU,
                "model_key":      model_key      or Config.DEFAULT_MODEL_KEY,
                "interval":       interval_seconds or Config.EXT_CAM_INTERVAL,
                "device":         device,
                "alpr_enabled":   (Config.ALPR_LIVE_ENABLED if alpr_enabled is None
                                   else bool(alpr_enabled)),
                "alpr_every":     int(alpr_every or Config.ALPR_LIVE_EVERY),
            }

            # Reset per-camera analytics on every (re)start
            self._camera_trackers.clear()
            self._camera_speed_estimators.clear()
            self._camera_congestion_detectors.clear()
            self._camera_congestion.clear()
            self._camera_incident_detectors.clear()
            self._live_plates.clear()
            self._alpr_seen.clear()
            self._alpr_total = 0
            self._last_counts.clear()
            self._total_vehicles = 0
            self._cycle_count = 0
            self._last_result = None
            self._last_error = None

            self._running = True
            self._thread = threading.Thread(
                target=self._monitor_loop,
                name="camera_monitor_loop",
                daemon=True,
            )
            self._thread.start()
            logger.info(
                f"ExternalCameraLiveMonitor started — "
                f"mode={source_mode}, device={device}, "
                f"limit={resolved_limit} cam(s), url={resolved_url}"
            )

        return self.get_status()

    def stop(self) -> None:
        """Gracefully stop the monitoring thread."""
        with self._lock:
            if not self._running:
                return
            self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=10.0)
        logger.info("ExternalCameraLiveMonitor stopped")

    # ── Internal loop ───────────────────────────────────────────────────────

    def _monitor_loop(self) -> None:
        """
        Main background loop: collect → preprocess → infer → analyze → buffer → sleep.

        GPU mode  : parallel inference across up to 4 cameras.
        CPU mode  : sequential inference on 1 camera only.
        """
        from services.inference import run_inference
        from fisheye import apply_fisheye
        from speed_estimator import SpeedEstimator
        from congestion_detector import CongestionDetector
        from utils.helpers import draw_detections_on_image
        from line_counter import line_counter
        from incident_detector import IncidentDetector
        from alpr import plate_recognizer
        import db as database

        cfg = self._config

        while self._running:
            cycle_start = time.time()

            try:
                device   = cfg["device"]
                is_gpu   = device != "cpu"
                cam_limit = cfg["camera_limit"]
                interval_s = cfg["interval"]

                # ── Step 1: Collect snapshots ──────────────────────────────
                entries: list[CameraEntry] = []

                if cfg["source_mode"] == "snapshot" and cfg["source_url"]:
                    raw = extract_camera_entries(cfg["source_url"], limit=cam_limit)
                    if is_gpu:
                        entries = fetch_snapshots_parallel(raw, max_workers=min(cam_limit, 4))
                    else:
                        # CPU: only first camera
                        entries = fetch_snapshots_parallel(raw[:1], max_workers=1)

                elif cfg["source_mode"] == "stream" and cfg["stream_url"]:
                    frame = capture_stream_frame(cfg["stream_url"])
                    if frame:
                        e = CameraEntry(url=cfg["stream_url"],
                                        name="Live Stream", camera_index=0)
                        e.snapshot = frame
                        entries = [e]

                if not entries:
                    logger.debug("No camera entries available; waiting...")
                    time.sleep(interval_s)
                    continue

                # ── Step 2: Fisheye preprocessing ─────────────────────────
                prep = cfg["preprocessing"]
                for entry in entries:
                    if entry.snapshot and prep.get("enabled", False):
                        entry.snapshot = apply_fisheye(
                            entry.snapshot,
                            strength=prep.get("strength", Config.FISHEYE_STRENGTH),
                            radius=prep.get("radius",   Config.FISHEYE_RADIUS),
                            effect=prep.get("effect",   Config.FISHEYE_EFFECT),
                        )

                valid = [e for e in entries if e.snapshot is not None]

                # ── Step 3: YOLO Inference ─────────────────────────────────
                # GPU → all cameras in parallel | CPU → first camera only
                inference_results: list[tuple] = []  # (CameraEntry, result_dict)

                if is_gpu and len(valid) > 1:
                    def _infer_gpu(entry: CameraEntry):
                        r = run_inference(
                            image=entry.snapshot,
                            model_key=cfg["model_key"],
                            conf=cfg["conf"],
                            iou=cfg["iou"],
                            device=device,
                        )
                        return entry, r

                    with ThreadPoolExecutor(max_workers=len(valid)) as pool:
                        futs = {pool.submit(_infer_gpu, e): e for e in valid}
                        for fut in as_completed(futs):
                            try:
                                inference_results.append(fut.result())
                            except Exception as exc:
                                logger.warning(f"GPU inference error: {exc}")
                else:
                    # CPU: single camera, sequential
                    for entry in valid[:1]:
                        r = run_inference(
                            image=entry.snapshot,
                            model_key=cfg["model_key"],
                            conf=cfg["conf"],
                            iou=cfg["iou"],
                            device=device,
                        )
                        inference_results.append((entry, r))

                # ── Step 4: Per-camera analytics ──────────────────────────
                camera_labels: dict[int, str] = {}
                all_detections: list[dict] = []
                cameras_info:   list[dict] = []

                for entry, result in inference_results:
                    cam_key = entry.name or f"cam_{entry.camera_index}"
                    dets    = result["detections"]
                    count   = result["total"]
                    w       = result["image_width"]
                    h       = result["image_height"]

                    self._last_counts[cam_key] = count
                    all_detections.extend(dets)

                    # Centroid tracking → stable track IDs
                    if cam_key not in self._camera_trackers:
                        self._camera_trackers[cam_key] = _CentroidTracker()
                    tracked, det_assignments = self._camera_trackers[cam_key].update(dets)

                    # Speed estimation
                    fps_equiv = 1.0 / max(interval_s, 0.5)
                    if cam_key not in self._camera_speed_estimators:
                        self._camera_speed_estimators[cam_key] = SpeedEstimator(
                            fps=fps_equiv,
                            scale_factor=Config.SPEED_SCALE_FACTOR,
                        )
                    speed_est = self._camera_speed_estimators[cam_key]
                    track_speeds: dict[int, float] = {}
                    # Map det_index → class_name for violation reporting
                    _tid_to_class: dict[int, str] = {
                        det_assignments[di]: dets[di].get("class_name", "unknown")
                        for di in range(len(dets)) if di in det_assignments
                    }
                    for tid, (cx, cy) in tracked.items():
                        track_speed = speed_est.update_single(
                            tid, cx, cy, self._cycle_count,
                            _tid_to_class.get(tid, "unknown"),
                        )
                        # Speed violation check (built into SpeedEstimator)
                        violation = speed_est._violation_checker.check(
                            tid, track_speed, self._cycle_count,
                        )
                        if violation:
                            vtype = _tid_to_class.get(tid, "unknown")
                            try:
                                database.save_speed_violation(
                                    cam_key, tid, vtype,
                                    track_speed, speed_est.speed_limit_kmh, "",
                                )
                                alert_manager.fire_speed_violation_alert(
                                    tid, track_speed, speed_est.speed_limit_kmh,
                                    cam_key, vtype,
                                )
                            except Exception as _sv_exc:
                                logger.warning("save_speed_violation error: %s", _sv_exc)
                        if track_speed > 0:
                            track_speeds[tid] = track_speed
                    avg_speed = speed_est.get_average_speed()
                    max_speed = speed_est.get_max_speed()

                    # Line counter — update per tracked detection
                    for det_idx, det in enumerate(dets):
                        tid = det_assignments.get(det_idx)
                        if tid is None:
                            continue
                        cx_lc, cy_lc = tracked.get(tid, (0, 0))
                        line_counter.update(
                            tid, cx_lc, cy_lc,
                            det.get("class_name", "unknown"),
                            self._cycle_count, w, h,
                        )
                    # Flush crossings → DB
                    for crossing in line_counter.pop_recent_crossings():
                        try:
                            from datetime import datetime as _dt
                            hour_bucket = _dt.utcnow().strftime("%Y-%m-%d %H:00")
                            database.save_traffic_count(
                                crossing["camera_id"], crossing["direction"],
                                crossing["class_name"], hour_bucket, 1,
                            )
                        except Exception as _lc_exc:
                            logger.warning("save_traffic_count error: %s", _lc_exc)

                    # Incident detection
                    if cam_key not in self._camera_incident_detectors:
                        self._camera_incident_detectors[cam_key] = IncidentDetector(
                            camera_id=cam_key, fps=fps_equiv,
                        )
                    incident_det = self._camera_incident_detectors[cam_key]
                    boxes_inc = {}
                    labels_inc = {}
                    for det_idx, det in enumerate(dets):
                        tid = det_assignments.get(det_idx)
                        if tid is None:
                            continue
                        boxes_inc[tid] = tuple(det["bbox"])
                        labels_inc[tid] = det.get("class_name", "unknown")
                    if boxes_inc:
                        new_incidents = incident_det.analyze(
                            boxes=boxes_inc, labels=labels_inc,
                            frame_idx=self._cycle_count, fps=fps_equiv,
                        )
                        for incident in new_incidents:
                            try:
                                database.save_incident(incident)
                                alert_manager.fire_incident_alert(
                                    incident["incident_type"],
                                    incident["description"],
                                    cam_key,
                                    incident.get("severity", "medium"),
                                )
                            except Exception as _inc_exc:
                                logger.warning("save_incident error: %s", _inc_exc)

                    # Congestion detection
                    if cam_key not in self._camera_congestion_detectors:
                        self._camera_congestion_detectors[cam_key] = CongestionDetector(w, h)
                    boxes     = {i: d["bbox"] for i, d in enumerate(dets)}
                    congestion = self._camera_congestion_detectors[cam_key].analyze(boxes)
                    self._camera_congestion[cam_key] = congestion

                    detection_speeds: dict[int, float] = {}
                    detections_with_speed: list[dict] = []
                    for det_idx, det in enumerate(dets):
                        det_copy = dict(det)
                        tid = det_assignments.get(det_idx)
                        speed_kmh = track_speeds.get(tid, 0.0) if tid is not None else 0.0
                        if speed_kmh > 0:
                            detection_speeds[det_idx] = speed_kmh
                            det_copy["speed_kmh"] = speed_kmh
                        detections_with_speed.append(det_copy)

                    # ── ALPR: nhận diện biển số trên feed live ──────
                    # Chạy OCR trên ảnh GỐC (entry.snapshot trước khi vẽ), throttle
                    # theo alpr_every chu kỳ để không làm chậm vòng lặp live.
                    cam_plates: list[dict] = self._run_live_alpr(
                        plate_recognizer, entry.snapshot, dets, cam_key, database,
                    )

                    # Annotate frame with per-vehicle speed labels
                    annotated = draw_detections_on_image(
                        entry.snapshot, detections_with_speed, speed_data=detection_speeds,
                    )
                    # Draw recognised plates (gold boxes + text) on top
                    if cam_plates:
                        annotated = _draw_plates_on_pil(annotated, cam_plates)
                    entry.snapshot = annotated
                    self._stream_frames[f"camera_{entry.camera_index}"] = \
                        _pil_to_jpeg_bytes(annotated, quality=92)

                    # Collage label: "CamName | 12v | H | 45km/h"
                    cong_initial = congestion["level"][0].upper()
                    speed_label = f"{max_speed:.0f}k" if max_speed > 0 else (
                        f"{avg_speed:.0f}k" if avg_speed > 0 else "—k"
                    )
                    label = f"{entry.name}|{count}v|{cong_initial}|{speed_label}"
                    camera_labels[entry.camera_index] = label

                    # ── Alerts ──────────────────────────────────────
                    # 1) High density
                    alert_manager.check_and_alert(count, camera_source=cam_key)
                    # 2) High congestion
                    if congestion["level"] == "high":
                        alert_manager.check_and_alert(
                            count,
                            camera_source=f"{cam_key}:congestion",
                            alert_type="high_congestion",
                        )

                    cameras_info.append({
                        "name":          cam_key,
                        "index":         entry.camera_index,
                        "count":         count,
                        "avg_speed_kmh": avg_speed,
                        "max_speed_kmh": max_speed,
                        "vehicle_speeds": [
                            {
                                "class_name": d.get("class_name", "unknown"),
                                "speed_kmh":  d.get("speed_kmh", 0.0),
                            }
                            for d in detections_with_speed
                            if d.get("speed_kmh", 0.0) > 0
                        ],
                        "congestion":    congestion,
                        "annotated":     f"/api/external-camera/snapshot/{entry.camera_index}",
                        "title":         cam_key,
                        "total_objects": count,
                        "plates":        cam_plates,
                    })

                # ── Step 5: Global analytics ───────────────────────────────
                self._total_vehicles = sum(self._last_counts.values())
                density_analyzer.record(self._total_vehicles)

                if all_detections and inference_results:
                    first_snap = inference_results[0][0].snapshot
                    if first_snap:
                        heatmap.update(all_detections, first_snap.width, first_snap.height)

                # ── Step 6: Build collage overview ────────────────────────
                collage = build_camera_collage(
                    entries,
                    cell_width=320, cell_height=240,
                    cols=2, labels=camera_labels,
                )
                self._stream_frames["overview"] = _pil_to_jpeg_bytes(collage)

                # ── Step 7: Summarise results ─────────────────────────────
                speeds      = [c["avg_speed_kmh"] for c in cameras_info if c["avg_speed_kmh"] > 0]
                max_speeds  = [c["max_speed_kmh"] for c in cameras_info if c["max_speed_kmh"] > 0]
                cong_levels = [c["congestion"]["level"] for c in cameras_info]
                cong_scores = [c["congestion"]["score"] for c in cameras_info]
                worst_cong  = ("high"     if "high"     in cong_levels else
                               "moderate" if "moderate" in cong_levels else "low")

                from datetime import datetime
                elapsed_ms = (time.time() - cycle_start) * 1000

                self._last_result = {
                    "camera_count":   len(cameras_info),
                    "cameras":        cameras_info,
                    "total_vehicles": self._total_vehicles,
                    "overview":       "/api/external-camera/snapshot/overview",
                    "summary": {
                        "class_counts":  {},
                        "total_objects": self._total_vehicles,
                        "inference_ms":  round(elapsed_ms, 0),
                        "camera_count":  len(cameras_info),
                    },
                    "preprocessing": {
                        "enabled": bool(cfg["preprocessing"].get("enabled")),
                        "source_layout": cfg.get("source_layout", "normal"),
                    },
                    "model": {"loaded_from_name": cfg.get("model_key", "best")},
                    "speed_summary": {
                        "avg_kmh": round(sum(speeds) / len(speeds), 1) if speeds else 0.0,
                        "max_kmh": max(max_speeds, default=0.0),
                    },
                    "congestion_summary": {
                        "level":     worst_cong,
                        "avg_score": round(sum(cong_scores) / max(len(cong_scores), 1), 2),
                    },
                    "alpr": {
                        "enabled":   bool(cfg.get("alpr_enabled")),
                        "available": plate_recognizer.is_available(),
                        "total":     self._alpr_total,
                        "recent":    list(reversed(self._live_plates[-12:])),
                    },
                }
                self._last_error            = None
                self._last_cycle_duration_ms = round(elapsed_ms, 1)
                self._actual_cycle_fps       = round(1000 / elapsed_ms, 2) if elapsed_ms > 0 else 0.0
                self._cycle_count           += 1
                self._last_updated_at        = datetime.now().isoformat()

                logger.info(
                    f"[Cycle {self._cycle_count}] "
                    f"{'GPU' if is_gpu else 'CPU'} | "
                    f"{len(inference_results)} cam(s) | "
                    f"vehicles={self._total_vehicles} | "
                    f"congestion={worst_cong} | "
                    f"avg_speed={self._last_result['speed_summary']['avg_kmh']}km/h | "
                    f"{elapsed_ms:.0f}ms"
                )

            except Exception as exc:
                logger.error(f"Monitor loop error: {exc}", exc_info=True)
                self._last_error   = str(exc)
                self._cycle_count += 1

            elapsed    = time.time() - cycle_start
            sleep_time = max(0.0, cfg["interval"] - elapsed)
            time.sleep(sleep_time)

    # ── ALPR (license plate) on live feed ───────────────────────────────────

    def _run_live_alpr(self, recognizer, snapshot, dets, cam_key, database) -> list[dict]:
        """
        Nhận diện biển số trên 1 snapshot live (có throttle theo alpr_every chu kỳ).

        - Chỉ OCR vùng xe (Car/Bus/Truck/Motorbike), giới hạn số crop để giữ tốc độ.
        - Lưu DB với camera_id=cam_key (dedup theo cửa sổ chu kỳ để tránh trùng).
        - Trả list plates {plate, confidence, bbox, vehicle_type} để vẽ lên frame.
        """
        cfg = self._config
        if not cfg.get("alpr_enabled") or snapshot is None:
            return []
        every = max(1, int(cfg.get("alpr_every", Config.ALPR_LIVE_EVERY)))
        if self._cycle_count % every != 0:
            return []
        if not recognizer.is_available():
            return []

        try:
            # PIL (RGB) → BGR ndarray cho OCR
            bgr = np.array(snapshot.convert("RGB"))[:, :, ::-1].copy()
            vehicle_boxes: list[dict] = []
            for d in dets:
                if d.get("class_name") in ("Car", "Bus", "Truck", "Motorbike"):
                    bbox = d.get("bbox")
                    if bbox and len(bbox) >= 4:
                        vehicle_boxes.append({"bbox": bbox,
                                              "vehicle_type": d["class_name"]})
            vehicle_boxes = vehicle_boxes[:max(1, int(Config.ALPR_LIVE_MAX_VEH))]
            plates = recognizer.recognize(bgr, vehicle_boxes or None)
        except Exception as exc:
            logger.debug("live ALPR error on %s: %s", cam_key, exc)
            return []

        from datetime import datetime as _dt
        dedup_window = max(20, every * 10)   # số chu kỳ coi là "trùng"
        for p in plates:
            key = f"{cam_key}|{p['plate']}"
            last = self._alpr_seen.get(key)
            if last is not None and (self._cycle_count - last) < dedup_window:
                continue  # vẫn vẽ lên frame nhưng không lưu lại
            self._alpr_seen[key] = self._cycle_count
            try:
                database.save_license_plate(
                    plate_text=p["plate"], confidence=p["confidence"],
                    vehicle_type=p.get("vehicle_type", "unknown"),
                    camera_id=cam_key, detection_id="live",
                    bbox=p.get("bbox", []),
                )
                self._alpr_total += 1
            except Exception as exc:
                logger.warning("save_license_plate (live) failed: %s", exc)
            self._live_plates.append({
                "plate":        p["plate"],
                "confidence":   p["confidence"],
                "vehicle_type": p.get("vehicle_type", "unknown"),
                "camera":       cam_key,
                "time":         _dt.now().strftime("%H:%M:%S"),
            })
        if len(self._live_plates) > 60:
            self._live_plates = self._live_plates[-60:]
        return plates

    # ── Frame / stream access ───────────────────────────────────────────────

    def get_frame(self, view: str = "overview") -> Optional[bytes]:
        """Return JPEG bytes for the given view key."""
        return self._stream_frames.get(view)

    def mjpeg_stream(self, view: str = "overview") -> Generator[bytes, None, None]:
        """
        MJPEG generator for Flask streaming response.
        Format: multipart/x-mixed-replace; boundary=frame
        """
        while self._running:
            frame_bytes = self.get_frame(view)
            payload = frame_bytes if frame_bytes else _placeholder_jpeg()
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n"
                + payload +
                b"\r\n"
            )
            time.sleep(0.1)   # ~10 fps max

    def get_status(self) -> dict:
        """Return current monitor status (shape matches frontend expectations)."""
        interval = self._config.get("interval", Config.EXT_CAM_INTERVAL)
        result   = self._last_result or {}
        return {
            "running":                self._running,
            "status":                 "active" if self._running else "stopped",
            "camera_counts":          dict(self._last_counts),
            "total_vehicles":         self._total_vehicles,
            "active_cameras":         len(self._last_counts),
            "cycle_count":            self._cycle_count,
            "last_updated_at":        self._last_updated_at,
            "last_cycle_duration_ms": self._last_cycle_duration_ms,
            "actual_cycle_fps":       self._actual_cycle_fps,
            "interval_seconds":       interval,
            "stream_ready":           bool(self._stream_frames.get("overview")),
            "last_result":            result,
            "error":                  self._last_error,
            "speed_summary":          result.get("speed_summary",
                                                  {"avg_kmh": 0.0, "max_kmh": 0.0}),
            "congestion_summary":     result.get("congestion_summary",
                                                  {"level": "low", "avg_score": 0.0}),
            "alpr":                   result.get("alpr", {
                                          "enabled":   bool(self._config.get("alpr_enabled")),
                                          "available": False,
                                          "total":     self._alpr_total,
                                          "recent":    list(reversed(self._live_plates[-12:])),
                                      }),
            "config": {k: v for k, v in self._config.items() if k != "preprocessing"},
        }


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _draw_plates_on_pil(img: Image.Image, plates: list[dict]) -> Image.Image:
    """Vẽ khung biển số (vàng) + text lên PIL image."""
    try:
        from PIL import ImageDraw
        draw = ImageDraw.Draw(img)
        for p in plates:
            bbox = p.get("bbox") or []
            if len(bbox) < 4:
                continue
            x1, y1, x2, y2 = (int(v) for v in bbox[:4])
            label = f"{p.get('plate', '')} {float(p.get('confidence', 0)):.2f}"
            draw.rectangle([x1, y1, x2, y2], outline=(255, 215, 0), width=2)
            tw = 7 * len(label) + 4
            draw.rectangle([x1, max(0, y1 - 14), x1 + tw, y1], fill=(255, 215, 0))
            draw.text((x1 + 2, max(0, y1 - 13)), label, fill=(0, 0, 0))
    except Exception as exc:
        logger.debug("_draw_plates_on_pil error: %s", exc)
    return img


def _pil_to_jpeg_bytes(img: Image.Image, quality: int = 80) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def _placeholder_jpeg() -> bytes:
    """Black 320×240 placeholder frame."""
    return _pil_to_jpeg_bytes(Image.new("RGB", (320, 240), color=(15, 15, 25)))


# Singleton
camera_monitor = ExternalCameraLiveMonitor()

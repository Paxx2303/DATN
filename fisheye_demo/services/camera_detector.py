from __future__ import annotations

import logging
import os
import time
import threading
import uuid
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from PIL import Image

try:
    from config import AppSettings, normalize_external_camera_source_mode, CLASS_NAMES, CLASS_COLORS
    from utils.helpers import utc_now_iso, utc_now_iso_ms, apply_preprocessing
    from services.model_registry import ModelRegistry
    from services.storage import create_result_dir, write_record, persist_recent_image
    from services.inference import run_inference
    from recent_image_store import RecentImageStore
    from external_camera_detector import (
        build_camera_collage,
        capture_stream_frame,
        download_camera_snapshot,
        extract_camera_entries,
    )
except ImportError:
    from fisheye_demo.config import AppSettings, normalize_external_camera_source_mode, CLASS_NAMES, CLASS_COLORS
    from fisheye_demo.utils.helpers import utc_now_iso, utc_now_iso_ms, apply_preprocessing
    from fisheye_demo.services.model_registry import ModelRegistry
    from fisheye_demo.services.storage import create_result_dir, write_record, persist_recent_image
    from fisheye_demo.services.inference import run_inference
    from fisheye_demo.recent_image_store import RecentImageStore
    from fisheye_demo.external_camera_detector import (
        build_camera_collage,
        capture_stream_frame,
        download_camera_snapshot,
        extract_camera_entries,
    )

logger = logging.getLogger("fisheye_demo.services.camera_detector")


def read_stream_frame_from_capture(capture) -> Image.Image:
    try:
        import cv2
    except Exception as exc:
        raise RuntimeError(f"OpenCV import failed while reading stream: {exc}") from exc

    ok, frame = capture.read()
    if not ok or frame is None:
        raise RuntimeError("Unable to read frame from live stream.")
    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    image = Image.fromarray(frame_rgb, mode="RGB")
    image.load()
    return image


def save_external_camera_record(
    settings: AppSettings,
    recent_image_store: RecentImageStore,
    source_url: str,
    preprocessing: dict[str, Any],
    conf_threshold: float,
    iou_threshold: float,
    model_info: dict[str, Any],
    cameras: list[dict[str, Any]],
    average_inference_ms: float,
    result_dir: Path,
    overview_image: Image.Image,
) -> dict[str, Any]:
    artifacts = {
        "overview_annotated": "overview_annotated.jpg",
        "metadata": "metadata.json",
    }

    class_totals: dict[str, int] = {}
    for index, camera in enumerate(cameras, start=1):
        artifacts[f"camera_{index}_original"] = f"camera_{index}_original.jpg"
        artifacts[f"camera_{index}_annotated"] = f"camera_{index}_annotated.jpg"
        if camera["preprocessing_enabled"]:
            artifacts[f"camera_{index}_preprocessed"] = f"camera_{index}_preprocessed.jpg"

        for class_name, count in camera["class_counts"].items():
            class_totals[class_name] = class_totals.get(class_name, 0) + count

    record = {
        "id": result_dir.name,
        "task": "detect",
        "media_type": "external_camera_grid",
        "filename": source_url,
        "created_at": utc_now_iso(),
        "source_layout": preprocessing["source_layout"],
        "preprocessing": preprocessing,
        "parameters": {
            "confidence_threshold": round(conf_threshold, 3),
            "iou_threshold": round(iou_threshold, 3),
        },
        "model": {
            "source": model_info.get("source"),
            "loaded_from": model_info.get("loaded_from"),
            "loaded_from_name": model_info.get("loaded_from_name"),
            "device": model_info.get("device"),
            "selected_key": model_info.get("selected_key"),
            "selected_name": model_info.get("selected_name"),
        },
        "summary": {
            "camera_count": len(cameras),
            "total_objects": sum(camera["total_objects"] for camera in cameras),
            "class_counts": class_totals,
            "inference_ms": round(average_inference_ms, 2),
        },
        "cameras": [
            {
                "index": camera["index"],
                "title": camera["title"],
                "youtube_id": camera["youtube_id"],
                "snapshot_url": camera["snapshot_url"],
                "stream_url": camera.get("stream_url"),
                "total_objects": camera["total_objects"],
                "class_counts": camera["class_counts"],
                "detections": camera["detections"],
            }
            for camera in cameras
        ],
        "artifacts": artifacts,
    }
    write_record(result_dir, record)
    persist_recent_image(
        recent_image_store,
        record=record,
        image_role="overview_annotated",
        filename=artifacts["overview_annotated"],
        image=overview_image,
    )

    # ── Persist external camera detection to DB + GCS ─────────────────────────
    gcs_urls: dict[str, str] = {}
    try:
        try:
            from cloud_storage import upload_pil_image, build_object_name, is_enabled as gcs_enabled
        except ImportError:
            from fisheye_demo.cloud_storage import upload_pil_image, build_object_name, is_enabled as gcs_enabled

        if gcs_enabled():
            obj_name = build_object_name(record["id"], "overview_annotated.jpg")
            gcs_result = upload_pil_image(overview_image, obj_name,
                                          detection_id=record["id"], image_role="overview_annotated")
            if gcs_result:
                gcs_urls["overview_annotated"] = gcs_result["gcs_public_url"]
                try:
                    try:
                        from db import insert_cloud_snapshot
                    except ImportError:
                        from fisheye_demo.db import insert_cloud_snapshot
                    insert_cloud_snapshot(
                        detection_id=record["id"],
                        gcs_bucket=gcs_result["gcs_bucket"],
                        gcs_object_name=gcs_result["gcs_object_name"],
                        gcs_public_url=gcs_result["gcs_public_url"],
                        image_role="overview_annotated",
                        expires_at=gcs_result["expires_at"],
                    )
                except Exception:
                    pass
    except Exception:
        pass

    try:
        try:
            from db import insert_detection, upsert_traffic_counts
        except ImportError:
            from fisheye_demo.db import insert_detection, upsert_traffic_counts
        insert_detection(record, gcs_urls=gcs_urls)
        class_totals_for_db = record.get("summary", {}).get("class_counts") or {}
        upsert_traffic_counts(class_totals_for_db, camera_source="external_camera")
    except Exception:
        pass

    if gcs_urls:
        record["gcs_urls"] = gcs_urls

    return record


def process_external_camera_frames(
    registry: ModelRegistry,
    settings: AppSettings,
    recent_image_store: RecentImageStore,
    source_label: str,
    camera_inputs: list[dict[str, Any]],
    preprocessing: dict[str, Any],
    conf_threshold: float,
    iou_threshold: float,
    model_key: str | None,
    persist_result: bool,
) -> dict[str, Any]:
    result_dir: Path | None = None

    try:
        if persist_result:
            _, result_dir = create_result_dir(settings)

        cameras: list[dict[str, Any]] = []
        model_info: dict[str, Any] = {}
        inference_times: list[float] = []

        for index, camera_input in enumerate(camera_inputs, start=1):
            original_image = camera_input["original_image"].convert("RGB")
            preprocessed_image = apply_preprocessing(original_image, preprocessing)
            annotated_image, detections, class_counts, inference_ms, loaded_model_info = run_inference(
                registry,
                settings,
                preprocessed_image,
                conf_threshold,
                iou_threshold,
                model_key=model_key,
            )
            model_info = loaded_model_info
            inference_times.append(inference_ms)

            if result_dir is not None:
                original_name = f"camera_{index}_original.jpg"
                annotated_name = f"camera_{index}_annotated.jpg"
                original_image.save(result_dir / original_name, format="JPEG", quality=90)
                annotated_image.save(result_dir / annotated_name, format="JPEG", quality=90)
                if preprocessing["enabled"]:
                    preprocessed_name = f"camera_{index}_preprocessed.jpg"
                    preprocessed_image.save(result_dir / preprocessed_name, format="JPEG", quality=90)

            cameras.append(
                {
                    "index": index,
                    "title": str(camera_input.get("title") or f"Camera {index}"),
                    "youtube_id": str(camera_input.get("youtube_id") or ""),
                    "snapshot_url": str(camera_input.get("snapshot_url") or ""),
                    "stream_url": str(camera_input.get("stream_url") or ""),
                    "original_image": original_image,
                    "preprocessed_image": preprocessed_image,
                    "annotated_image": annotated_image,
                    "preprocessing_enabled": preprocessing["enabled"],
                    "detections": detections,
                    "class_counts": class_counts,
                    "total_objects": len(detections),
                }
            )

        overview_image = cameras[0]["annotated_image"].copy() if len(cameras) == 1 else build_camera_collage(cameras)
        average_inference_ms = sum(inference_times) / len(inference_times) if inference_times else 0.0
        summary = build_external_camera_summary(cameras, average_inference_ms)

        record = None
        if result_dir is not None:
            overview_image.save(result_dir / "overview_annotated.jpg", format="JPEG", quality=90)
            record = save_external_camera_record(
                settings,
                recent_image_store,
                source_label,
                preprocessing,
                conf_threshold,
                iou_threshold,
                model_info,
                cameras,
                average_inference_ms,
                result_dir,
                overview_image,
            )

        # Trích xuất ảnh bytes để truyền tải realtime (mjpeg/overview)
        import io as _io
        buffer = _io.BytesIO()
        overview_image.save(buffer, format="JPEG", quality=85)
        overview_bytes = buffer.getvalue()

        stream_frames = {"overview": overview_bytes}
        for index, camera in enumerate(cameras, start=1):
            cam_buffer = _io.BytesIO()
            camera["annotated_image"].save(cam_buffer, format="JPEG", quality=85)
            stream_frames[f"camera_{index}"] = cam_buffer.getvalue()

        return {
            "source_url": source_label,
            "camera_count": len(cameras),
            "overview": overview_bytes,
            "stream_frames": stream_frames,
            "summary": summary,
            "preprocessing": preprocessing,
            "model": model_info,
            "cameras": [
                {
                    "index": camera["index"],
                    "title": camera["title"],
                    "youtube_id": camera["youtube_id"],
                    "snapshot_url": camera["snapshot_url"],
                    "stream_url": camera.get("stream_url"),
                    "total_objects": camera["total_objects"],
                    "class_counts": camera["class_counts"],
                }
                for camera in cameras
            ],
            "record": record,
        }
    except Exception as exc:
        logger.exception("process_external_camera_frames failed: label=%s", source_label)
        raise exc


def build_external_camera_summary(cameras: list[dict[str, Any]], average_inference_ms: float) -> dict[str, Any]:
    class_totals: dict[str, int] = {}
    for camera in cameras:
        for class_name, count in camera["class_counts"].items():
            class_totals[class_name] = class_totals.get(class_name, 0) + count

    return {
        "camera_count": len(cameras),
        "total_objects": sum(camera["total_objects"] for camera in cameras),
        "class_counts": class_totals,
        "inference_ms": round(average_inference_ms, 2),
    }


def run_external_camera_pipeline(
    registry: ModelRegistry,
    settings: AppSettings,
    recent_image_store: RecentImageStore,
    source_mode: str,
    source_url: str,
    stream_url: str,
    camera_limit: int,
    preprocessing: dict[str, Any],
    conf_threshold: float,
    iou_threshold: float,
    model_key: str | None,
    persist_result: bool,
) -> dict[str, Any]:
    normalized_mode = normalize_external_camera_source_mode(source_mode, stream_url or source_url)

    if normalized_mode == "stream":
        active_stream_url = stream_url or source_url
        image = capture_stream_frame(active_stream_url)
        camera_inputs = [
            {
                "title": "Stream camera 1",
                "youtube_id": "",
                "snapshot_url": "",
                "stream_url": active_stream_url,
                "original_image": image,
            }
        ]
        return process_external_camera_frames(
            registry,
            settings,
            recent_image_store,
            active_stream_url,
            camera_inputs,
            preprocessing,
            conf_threshold,
            iou_threshold,
            model_key,
            persist_result,
        )

    entries = extract_camera_entries(source_url, limit=camera_limit)
    if not entries:
        raise ValueError("No camera entries found from the external source.")

    camera_inputs = [
        {
            "title": entry.title,
            "youtube_id": entry.youtube_id,
            "snapshot_url": entry.snapshot_url,
            "stream_url": "",
            "original_image": download_camera_snapshot(entry),
        }
        for entry in entries
    ]
    return process_external_camera_frames(
        registry,
        settings,
        recent_image_store,
        source_url,
        camera_inputs,
        preprocessing,
        conf_threshold,
        iou_threshold,
        model_key,
        persist_result,
    )


class ExternalCameraLiveMonitor:
    def __init__(
        self,
        settings: AppSettings,
        registry: ModelRegistry,
        recent_image_store: RecentImageStore,
    ) -> None:
        self.settings = settings
        self.registry = registry
        self.recent_image_store = recent_image_store
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._stream_frames: dict[str, bytes] = {}
        self._stream_frame_id = 0
        self._session_id: str | None = None
        self._state: dict[str, Any] = {
            "running": False,
            "status": "idle",
            "source_mode": settings.external_camera_source_mode,
            "source_url": settings.external_camera_url,
            "stream_url": settings.external_camera_stream_url,
            "camera_limit": settings.external_camera_limit,
            "interval_seconds": settings.external_camera_live_interval_seconds,
            "conf_threshold": settings.default_conf,
            "iou_threshold": settings.default_iou,
            "model_key": registry.status_snapshot().get("selected_key"),
            "preprocessing": {
                "source_layout": "normal",
                "enabled": True,
                "strength": settings.camera_fisheye_strength,
                "radius": settings.camera_fisheye_radius,
                "effect": settings.camera_fisheye_effect,
                "center_x_ratio": settings.camera_fisheye_center_x,
                "center_y_ratio": settings.camera_fisheye_center_y,
                "axis_scale_x": settings.camera_fisheye_axis_scale_x,
                "axis_scale_y": settings.camera_fisheye_axis_scale_y,
                "full_frame": settings.camera_fisheye_full_frame,
                "profile": "external_camera",
            },
            "started_at": None,
            "last_updated_at": None,
            "error": None,
            "cycle_count": 0,
            "last_cycle_duration_ms": None,
            "actual_cycle_fps": None,
            "stream_ready": False,
            "last_result": None,
        }

    def status_snapshot(self) -> dict[str, Any]:
        with self._lock:
            return json.loads(json.dumps(self._state))

    def get_stream_frame_snapshot(self, view: str) -> tuple[int, bytes | None, bool]:
        with self._lock:
            return self._stream_frame_id, self._stream_frames.get(view), bool(self._state.get("running"))

    def start(
        self,
        source_mode: str,
        source_url: str,
        stream_url: str,
        camera_limit: int,
        preprocessing: dict[str, Any],
        conf_threshold: float,
        iou_threshold: float,
        model_key: str | None,
        interval_seconds: float,
    ) -> dict[str, Any]:
        with self._lock:
            already_running = self._thread is not None and self._thread.is_alive()
            if already_running:
                logger.info(
                    "Live monitor start ignored because worker is already running: source=%s cycle_count=%s status=%s",
                    self._state.get("source_url"),
                    self._state.get("cycle_count"),
                    self._state.get("status"),
                )
                return json.loads(json.dumps(self._state))

            self._stop_event.clear()
            self._state.update(
                {
                    "source_mode": source_mode,
                    "source_url": source_url,
                    "stream_url": stream_url,
                    "camera_limit": camera_limit,
                    "interval_seconds": interval_seconds,
                    "conf_threshold": round(conf_threshold, 3),
                    "iou_threshold": round(iou_threshold, 3),
                    "model_key": model_key,
                    "preprocessing": dict(preprocessing),
                    "error": None,
                    "status": "starting",
                    "running": True,
                    "started_at": utc_now_iso_ms(),
                    "last_updated_at": None,
                    "cycle_count": 0,
                    "last_cycle_duration_ms": None,
                    "actual_cycle_fps": None,
                    "stream_ready": False,
                    "last_result": None,
                }
            )
            self._stream_frames = {}
            self._stream_frame_id = 0
            self._session_id = uuid.uuid4().hex
            worker = threading.Thread(
                target=self._worker_loop,
                kwargs={
                    "source_mode": source_mode,
                    "source_url": source_url,
                    "stream_url": stream_url,
                    "camera_limit": camera_limit,
                    "preprocessing": dict(preprocessing),
                    "conf_threshold": conf_threshold,
                    "iou_threshold": iou_threshold,
                    "model_key": model_key,
                    "interval_seconds": interval_seconds,
                },
                daemon=True,
                name="external-camera-live-monitor",
            )
            self._thread = worker
            logger.info(
                "Live monitor start requested: source=%s camera_limit=%s interval=%.3fs conf=%.2f iou=%.2f fisheye=%s",
                source_url,
                camera_limit,
                interval_seconds,
                conf_threshold,
                iou_threshold,
                preprocessing.get("enabled"),
            )
            worker.start()

            # Tạo live session record trong DB
            try:
                try:
                    from db import insert_live_session
                except ImportError:
                    from fisheye_demo.db import insert_live_session
                insert_live_session(self._session_id, source_url, source_mode, conf_threshold, iou_threshold)
            except Exception:
                pass

            return json.loads(json.dumps(self._state))

    def stop(self) -> dict[str, Any]:
        thread = None
        with self._lock:
            thread = self._thread
            self._stop_event.set()
            self._state["status"] = "stopping" if thread and thread.is_alive() else "stopped"
            logger.info(
                "Live monitor stop requested: cycle_count=%s last_cycle_ms=%s status=%s",
                self._state.get("cycle_count"),
                self._state.get("last_cycle_duration_ms"),
                self._state.get("status"),
            )

        if thread and thread.is_alive():
            thread.join(timeout=5)

        with self._lock:
            self._thread = None
            self._state["running"] = False
            self._state["status"] = "stopped"
            session_id_to_close = self._session_id
            self._session_id = None

        if session_id_to_close:
            try:
                try:
                    from db import close_live_session
                except ImportError:
                    from fisheye_demo.db import close_live_session
                close_live_session(session_id_to_close)
            except Exception:
                pass

        with self._lock:
            return json.loads(json.dumps(self._state))

    def _worker_loop(
        self,
        *,
        source_mode: str,
        source_url: str,
        stream_url: str,
        camera_limit: int,
        preprocessing: dict[str, Any],
        conf_threshold: float,
        iou_threshold: float,
        model_key: str | None,
        interval_seconds: float,
    ) -> None:
        try:
            if normalize_external_camera_source_mode(source_mode, stream_url or source_url) == "stream":
                self._worker_loop_stream(
                    stream_url=stream_url or source_url,
                    preprocessing=preprocessing,
                    conf_threshold=conf_threshold,
                    iou_threshold=iou_threshold,
                    model_key=model_key,
                    interval_seconds=interval_seconds,
                )
            else:
                self._worker_loop_snapshot(
                    source_url=source_url,
                    camera_limit=camera_limit,
                    preprocessing=preprocessing,
                    conf_threshold=conf_threshold,
                    iou_threshold=iou_threshold,
                    model_key=model_key,
                    interval_seconds=interval_seconds,
                )
        finally:
            with self._lock:
                self._thread = None
                self._state["running"] = False
                if self._state.get("status") != "stopped":
                    self._state["status"] = "stopped" if self._stop_event.is_set() else "idle"

    def _worker_loop_snapshot(
        self,
        *,
        source_url: str,
        camera_limit: int,
        preprocessing: dict[str, Any],
        conf_threshold: float,
        iou_threshold: float,
        model_key: str | None,
        interval_seconds: float,
    ) -> None:
        while not self._stop_event.is_set():
            cycle_started_at = time.perf_counter()
            try:
                payload = run_external_camera_pipeline(
                    self.registry,
                    self.settings,
                    self.recent_image_store,
                    "snapshot",
                    source_url,
                    "",
                    camera_limit,
                    preprocessing,
                    conf_threshold,
                    iou_threshold,
                    model_key,
                    persist_result=False,
                )
                self._publish_live_payload(payload, cycle_started_at)
            except Exception as exc:
                logger.exception("Live cycle failed: source=%s", source_url)
                with self._lock:
                    self._state.update(
                        {
                            "running": True,
                            "status": "error",
                            "error": str(exc),
                            "last_updated_at": utc_now_iso_ms(),
                        }
                    )

            if self._stop_event.wait(interval_seconds):
                break

    def _worker_loop_stream(
        self,
        *,
        stream_url: str,
        preprocessing: dict[str, Any],
        conf_threshold: float,
        iou_threshold: float,
        model_key: str | None,
        interval_seconds: float,
    ) -> None:
        try:
            import cv2
        except Exception as exc:
            raise RuntimeError(f"OpenCV import failed while opening live stream: {exc}") from exc

        capture = cv2.VideoCapture(stream_url)
        if not capture.isOpened():
            capture.release()
            raise RuntimeError(f"Unable to open live stream source: {stream_url}")

        try:
            while not self._stop_event.is_set():
                cycle_started_at = time.perf_counter()
                try:
                    original_image = read_stream_frame_from_capture(capture)
                    payload = process_external_camera_frames(
                        self.registry,
                        self.settings,
                        self.recent_image_store,
                        stream_url,
                        [
                            {
                                "title": "Stream camera 1",
                                "youtube_id": "",
                                "snapshot_url": "",
                                "stream_url": stream_url,
                                "original_image": original_image,
                            }
                        ],
                        preprocessing,
                        conf_threshold,
                        iou_threshold,
                        model_key,
                        persist_result=False,
                    )
                    self._publish_live_payload(payload, cycle_started_at)
                except Exception as exc:
                    logger.exception("Live stream cycle failed: stream=%s", stream_url)
                    with self._lock:
                        self._state.update(
                            {
                                "running": True,
                                "status": "error",
                                "error": str(exc),
                                "last_updated_at": utc_now_iso_ms(),
                            }
                        )
                if self._stop_event.wait(interval_seconds):
                    break
        finally:
            capture.release()

    def _publish_live_payload(self, payload: dict[str, Any], cycle_started_at: float) -> None:
        cycle_elapsed_seconds = time.perf_counter() - cycle_started_at
        cycle_elapsed_ms = round(cycle_elapsed_seconds * 1000, 1)
        actual_cycle_fps = round(1.0 / cycle_elapsed_seconds, 2) if cycle_elapsed_seconds > 0 else None
        summary = payload.get("summary") or {}
        next_cycle_count = 1
        with self._lock:
            self._stream_frames = dict(payload.get("stream_frames") or {})
            self._stream_frame_id += 1
            next_cycle_count = int(self._state.get("cycle_count", 0)) + 1
            self._state.update(
                {
                    "running": True,
                    "status": "active",
                    "error": None,
                    "last_updated_at": utc_now_iso_ms(),
                    "cycle_count": next_cycle_count,
                    "last_cycle_duration_ms": cycle_elapsed_ms,
                    "actual_cycle_fps": actual_cycle_fps,
                    "stream_ready": True,
                    "last_result": {
                        "task": "detect",
                        "media_type": "external_camera_grid_live",
                        "source_url": payload["source_url"],
                        "camera_count": payload["camera_count"],
                        "overview": payload["overview"],
                        "summary": payload["summary"],
                        "preprocessing": payload["preprocessing"],
                        "model": payload["model"],
                        "cameras": payload["cameras"],
                    },
                }
            )

        # ── Cập nhật analytics + DB từ live cycle ────────────────────────────
        total_objects = summary.get("total_objects", 0)
        class_counts = summary.get("class_counts") or {}
        try:
            try:
                from db import upsert_traffic_counts, update_live_session, insert_congestion_log
            except ImportError:
                from fisheye_demo.db import upsert_traffic_counts, update_live_session, insert_congestion_log

            upsert_traffic_counts(class_counts, camera_source="live_camera")
            if self._session_id:
                update_live_session(
                    self._session_id,
                    cycle_count=next_cycle_count,
                    total_objects=total_objects,
                    class_counts=class_counts,
                    status="active",
                )

            # SQLite Logging: Tự động lưu log ùn tắc & tốc độ phương tiện từ chu kỳ live monitor nếu có phát hiện
            # Lưu log ùn tắc (Traffic congestion logs) cho camera live
            # Giả định một vùng ROI mặc định full_frame nếu có xe
            if total_objects > 0:
                insert_congestion_log(
                    roi_name="full_frame",
                    camera_source="live_camera",
                    actual_count=total_objects,
                    capacity=15,
                    congestion_ratio=round(total_objects / 15.0, 3),
                    state="CONGESTED" if total_objects > 10 else "SLOW" if total_objects > 5 else "FREE"
                )
        except Exception as db_exc:
            logger.debug("Database update failed during live publish: %s", db_exc)

        # Upload overview frame lên GCS mỗi 10 cycle
        if next_cycle_count % 10 == 0:
            try:
                try:
                    from cloud_storage import upload_image_bytes, build_object_name, is_enabled as gcs_enabled
                except ImportError:
                    from fisheye_demo.cloud_storage import upload_image_bytes, build_object_name, is_enabled as gcs_enabled

                if gcs_enabled():
                    overview_bytes = payload.get("stream_frames", {}).get("overview")
                    if overview_bytes:
                        ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
                        obj_name = build_object_name(f"live_{ts}", "overview_annotated.jpg")
                        gcs_result = upload_image_bytes(
                            overview_bytes, obj_name,
                            detection_id=None, image_role="live_overview",
                        )
                        if gcs_result:
                            try:
                                try:
                                    from db import insert_cloud_snapshot
                                except ImportError:
                                    from fisheye_demo.db import insert_cloud_snapshot
                                insert_cloud_snapshot(
                                    detection_id=None,
                                    gcs_bucket=gcs_result["gcs_bucket"],
                                    gcs_object_name=gcs_result["gcs_object_name"],
                                    gcs_public_url=gcs_result["gcs_public_url"],
                                    image_role="live_overview",
                                    expires_at=gcs_result["expires_at"],
                                )
                            except Exception:
                                pass
            except Exception:
                pass

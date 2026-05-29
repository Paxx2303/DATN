from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any
import numpy as np
from PIL import Image

try:
    from config import AppSettings
    from utils.helpers import apply_preprocessing, secure_filename, utc_now_iso
    from services.storage import create_result_dir, write_record, persist_recent_image
    from recent_image_store import RecentImageStore
except ImportError:
    from fisheye_demo.config import AppSettings
    from fisheye_demo.utils.helpers import apply_preprocessing, secure_filename, utc_now_iso
    from fisheye_demo.services.storage import create_result_dir, write_record, persist_recent_image
    from fisheye_demo.recent_image_store import RecentImageStore


def convert_video_to_fisheye(
    settings: AppSettings,
    input_path: Path,
    output_path: Path,
    preprocessing: dict[str, Any],
) -> tuple[dict[str, Any], Image.Image, Image.Image]:
    try:
        import cv2
    except Exception as exc:
        raise RuntimeError(f"OpenCV import failed: {exc}") from exc

    capture = cv2.VideoCapture(str(input_path))
    if not capture.isOpened():
        raise ValueError("Cannot open uploaded video.")

    fps = capture.get(cv2.CAP_PROP_FPS)
    fps = fps if fps and fps > 0 else 25.0
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    declared_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)

    if width <= 0 or height <= 0:
        capture.release()
        raise ValueError("Uploaded video has invalid frame size.")

    writer = cv2.VideoWriter(
        str(output_path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        (width, height),
    )
    if not writer.isOpened():
        capture.release()
        raise RuntimeError("Cannot open output video writer.")

    processed_frames = 0
    preview_original: Image.Image | None = None
    preview_fisheye: Image.Image | None = None

    try:
        while True:
            ok, frame_bgr = capture.read()
            if not ok:
                break

            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            original_image = Image.fromarray(frame_rgb)
            fisheye_image = apply_preprocessing(original_image, preprocessing).convert("RGB")

            if preview_original is None:
                preview_original = original_image.copy()
                preview_fisheye = fisheye_image.copy()

            writer.write(cv2.cvtColor(np.array(fisheye_image), cv2.COLOR_RGB2BGR))
            processed_frames += 1
    finally:
        capture.release()
        writer.release()

    if processed_frames == 0 or preview_original is None or preview_fisheye is None:
        raise ValueError("Uploaded video does not contain readable frames.")

    video_info = {
        "width": width,
        "height": height,
        "fps": round(fps, 3),
        "declared_frames": declared_frames,
        "processed_frames": processed_frames,
        "duration_seconds": round(processed_frames / fps, 3),
    }
    return video_info, preview_original, preview_fisheye


def save_video_conversion_record(
    settings: AppSettings,
    recent_image_store: RecentImageStore,
    filename: str,
    original_video_path: Path,
    fisheye_video_path: Path,
    preview_original: Image.Image,
    preview_fisheye: Image.Image,
    preprocessing: dict[str, Any],
    video_info: dict[str, Any],
) -> dict[str, Any]:
    result_id, result_dir = create_result_dir(settings)

    original_video_name = f"original{original_video_path.suffix.lower() or '.mp4'}"
    fisheye_video_name = "fisheye.mp4"
    artifacts = {
        "original_video": original_video_name,
        "fisheye_video": fisheye_video_name,
        "preview_original": "preview_original.jpg",
        "preview_fisheye": "preview_fisheye.jpg",
        "metadata": "metadata.json",
    }

    shutil.copy2(original_video_path, result_dir / artifacts["original_video"])
    shutil.copy2(fisheye_video_path, result_dir / artifacts["fisheye_video"])
    preview_original.save(result_dir / artifacts["preview_original"], format="JPEG", quality=90)
    preview_fisheye.save(result_dir / artifacts["preview_fisheye"], format="JPEG", quality=90)

    record = {
        "id": result_id,
        "task": "convert",
        "media_type": "video",
        "filename": secure_filename(filename),
        "created_at": utc_now_iso(),
        "source_layout": preprocessing["source_layout"],
        "preprocessing": preprocessing,
        "video_info": video_info,
        "summary": {
            "output_kind": "fisheye_video",
            "processed_frames": video_info["processed_frames"],
            "duration_seconds": video_info["duration_seconds"],
            "fps": video_info["fps"],
        },
        "artifacts": artifacts,
    }
    write_record(result_dir, record)
    persist_recent_image(
        recent_image_store,
        record=record,
        image_role="preview_fisheye",
        filename=artifacts["preview_fisheye"],
        image=preview_fisheye,
    )
    return record


def save_video_detection_record(
    settings: AppSettings,
    recent_image_store: RecentImageStore,
    filename: str,
    preprocessing: dict[str, Any],
    conf_threshold: float,
    iou_threshold: float,
    model_info: dict[str, Any],
    video_summary: dict[str, Any],
    result_dir: Path,
) -> dict[str, Any]:
    artifacts = {
        "annotated_video": "annotated.mp4",
        "metadata": "metadata.json",
    }

    preview_path = result_dir / "preview_annotated.jpg"
    if preview_path.exists():
        artifacts["preview_annotated"] = preview_path.name

    video_timing = {
        "video_detection_stride": video_summary.get("detection_stride"),
        "video_effective_detect_fps": video_summary.get("effective_detect_fps"),
        "video_processing_fps": video_summary.get("processing_fps"),
        "video_inference_fps": video_summary.get("inference_fps"),
    }
    if video_summary.get("target_detect_fps") is not None:
        video_timing["video_target_detect_fps"] = video_summary.get("target_detect_fps")

    record = {
        "id": result_dir.name,
        "task": "detect",
        "media_type": "video",
        "filename": secure_filename(filename),
        "created_at": utc_now_iso(),
        "source_layout": preprocessing["source_layout"],
        "preprocessing": preprocessing,
        "parameters": {
            "confidence_threshold": round(conf_threshold, 3),
            "iou_threshold": round(iou_threshold, 3),
            **{k: v for k, v in video_timing.items() if v is not None},
        },
        "model": {
            "source": model_info.get("source"),
            "loaded_from": model_info.get("loaded_from"),
            "loaded_from_name": model_info.get("loaded_from_name"),
            "device": model_info.get("device"),
            "selected_key": model_info.get("selected_key"),
            "selected_name": model_info.get("selected_name"),
        },
        "summary": video_summary,
        "artifacts": artifacts,
    }
    write_record(result_dir, record)
    if preview_path.exists():
        with Image.open(preview_path) as preview_image:
            preview_image.load()
            persist_recent_image(
                recent_image_store,
                record=record,
                image_role="preview_annotated",
                filename=artifacts["preview_annotated"],
                image=preview_image.convert("RGB"),
            )

    # ── Persist video detection to DB + GCS ──────────────────────────────────
    gcs_urls: dict[str, str] = {}
    try:
        try:
            from cloud_storage import upload_pil_image, build_object_name, is_enabled as gcs_enabled
        except ImportError:
            from fisheye_demo.cloud_storage import upload_pil_image, build_object_name, is_enabled as gcs_enabled

        if gcs_enabled() and preview_path.exists():
            with Image.open(preview_path) as _prev:
                _prev.load()
                obj_name = build_object_name(record["id"], "preview_annotated.jpg")
                gcs_result = upload_pil_image(_prev.convert("RGB"), obj_name,
                                              detection_id=record["id"], image_role="preview_annotated")
                if gcs_result:
                    gcs_urls["preview_annotated"] = gcs_result["gcs_public_url"]
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
                            image_role="preview_annotated",
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
        class_counts = video_summary.get("class_counts") or {}
        upsert_traffic_counts(class_counts, camera_source="video_upload")
    except Exception:
        pass

    if gcs_urls:
        record["gcs_urls"] = gcs_urls

    return record

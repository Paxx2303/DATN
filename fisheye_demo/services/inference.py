from __future__ import annotations

import time
from typing import Any
import numpy as np
from PIL import Image

try:
    from config import AppSettings, CLASS_NAMES, CLASS_COLORS
    from utils.helpers import normalize_class_name, to_hex_bgr, utc_now_iso, secure_filename
    from services.model_registry import ModelRegistry
    from services.storage import create_result_dir, write_record, persist_recent_image
    from recent_image_store import RecentImageStore
except ImportError:
    from fisheye_demo.config import AppSettings, CLASS_NAMES, CLASS_COLORS
    from fisheye_demo.utils.helpers import normalize_class_name, to_hex_bgr, utc_now_iso, secure_filename
    from fisheye_demo.services.model_registry import ModelRegistry
    from fisheye_demo.services.storage import create_result_dir, write_record, persist_recent_image
    from fisheye_demo.recent_image_store import RecentImageStore


def run_inference(
    registry: ModelRegistry,
    settings: AppSettings,
    image: Image.Image,
    conf_threshold: float,
    iou_threshold: float,
    model_key: str | None = None,
):
    model, model_info = registry.load(model_key)

    try:
        import cv2
    except Exception as exc:
        raise RuntimeError(f"OpenCV import failed: {exc}") from exc

    frame_rgb = np.array(image.convert("RGB"))
    frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)

    started_at = time.perf_counter()
    results = model.predict(
        source=frame_bgr,
        conf=conf_threshold,
        iou=iou_threshold,
        verbose=False,
        device=settings.device,
    )[0]
    elapsed_ms = (time.perf_counter() - started_at) * 1000

    annotated = frame_rgb.copy()
    detections: list[dict[str, Any]] = []
    class_counts = {class_name: 0 for class_name in CLASS_NAMES}
    raw_names = getattr(getattr(model, "model", None), "names", None) or getattr(model, "names", None) or {}

    for box in list(results.boxes or []):
        x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
        confidence = float(box.conf[0])
        class_id = int(box.cls[0])
        raw_label = str(raw_names.get(class_id, class_id))
        label = normalize_class_name(raw_label)

        if model_info["source"] == "fallback" and settings.filter_fallback_to_supported_classes and label not in CLASS_NAMES:
            continue

        color = CLASS_COLORS.get(label, "#FFFFFF")
        color_bgr = to_hex_bgr(color)
        cv2.rectangle(annotated, (x1, y1), (x2, y2), color_bgr, 3)

        box_label = f"{label} {confidence:.0%}"
        (text_width, text_height), baseline = cv2.getTextSize(box_label, cv2.FONT_HERSHEY_SIMPLEX, 0.62, 2)
        label_x = x1
        label_y = max(y1 - 10, text_height + 6)
        cv2.rectangle(
            annotated,
            (label_x, label_y - text_height - 6),
            (label_x + text_width + 8, label_y + baseline),
            color_bgr,
            -1,
        )
        cv2.putText(
            annotated,
            box_label,
            (label_x + 4, label_y - 3),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.62,
            (0, 0, 0),
            2,
        )

        class_counts[label] = class_counts.get(label, 0) + 1
        detections.append(
            {
                "class": label,
                "raw_class": raw_label,
                "confidence": round(confidence, 4),
                "bbox": [x1, y1, x2, y2],
                "color": color,
            }
        )

    detections.sort(key=lambda item: item["confidence"], reverse=True)
    return Image.fromarray(annotated), detections, class_counts, elapsed_ms, model_info


def save_detection_record(
    settings: AppSettings,
    recent_image_store: RecentImageStore,
    filename: str,
    original_image: Image.Image,
    preprocessed_image: Image.Image,
    annotated_image: Image.Image,
    detections: list[dict[str, Any]],
    class_counts: dict[str, int],
    inference_ms: float,
    conf_threshold: float,
    iou_threshold: float,
    model_info: dict[str, Any],
    preprocessing: dict[str, Any],
) -> dict[str, Any]:
    result_id, result_dir = create_result_dir(settings)

    artifacts = {
        "original": "original.jpg",
        "annotated": "annotated.jpg",
        "metadata": "metadata.json",
    }
    original_image.save(result_dir / artifacts["original"], format="JPEG", quality=92)
    annotated_image.save(result_dir / artifacts["annotated"], format="JPEG", quality=92)

    if preprocessing["enabled"]:
        artifacts["preprocessed"] = "preprocessed.jpg"
        preprocessed_image.save(result_dir / artifacts["preprocessed"], format="JPEG", quality=92)

    record = {
        "id": result_id,
        "task": "detect",
        "media_type": "image",
        "filename": secure_filename(filename),
        "created_at": utc_now_iso(),
        "source_layout": preprocessing["source_layout"],
        "preprocessing": preprocessing,
        "image_size": {"width": original_image.width, "height": original_image.height},
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
            "total_objects": len(detections),
            "inference_ms": round(inference_ms, 2),
            "class_counts": class_counts,
        },
        "detections": detections,
        "artifacts": artifacts,
    }
    write_record(result_dir, record)
    persist_recent_image(
        recent_image_store,
        record=record,
        image_role="annotated",
        filename=artifacts["annotated"],
        image=annotated_image,
    )

    # ── Persist to PostgreSQL + GCS ──────────────────────────────────────────
    gcs_urls: dict[str, str] = {}
    try:
        try:
            from cloud_storage import upload_pil_image, build_object_name, is_enabled as gcs_enabled
        except ImportError:
            from fisheye_demo.cloud_storage import upload_pil_image, build_object_name, is_enabled as gcs_enabled

        if gcs_enabled():
            obj_name = build_object_name(result_id, "annotated.jpg")
            gcs_result = upload_pil_image(annotated_image, obj_name, detection_id=result_id, image_role="annotated")
            if gcs_result:
                gcs_urls["annotated"] = gcs_result["gcs_public_url"]
                try:
                    try:
                        from db import insert_cloud_snapshot
                    except ImportError:
                        from fisheye_demo.db import insert_cloud_snapshot
                    insert_cloud_snapshot(
                        detection_id=result_id,
                        gcs_bucket=gcs_result["gcs_bucket"],
                        gcs_object_name=gcs_result["gcs_object_name"],
                        gcs_public_url=gcs_result["gcs_public_url"],
                        image_role="annotated",
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
        upsert_traffic_counts(class_counts, camera_source="upload")
    except Exception:
        pass

    if gcs_urls:
        record["gcs_urls"] = gcs_urls

    return record


def save_image_conversion_record(
    settings: AppSettings,
    recent_image_store: RecentImageStore,
    filename: str,
    original_image: Image.Image,
    fisheye_image: Image.Image,
    preprocessing: dict[str, Any],
) -> dict[str, Any]:
    result_id, result_dir = create_result_dir(settings)
    artifacts = {
        "original": "original.jpg",
        "fisheye_image": "fisheye.jpg",
        "metadata": "metadata.json",
    }

    original_image.save(result_dir / artifacts["original"], format="JPEG", quality=92)
    fisheye_image.save(result_dir / artifacts["fisheye_image"], format="JPEG", quality=92)

    record = {
        "id": result_id,
        "task": "convert",
        "media_type": "image",
        "filename": secure_filename(filename),
        "created_at": utc_now_iso(),
        "source_layout": preprocessing["source_layout"],
        "preprocessing": preprocessing,
        "image_size": {"width": original_image.width, "height": original_image.height},
        "summary": {
            "output_kind": "fisheye_image",
            "width": fisheye_image.width,
            "height": fisheye_image.height,
        },
        "artifacts": artifacts,
    }
    write_record(result_dir, record)
    persist_recent_image(
        recent_image_store,
        record=record,
        image_role="fisheye_image",
        filename=artifacts["fisheye_image"],
        image=fisheye_image,
    )
    return record

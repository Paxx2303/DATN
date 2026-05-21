from __future__ import annotations

import math
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image

try:
    from fisheye_demo.fisheye import apply_fisheye
except ModuleNotFoundError:
    from fisheye import apply_fisheye

try:
    from fisheye_demo.speed_estimator import SpeedEstimator, annotate_speed_on_frame
    from fisheye_demo.congestion_detector import CongestionDetector, annotate_congestion_on_frame
    _TRAFFIC_FEATURES_AVAILABLE = True
except ImportError:
    try:
        from speed_estimator import SpeedEstimator, annotate_speed_on_frame
        from congestion_detector import CongestionDetector, annotate_congestion_on_frame
        _TRAFFIC_FEATURES_AVAILABLE = True
    except ImportError:
        _TRAFFIC_FEATURES_AVAILABLE = False


_BOX_COLORS_BGR: list[tuple[int, int, int]] = [
    (40, 190, 255),
    (80, 175, 76),
    (180, 105, 255),
    (42, 210, 215),
    (34, 139, 230),
    (227, 180, 70),
]


def detection_stride(source_fps: float, target_detect_fps: float | None) -> int:
    """How many source frames between YOLO runs. 1 = every frame after fisheye."""
    if target_detect_fps is None or target_detect_fps <= 0:
        return 1
    if source_fps <= 0:
        return 1
    if target_detect_fps >= source_fps:
        return 1
    return max(1, int(round(source_fps / target_detect_fps)))


def _annotate_bgr_from_result(
    frame_bgr: np.ndarray,
    result: Any,
    *,
    names: dict[Any, str],
    normalized_name_map: dict[str, str],
    allowed_classes: set[str] | None,
    filter_allowed_classes: bool,
) -> np.ndarray:
    """Draw last inference boxes on the current fisheye frame (same resolution)."""
    out = frame_bgr.copy()
    boxes = getattr(result, "boxes", None)
    if boxes is None or len(boxes) == 0:
        return out

    xyxy = boxes.xyxy.cpu().numpy()
    cls_ids = boxes.cls.cpu().numpy().astype(int)
    confs = boxes.conf.cpu().numpy()

    for i in range(len(xyxy)):
        x1, y1, x2, y2 = (int(v) for v in xyxy[i])
        cls_id = int(cls_ids[i])
        conf = float(confs[i])
        raw_name = str(names.get(cls_id, cls_id))
        label = normalized_name_map.get(raw_name.lower(), raw_name)
        if filter_allowed_classes and allowed_classes and label not in allowed_classes:
            continue
        color = _BOX_COLORS_BGR[cls_id % len(_BOX_COLORS_BGR)]
        cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)
        txt = f"{label} {conf * 100:.0f}%"
        cv2.putText(
            out,
            txt,
            (x1, max(18, y1 - 4)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            color,
            1,
            cv2.LINE_AA,
        )
    return out


def run_video_detect(
    input_path: str,
    output_path: str,
    model,
    conf: float = 0.25,
    iou: float = 0.45,
    device: str = "cpu",
    apply_fisheye_transform: bool = False,
    fisheye_strength: float = 0.70,
    fisheye_radius: float = 0.85,
    fisheye_effect: str = "standard",
    preview_path: str | None = None,
    name_map: dict[str, str] | None = None,
    allowed_classes: set[str] | None = None,
    filter_allowed_classes: bool = False,
    target_detect_fps: float | None = None,
    # ── Traffic features ──────────────────────────────────────────────────────
    enable_speed_estimation: bool = False,
    speed_pixels_per_meter: float = 8.0,
    speed_limit_kmh: float = 60.0,
    enable_congestion_detection: bool = False,
    congestion_capacity: int = 15,
    # ── Incident detection ────────────────────────────────────────────────────
    incident_detector: Any | None = None,
    incident_camera_id: str = "video_upload",
) -> dict[str, Any]:
    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {input_path}")

    fps = float(cap.get(cv2.CAP_PROP_FPS) or 25.0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)

    if width <= 0 or height <= 0:
        cap.release()
        raise ValueError("Uploaded video has invalid frame size.")

    stride = detection_stride(fps, target_detect_fps)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(
        output_path,
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        (width, height),
    )
    if not writer.isOpened():
        cap.release()
        raise RuntimeError(f"Cannot create video writer at: {output_path}")

    names = getattr(getattr(model, "model", None), "names", None) or getattr(model, "names", None) or {}
    normalized_name_map = {str(key).lower(): value for key, value in (name_map or {}).items()}

    frame_count = 0
    inference_times: list[float] = []
    class_counts: dict[str, int] = {}
    first_annotated_frame: np.ndarray | None = None
    last_result: Any | None = None
    inference_runs = 0

    # ── Traffic feature instances ─────────────────────────────────────────────
    speed_est: SpeedEstimator | None = None
    congestion_det: CongestionDetector | None = None

    # ── Incident tracking ─────────────────────────────────────────────────────
    all_incidents: list[dict[str, Any]] = []
    incident_counts: dict[str, int] = {}

    if _TRAFFIC_FEATURES_AVAILABLE:
        if enable_speed_estimation:
            speed_est = SpeedEstimator(
                fps=fps,
                pixels_per_meter=speed_pixels_per_meter,
                fisheye_correction=True,
                speed_limit_kmh=speed_limit_kmh,
            )
        if enable_congestion_detection:
            congestion_det = CongestionDetector()
            # Cập nhật capacity cho ROI mặc định
            congestion_det.add_roi("full_frame", 0.0, 0.0, 1.0, 1.0, capacity=congestion_capacity)
            congestion_det.add_roi("intersection", 0.25, 0.25, 0.75, 0.75, capacity=max(1, congestion_capacity // 2))

    wall_t0 = time.perf_counter()
    try:
        while True:
            ok, frame_bgr = cap.read()
            if not ok:
                break

            inference_frame = frame_bgr
            if apply_fisheye_transform:
                frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                fisheye_image = apply_fisheye(
                    Image.fromarray(frame_rgb),
                    strength=fisheye_strength,
                    radius=fisheye_radius,
                    effect=fisheye_effect,
                ).convert("RGB")
                inference_frame = cv2.cvtColor(np.array(fisheye_image), cv2.COLOR_RGB2BGR)

            run_infer = (frame_count % stride == 0) or last_result is None
            if run_infer:
                start = time.perf_counter()
                last_result = model.predict(
                    source=inference_frame,
                    conf=conf,
                    iou=iou,
                    verbose=False,
                    device=device,
                )[0]
                inference_ms = (time.perf_counter() - start) * 1000
                inference_times.append(inference_ms)
                inference_runs += 1

                annotated_frame = last_result.plot()
                for box in list(last_result.boxes or []):
                    class_id = int(box.cls[0])
                    raw_name = str(names.get(class_id, class_id))
                    normalized_name = normalized_name_map.get(raw_name.lower(), raw_name)
                    if filter_allowed_classes and allowed_classes and normalized_name not in allowed_classes:
                        continue
                    class_counts[normalized_name] = class_counts.get(normalized_name, 0) + 1
            else:
                annotated_frame = _annotate_bgr_from_result(
                    inference_frame,
                    last_result,
                    names=names,
                    normalized_name_map=normalized_name_map,
                    allowed_classes=allowed_classes,
                    filter_allowed_classes=filter_allowed_classes,
                )

            # ── Traffic features overlay ──────────────────────────────────────
            if last_result is not None and _TRAFFIC_FEATURES_AVAILABLE:
                # Xây dựng detections list từ last_result
                frame_dets: list[dict[str, Any]] = []
                boxes_obj = getattr(last_result, "boxes", None)
                if boxes_obj is not None and len(boxes_obj):
                    xyxy_arr = boxes_obj.xyxy.cpu().numpy()
                    cls_arr = boxes_obj.cls.cpu().numpy().astype(int)
                    conf_arr = boxes_obj.conf.cpu().numpy()
                    for i in range(len(xyxy_arr)):
                        x1, y1, x2, y2 = (float(v) for v in xyxy_arr[i])
                        raw_name = str(names.get(int(cls_arr[i]), int(cls_arr[i])))
                        cls_name = normalized_name_map.get(raw_name.lower(), raw_name)
                        frame_dets.append({
                            "class": cls_name,
                            "confidence": float(conf_arr[i]),
                            "bbox": [x1, y1, x2, y2],
                        })

                # Speed estimation
                if speed_est is not None:
                    speed_results = speed_est.update(frame_dets, width, height)
                    annotated_frame = annotate_speed_on_frame(
                        annotated_frame, speed_results, width, height,
                        speed_limit_kmh=speed_limit_kmh,
                    )

                # Congestion detection
                if congestion_det is not None:
                    cong_result = congestion_det.update(frame_dets, width, height)
                    annotated_frame = annotate_congestion_on_frame(
                        annotated_frame, cong_result, width, height,
                    )

                # Incident detection
                if incident_detector is not None:
                    try:
                        frame_rgb_for_inc = cv2.cvtColor(inference_frame, cv2.COLOR_BGR2RGB)
                        new_incidents = incident_detector.process_frame(
                            frame_dets,
                            frame_rgb_for_inc,
                            incident_camera_id,
                            width,
                            height,
                        )
                        for inc in new_incidents:
                            all_incidents.append(inc)
                            inc_type = inc.get("type", "unknown")
                            incident_counts[inc_type] = incident_counts.get(inc_type, 0) + 1
                    except Exception:
                        pass

            if frame_count == 0:
                first_annotated_frame = annotated_frame.copy()

            writer.write(annotated_frame)
            frame_count += 1
    finally:
        cap.release()
        writer.release()

    wall_elapsed = max(time.perf_counter() - wall_t0, 1e-9)

    if frame_count == 0:
        raise ValueError("Uploaded video does not contain readable frames.")

    if preview_path is not None and first_annotated_frame is not None:
        Path(preview_path).parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(preview_path, first_annotated_frame)

    avg_ms = round(sum(inference_times) / len(inference_times), 2) if inference_times else 0.0
    total_detections = sum(class_counts.values())
    duration_seconds = round(frame_count / fps, 3) if fps > 0 else 0.0
    processing_fps = round(frame_count / wall_elapsed, 2)
    inference_fps = round(inference_runs / wall_elapsed, 2)
    effective_detect_fps = round(fps / stride, 2) if stride > 0 else fps

    summary: dict[str, Any] = {
        "total_frames": frame_count,
        "fps_original": round(fps, 2),
        "resolution": f"{width}x{height}",
        "inference_ms_avg": avg_ms,
        "class_counts": class_counts,
        "total_detections": total_detections,
        "duration_seconds": duration_seconds,
        "processing_fps": processing_fps,
        "inference_fps": inference_fps,
        "fisheye_before_detect": apply_fisheye_transform,
        "detection_stride": stride,
        "effective_detect_fps": effective_detect_fps,
    }
    if target_detect_fps is not None and target_detect_fps > 0:
        summary["target_detect_fps"] = round(target_detect_fps, 3)
    else:
        summary["target_detect_fps"] = None

    # ── Traffic feature stats ─────────────────────────────────────────────────
    if speed_est is not None:
        summary["speed_stats"] = speed_est.get_stats()
    if congestion_det is not None:
        summary["congestion_stats"] = congestion_det.get_status()

    # ── Incident stats ────────────────────────────────────────────────────────
    if incident_detector is not None:
        summary["incident_counts"] = incident_counts
        summary["total_incidents"] = sum(incident_counts.values())
        summary["incidents"] = [
            {k: v for k, v in inc.items() if k not in ("frame_rgb",)}
            for inc in all_incidents
        ]

    return summary

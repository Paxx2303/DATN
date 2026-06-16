"""
video_detect.py — Video Processing Pipeline

Chạy trong worker thread (không phải Flask main thread).
Hỗ trợ:
- Fisheye transform mỗi frame (trước YOLO)
- YOLO tracking với detection stride
- Speed estimation
- Congestion/incident detection
- Progress callback cho job queue
"""

import cv2
import numpy as np
import logging
import time
from pathlib import Path
from typing import Any, Callable, Optional
from fisheye import apply_fisheye_to_cv2
from speed_estimator import SpeedEstimator
from congestion_detector import CongestionDetector
from incident_detector import IncidentDetector
from line_counter import LineCounter
from config import Config

logger = logging.getLogger(__name__)


def detection_stride(fps_source: float, target_fps: float) -> int:
    """
    Tính bước nhảy frame để đạt target_fps.
    
    Ví dụ: fps_source=30, target_fps=5 → stride=6
    (cứ 6 frame mới chạy YOLO 1 lần)
    
    Luôn >= 1 để không bỏ sót frame nào.
    """
    if target_fps is None or target_fps <= 0:
        return 1
    stride = max(1, round(fps_source / target_fps))
    return stride


def run_video_detect(
    input_path: str,
    output_path: str,
    model: Any,                          # ultralytics YOLO instance
    conf: float = 0.35,
    iou: float = 0.45,
    device: str = "cpu",
    apply_fisheye_transform: bool = False,
    fisheye_strength: float = 0.6,
    fisheye_radius: float = 0.85,
    fisheye_effect: str = "standard",
    fisheye_center_x: float = 0.5,
    fisheye_center_y: float = 0.5,
    preview_path: Optional[str] = None,
    name_map: Optional[dict[str, str]] = None,
    allowed_classes: Optional[set[str]] = None,
    filter_allowed_classes: bool = False,
    target_detect_fps: Optional[float] = 5.0,
    incident_detector_inst: Optional[IncidentDetector] = None,
    incident_camera_id: str = "video",
    progress_cb: Optional[Callable[[float], None]] = None,
) -> dict[str, Any]:
    """
    Xử lý toàn bộ video và ghi ra video annotated.
    
    Returns
    -------
    dict chứa:
        counts      : {vehicle_type: count}
        avg_speed   : float (km/h)
        incidents   : list of incident dicts
        duration_s  : float (giây xử lý)
        frame_count : int
    """
    name_map = name_map or {}
    allowed_classes = allowed_classes or set()
    
    # ── Mở video nguồn ───────────────────────────────────────
    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {input_path}")
    
    fps_src = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    stride = detection_stride(fps_src, target_detect_fps)
    logger.info(f"Video: {width}x{height} @ {fps_src:.1f}fps, {total_frames} frames, stride={stride}")
    
    # ── Khởi tạo VideoWriter ──────────────────────────────────
    # Thử H264 trước, fallback sang mp4v
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(output_path, fourcc, fps_src, (width, height))
    if not writer.isOpened():
        raise RuntimeError(f"Cannot open VideoWriter at {output_path}")
    
    # ── Khởi tạo analytics modules ───────────────────────────
    speed_estimator = SpeedEstimator(
        fps=fps_src,
        scale_factor=Config.SPEED_SCALE_FACTOR,
        speed_limit_kmh=Config.SPEED_LIMIT_KMH,
    )
    congestion = CongestionDetector(frame_width=width, frame_height=height)
    line_counter = LineCounter(camera_id=incident_camera_id)
    congestion_result: dict = {}

    # ── Tracking state ────────────────────────────────────────
    counts: dict[str, int] = {}          # Đếm xe theo loại (unique track)
    seen_tracks: dict[int, str] = {}     # track_id → display_name (lần đầu xuất hiện)
    last_boxes: dict[int, tuple] = {}    # track_id → (x1,y1,x2,y2)
    last_labels: dict[int, str] = {}     # track_id → class_name
    preview_saved = False
    frame_idx = 0
    t_start = time.time()
    
    # ── Màu sắc cho từng loại xe ─────────────────────────────
    COLOR_MAP = {
        "car":        (0, 255, 0),
        "truck":      (255, 128, 0),
        "bus":        (0, 128, 255),
        "motorcycle": (255, 0, 255),
        "person":     (255, 255, 0),
        "bicycle":    (0, 255, 255),
    }
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        
        # ── Fisheye transform ─────────────────────────────────
        if apply_fisheye_transform:
            frame = apply_fisheye_to_cv2(
                frame, strength=fisheye_strength,
                radius=fisheye_radius, effect=fisheye_effect,
                center_x=fisheye_center_x, center_y=fisheye_center_y,
            )
        
        # ── YOLO inference (mỗi stride frames) ───────────────
        if frame_idx % stride == 0:
            # model.track() trả về Results với .boxes.data tensor
            results = model.track(
                frame,
                conf=conf, iou=iou,
                device=device,
                persist=True,      # Giữ track state giữa các frame
                verbose=False,
            )
            
            # Parse kết quả tracking
            last_boxes.clear()
            last_labels.clear()
            
            if results and results[0].boxes is not None:
                boxes_data = results[0].boxes
                for box in boxes_data:
                    if box.id is None:
                        continue
                    track_id = int(box.id.item())
                    cls_id   = int(box.cls.item())
                    cls_name = model.names[cls_id]
                    
                    # Filter class nếu cần
                    if filter_allowed_classes and cls_name not in allowed_classes:
                        continue
                    
                    x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
                    display_name = name_map.get(cls_name, cls_name)
                    last_boxes[track_id]  = (x1, y1, x2, y2)
                    last_labels[track_id] = display_name

                    # Đếm unique: chỉ ghi nhận lần ĐẦU mỗi track_id xuất hiện
                    if track_id not in seen_tracks:
                        seen_tracks[track_id] = display_name

                    # Cập nhật speed estimator và line counter
                    cx = (x1 + x2) // 2
                    cy = (y1 + y2) // 2
                    speed_estimator.update_single(track_id, cx, cy, frame_idx, display_name)
                    line_counter.update(track_id, cx, cy, display_name, frame_idx, width, height)

            # ── Congestion analysis (trên frame detect) ──────────
            congestion_result = congestion.analyze(last_boxes)
        
        # ── Vẽ bounding boxes và labels ───────────────────────
        for track_id, (x1, y1, x2, y2) in last_boxes.items():
            label = last_labels.get(track_id, "vehicle")
            cls_key = label.lower()
            color = COLOR_MAP.get(cls_key, (255, 255, 255))
            
            # Lấy tốc độ hiện tại
            speed = speed_estimator.get_speed(track_id)
            speed_text = f"{speed:.0f}km/h" if speed > 0 else ""
            
            # Vẽ bounding box
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            
            # Label text: "Car#5 42km/h"
            text = f"{label}#{track_id}"
            if speed_text:
                text += f" {speed_text}"
            
            # Background cho text
            (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.rectangle(frame, (x1, y1 - th - 6), (x1 + tw + 4, y1), color, -1)
            cv2.putText(frame, text, (x1 + 2, y1 - 4),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
        
        # ── Incident detection ────────────────────────────────
        if incident_detector_inst and frame_idx % stride == 0:
            incidents = incident_detector_inst.analyze(
                boxes=last_boxes,
                labels=last_labels,
                frame_idx=frame_idx,
                fps=fps_src,
            )
            for inc in incidents:
                # Vẽ warning overlay
                x1, y1, x2, y2 = inc.get("bbox", (0,0,0,0))
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 3)
                cv2.putText(frame, inc["incident_type"], (x1, y1 - 10),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
        
        # ── Draw virtual counting lines ───────────────────────
        _LINE_BGR = {"north":(80,80,255),"south":(255,80,80),"east":(80,255,80),"west":(0,200,255)}
        for direction, pts in line_counter.get_line_coords_pixel(width, height).items():
            color = _LINE_BGR.get(direction, (255, 255, 255))
            cv2.line(frame, pts["start"], pts["end"], color, 2)
            mid = ((pts["start"][0]+pts["end"][0])//2, (pts["start"][1]+pts["end"][1])//2)
            cv2.putText(frame, direction[0].upper(), mid,
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

        # ── Overlay: vehicle count ────────────────────────────
        total_count = len(last_boxes)
        cv2.putText(frame, f"Vehicles: {total_count}", (10, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 2)
        
        # ── Ghi frame ra video ────────────────────────────────
        writer.write(frame)
        
        # ── Lưu preview frame (frame 10 hoặc 5% đầu) ─────────
        if not preview_saved and (frame_idx == min(10, total_frames // 20)):
            if preview_path:
                cv2.imwrite(preview_path, frame)
                preview_saved = True
        
        frame_idx += 1
        
        # ── Cập nhật progress ─────────────────────────────────
        if progress_cb and total_frames > 0:
            pct = (frame_idx / total_frames) * 95.0  # dành 5% cho finalize
            progress_cb(pct)
    
    # ── Cleanup ───────────────────────────────────────────────
    cap.release()
    writer.release()

    # Đếm cuối: số track_id DUY NHẤT theo loại trong toàn bộ video
    counts = {}
    for label in seen_tracks.values():
        counts[label] = counts.get(label, 0) + 1

    avg_speed = speed_estimator.get_average_speed()
    duration = time.time() - t_start

    logger.info(f"Video processing done: {frame_idx} frames in {duration:.1f}s, counts={counts}")

    return {
        "counts": counts,
        "total_unique": len(seen_tracks),
        "avg_speed": round(avg_speed, 1),
        "max_speed": speed_estimator.get_max_speed(),
        "incidents": incident_detector_inst.get_all_incidents() if incident_detector_inst else [],
        "line_counter": line_counter.get_stats(),
        "speed_violations": speed_estimator.get_violations(),
        "congestion": congestion_result,
        "duration_s": round(duration, 2),
        "frame_count": frame_idx,
        "fps_processed": round(frame_idx / max(duration, 0.1), 1),
        "resolution": f"{width}x{height}",
        "detection_stride": stride,
        "target_detect_fps": target_detect_fps,
    }

"""
speed_estimator.py — Ước tính tốc độ xe qua 2 frame liên tiếp

Nguyên lý:
  - Track object qua IoU giữa các frame
  - Đo displacement pixel của centroid giữa frame t và frame t-1
  - Chuyển đổi pixel/frame → km/h qua hệ số calibration (pixels_per_meter)
  - Áp dụng fisheye correction: vật ở rìa ảnh bị co lại → cần scale up

Cách dùng:
  estimator = SpeedEstimator(fps=25.0, pixels_per_meter=8.0)
  for frame_detections in video_frames:
      speeds = estimator.update(frame_detections, frame_w, frame_h)
      # speeds: list of {"track_id", "class", "speed_kmh", "bbox", ...}

Calibration:
  pixels_per_meter phụ thuộc vào độ cao camera và góc nhìn.
  Ví dụ: camera 5m, góc 45° → ~8-12 px/m ở vùng trung tâm ảnh fisheye.
  Có thể calibrate bằng cách đo khoảng cách thực tế giữa 2 điểm trên mặt đường.
"""
from __future__ import annotations

import math
import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any

import numpy as np

# Hệ số chuyển đổi mặc định (có thể override qua API)
DEFAULT_PIXELS_PER_METER = 8.0   # px/m ở vùng trung tâm ảnh
DEFAULT_FPS = 25.0
SPEED_HISTORY_SIZE = 10           # số frame để smooth tốc độ
MAX_TRACK_AGE = 30                # frame không thấy thì xóa track
MIN_DISPLACEMENT_PX = 1.5        # bỏ qua chuyển động quá nhỏ (noise)
MAX_SPEED_KMH = 200.0            # cap tốc độ tối đa (lọc outlier)

# Màu cảnh báo tốc độ
SPEED_COLORS = {
    "normal":   "#4FC3F7",   # xanh — < 40 km/h
    "moderate": "#FFB74D",   # cam  — 40-70 km/h
    "fast":     "#EF5350",   # đỏ   — > 70 km/h
}

VEHICLE_CLASSES = {"Car", "Bus", "Truck", "Motorbike"}


class SpeedEstimator:
    """
    Ước tính tốc độ xe qua displacement centroid giữa các frame.
    Thread-safe.
    """

    def __init__(
        self,
        fps: float = DEFAULT_FPS,
        pixels_per_meter: float = DEFAULT_PIXELS_PER_METER,
        fisheye_correction: bool = True,
        speed_limit_kmh: float = 60.0,
    ) -> None:
        self.fps = max(1.0, fps)
        self.pixels_per_meter = max(0.1, pixels_per_meter)
        self.fisheye_correction = fisheye_correction
        self.speed_limit_kmh = speed_limit_kmh

        self._lock = threading.Lock()
        # track_id → {cx, cy, norm_box, class, speed_history, age, last_speed}
        self._tracks: dict[str, dict[str, Any]] = {}
        self._next_id = 0
        self._frame_count = 0

        # Thống kê tổng hợp
        self._speed_records: deque = deque(maxlen=500)
        self._overspeed_count = 0
        self._total_vehicles_tracked = 0

    # ── Public API ────────────────────────────────────────────────────────────

    def update(
        self,
        detections: list[dict[str, Any]],
        frame_width: int,
        frame_height: int,
    ) -> list[dict[str, Any]]:
        """
        Cập nhật với detections của frame hiện tại.

        Args:
            detections: list of {"class": str, "bbox": [x1,y1,x2,y2], "confidence": float}
            frame_width, frame_height: kích thước frame (pixel)

        Returns:
            list of speed results cho từng tracked vehicle
        """
        with self._lock:
            self._frame_count += 1
            results: list[dict[str, Any]] = []

            # Chỉ track vehicle classes
            vehicle_dets = [
                d for d in detections
                if d.get("class", "") in VEHICLE_CLASSES
            ]

            # Normalize bbox về 0-1
            norm_dets = []
            for det in vehicle_dets:
                x1, y1, x2, y2 = det.get("bbox", [0, 0, 0, 0])
                cx = ((x1 + x2) / 2) / frame_width
                cy = ((y1 + y2) / 2) / frame_height
                norm_box = [
                    x1 / frame_width, y1 / frame_height,
                    x2 / frame_width, y2 / frame_height,
                ]
                norm_dets.append({
                    **det,
                    "cx": cx, "cy": cy,
                    "norm_box": norm_box,
                })

            # Match với tracks cũ
            matched_ids: set[str] = set()
            for det in norm_dets:
                best_iou = 0.25
                best_id: str | None = None

                for tid, track in self._tracks.items():
                    if tid in matched_ids:
                        continue
                    iou = self._iou(det["norm_box"], track["norm_box"])
                    if iou > best_iou:
                        best_iou = iou
                        best_id = tid

                if best_id is not None:
                    # Tính tốc độ từ displacement
                    track = self._tracks[best_id]
                    dx = (det["cx"] - track["cx"]) * frame_width
                    dy = (det["cy"] - track["cy"]) * frame_height
                    displacement_px = math.hypot(dx, dy)

                    speed_kmh = self._px_to_kmh(
                        displacement_px,
                        det["cx"], det["cy"],
                        frame_width, frame_height,
                    )

                    # Smooth tốc độ
                    track["speed_history"].append(speed_kmh)
                    smoothed = self._smooth_speed(track["speed_history"])
                    track["last_speed"] = smoothed
                    track["cx"] = det["cx"]
                    track["cy"] = det["cy"]
                    track["norm_box"] = det["norm_box"]
                    track["class"] = det.get("class", "")
                    track["age"] = 0

                    matched_ids.add(best_id)

                    # Ghi record nếu tốc độ hợp lệ
                    if smoothed > 0:
                        is_overspeed = smoothed > self.speed_limit_kmh
                        if is_overspeed:
                            self._overspeed_count += 1
                        self._speed_records.append({
                            "track_id": best_id,
                            "class": det.get("class", ""),
                            "speed_kmh": round(smoothed, 1),
                            "is_overspeed": is_overspeed,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "cx": round(det["cx"], 3),
                            "cy": round(det["cy"], 3),
                        })

                    results.append(self._build_result(best_id, det, smoothed))
                else:
                    # Track mới
                    tid = str(self._next_id)
                    self._next_id += 1
                    self._total_vehicles_tracked += 1
                    self._tracks[tid] = {
                        "cx": det["cx"],
                        "cy": det["cy"],
                        "norm_box": det["norm_box"],
                        "class": det.get("class", ""),
                        "speed_history": deque(maxlen=SPEED_HISTORY_SIZE),
                        "last_speed": 0.0,
                        "age": 0,
                    }
                    results.append(self._build_result(tid, det, 0.0))

            # Tăng age và xóa track cũ
            to_del = []
            for tid, track in self._tracks.items():
                if tid not in matched_ids:
                    track["age"] += 1
                    if track["age"] > MAX_TRACK_AGE:
                        to_del.append(tid)
            for tid in to_del:
                del self._tracks[tid]

            return results

    def get_stats(self) -> dict[str, Any]:
        """Thống kê tổng hợp tốc độ."""
        with self._lock:
            records = list(self._speed_records)
            active_tracks = len(self._tracks)

        if not records:
            return {
                "active_tracks": active_tracks,
                "total_vehicles_tracked": self._total_vehicles_tracked,
                "overspeed_count": self._overspeed_count,
                "avg_speed_kmh": 0.0,
                "max_speed_kmh": 0.0,
                "speed_limit_kmh": self.speed_limit_kmh,
                "recent_speeds": [],
                "config": {
                    "fps": self.fps,
                    "pixels_per_meter": self.pixels_per_meter,
                    "fisheye_correction": self.fisheye_correction,
                },
            }

        speeds = [r["speed_kmh"] for r in records if r["speed_kmh"] > 0]
        avg_speed = round(sum(speeds) / len(speeds), 1) if speeds else 0.0
        max_speed = round(max(speeds), 1) if speeds else 0.0

        # Phân bố tốc độ
        dist = {"slow": 0, "normal": 0, "fast": 0, "overspeed": 0}
        for s in speeds:
            if s < 20:
                dist["slow"] += 1
            elif s < 40:
                dist["normal"] += 1
            elif s <= self.speed_limit_kmh:
                dist["fast"] += 1
            else:
                dist["overspeed"] += 1

        return {
            "active_tracks": active_tracks,
            "total_vehicles_tracked": self._total_vehicles_tracked,
            "overspeed_count": self._overspeed_count,
            "avg_speed_kmh": avg_speed,
            "max_speed_kmh": max_speed,
            "speed_limit_kmh": self.speed_limit_kmh,
            "speed_distribution": dist,
            "recent_speeds": list(self._speed_records)[-20:],
            "config": {
                "fps": self.fps,
                "pixels_per_meter": self.pixels_per_meter,
                "fisheye_correction": self.fisheye_correction,
            },
        }

    def get_current_speeds(self) -> list[dict[str, Any]]:
        """Tốc độ hiện tại của tất cả track đang active."""
        with self._lock:
            result = []
            for tid, track in self._tracks.items():
                speed = track.get("last_speed", 0.0)
                result.append({
                    "track_id": tid,
                    "class": track.get("class", ""),
                    "speed_kmh": round(speed, 1),
                    "is_overspeed": speed > self.speed_limit_kmh,
                    "speed_label": self._speed_label(speed),
                    "speed_color": self._speed_color(speed),
                    "cx": round(track.get("cx", 0), 3),
                    "cy": round(track.get("cy", 0), 3),
                })
            return sorted(result, key=lambda x: x["speed_kmh"], reverse=True)

    def update_config(
        self,
        fps: float | None = None,
        pixels_per_meter: float | None = None,
        speed_limit_kmh: float | None = None,
    ) -> None:
        with self._lock:
            if fps is not None:
                self.fps = max(1.0, fps)
            if pixels_per_meter is not None:
                self.pixels_per_meter = max(0.1, pixels_per_meter)
            if speed_limit_kmh is not None:
                self.speed_limit_kmh = max(1.0, speed_limit_kmh)

    def reset(self) -> None:
        with self._lock:
            self._tracks.clear()
            self._speed_records.clear()
            self._overspeed_count = 0
            self._total_vehicles_tracked = 0
            self._frame_count = 0

    # ── Private helpers ───────────────────────────────────────────────────────

    def _px_to_kmh(
        self,
        displacement_px: float,
        cx: float, cy: float,
        frame_width: int, frame_height: int,
    ) -> float:
        """Chuyển displacement pixel/frame → km/h."""
        if displacement_px < MIN_DISPLACEMENT_PX:
            return 0.0

        ppm = self.pixels_per_meter

        # Fisheye correction: vật ở rìa bị co lại → scale up
        if self.fisheye_correction:
            # Khoảng cách từ tâm ảnh (normalized 0-1)
            dist_from_center = math.hypot(cx - 0.5, cy - 0.5)
            # Scale factor: tăng dần từ tâm ra rìa (max ~1.8x ở góc)
            correction = 1.0 + dist_from_center * 1.6
            ppm = ppm / correction  # px/m nhỏ hơn ở rìa → tốc độ lớn hơn

        # m/frame → m/s → km/h
        meters_per_frame = displacement_px / ppm
        meters_per_second = meters_per_frame * self.fps
        kmh = meters_per_second * 3.6

        return min(kmh, MAX_SPEED_KMH)

    @staticmethod
    def _smooth_speed(history: deque) -> float:
        """Weighted moving average — frame gần nhất có trọng số cao hơn."""
        if not history:
            return 0.0
        vals = list(history)
        if len(vals) == 1:
            return vals[0]
        weights = list(range(1, len(vals) + 1))
        total_w = sum(weights)
        return sum(v * w for v, w in zip(vals, weights)) / total_w

    @staticmethod
    def _iou(box_a: list, box_b: list) -> float:
        xa1, ya1, xa2, ya2 = box_a
        xb1, yb1, xb2, yb2 = box_b
        ix1, iy1 = max(xa1, xb1), max(ya1, yb1)
        ix2, iy2 = min(xa2, xb2), min(ya2, yb2)
        if ix2 <= ix1 or iy2 <= iy1:
            return 0.0
        inter = (ix2 - ix1) * (iy2 - iy1)
        area_a = (xa2 - xa1) * (ya2 - ya1)
        area_b = (xb2 - xb1) * (yb2 - yb1)
        union = area_a + area_b - inter
        return inter / union if union > 0 else 0.0

    @staticmethod
    def _speed_label(speed: float) -> str:
        if speed <= 0:
            return "—"
        if speed < 20:
            return "Chậm"
        if speed < 40:
            return "Bình thường"
        if speed < 70:
            return "Nhanh"
        return "Quá tốc"

    @staticmethod
    def _speed_color(speed: float) -> str:
        if speed < 40:
            return SPEED_COLORS["normal"]
        if speed < 70:
            return SPEED_COLORS["moderate"]
        return SPEED_COLORS["fast"]

    def _build_result(
        self,
        track_id: str,
        det: dict[str, Any],
        speed: float,
    ) -> dict[str, Any]:
        is_overspeed = speed > self.speed_limit_kmh and speed > 0
        return {
            "track_id": track_id,
            "class": det.get("class", ""),
            "confidence": round(float(det.get("confidence", 0)), 3),
            "bbox": det.get("bbox", []),
            "speed_kmh": round(speed, 1),
            "speed_label": self._speed_label(speed),
            "speed_color": self._speed_color(speed),
            "is_overspeed": is_overspeed,
            "cx": round(det.get("cx", 0), 3),
            "cy": round(det.get("cy", 0), 3),
        }


# ── Annotate frame với speed overlay ─────────────────────────────────────────

def annotate_speed_on_frame(
    frame_bgr: "np.ndarray",
    speed_results: list[dict[str, Any]],
    frame_width: int,
    frame_height: int,
    speed_limit_kmh: float = 60.0,
) -> "np.ndarray":
    """
    Vẽ tốc độ lên frame BGR (OpenCV).
    Gọi sau khi đã vẽ bbox YOLO.
    """
    try:
        import cv2
        import numpy as np
    except ImportError:
        return frame_bgr

    out = frame_bgr.copy()

    for item in speed_results:
        speed = item.get("speed_kmh", 0.0)
        if speed <= 0:
            continue

        bbox = item.get("bbox", [])
        if len(bbox) < 4:
            continue

        x1, y1, x2, y2 = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
        is_overspeed = item.get("is_overspeed", False)

        # Màu: đỏ nếu quá tốc, xanh nếu bình thường
        color_bgr = (0, 60, 220) if is_overspeed else (200, 200, 50)

        # Vẽ speed badge phía trên bbox
        label = f"{speed:.0f} km/h"
        if is_overspeed:
            label = f"⚡{speed:.0f} km/h"

        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.5
        thickness = 1
        (tw, th), baseline = cv2.getTextSize(label, font, font_scale, thickness)

        # Background pill
        pad = 3
        bx1 = x1
        by1 = max(0, y1 - th - pad * 2 - 18)  # acima do bbox YOLO label
        bx2 = x1 + tw + pad * 2
        by2 = by1 + th + pad * 2

        cv2.rectangle(out, (bx1, by1), (bx2, by2), color_bgr, -1)
        cv2.putText(
            out, label,
            (bx1 + pad, by2 - pad - baseline),
            font, font_scale, (255, 255, 255), thickness, cv2.LINE_AA,
        )

        # Nếu quá tốc: vẽ viền đỏ nháy quanh bbox
        if is_overspeed:
            cv2.rectangle(out, (x1, y1), (x2, y2), (0, 0, 255), 3)

    return out

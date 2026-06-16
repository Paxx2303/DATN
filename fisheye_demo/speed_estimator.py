"""
speed_estimator.py — Vehicle Speed Estimation + Violation Detection

PHƯƠNG PHÁP:
- Theo dõi lịch sử vị trí center point của mỗi track_id.
- Tính displacement (pixel) giữa các frame.
- Nhân với scale_factor (px → mét) và fps để ra m/s → km/h.

GIỚI HẠN:
- Không có calibration thực tế → kết quả là ước lượng tương đối.
- scale_factor phải được calibrate dựa trên kích thước thực của cảnh quay.
"""

import cv2
import numpy as np
import time
import threading
import logging
from collections import deque
from typing import Optional

logger = logging.getLogger(__name__)

HISTORY_FRAMES = 10
DEFAULT_SPEED_LIMIT = 50.0  # km/h
VIOLATION_CONSECUTIVE_FRAMES = 3
VIOLATION_COOLDOWN_SECONDS = 30.0


class SpeedEstimator:
    """Theo dõi và ước lượng tốc độ cho nhiều vehicles cùng lúc."""

    def __init__(
        self,
        fps: float = 25.0,
        scale_factor: float = 0.05,
        pixels_per_meter: float = None,
        fisheye_correction: bool = False,
        speed_limit_kmh: float = DEFAULT_SPEED_LIMIT,
    ):
        """
        Parameters
        ----------
        fps              : FPS của video nguồn
        scale_factor     : px → mét (legacy, dùng nếu pixels_per_meter=None)
        pixels_per_meter : px/m calibration (ưu tiên hơn scale_factor)
        fisheye_correction: có hiệu chỉnh fisheye distortion không
        speed_limit_kmh  : ngưỡng tốc độ cho SpeedViolationChecker
        """
        self._fps = max(fps, 1.0)
        if pixels_per_meter is not None:
            self._scale = 1.0 / max(pixels_per_meter, 0.001)
        else:
            self._scale = scale_factor
        self._fisheye = fisheye_correction
        self.fps = self._fps
        self.pixels_per_meter = pixels_per_meter or (1.0 / self._scale)
        self.speed_limit_kmh = speed_limit_kmh

        # track_id → deque[(frame_idx, cx, cy)]
        self._tracks: dict[int, deque] = {}
        # track_id → smoothed speed (km/h)
        self._speeds: dict[int, float] = {}
        # track_id → class_name
        self._classes: dict[int, str] = {}

        self._lock = threading.Lock()
        self._violation_checker = SpeedViolationChecker(
            speed_limit_kmh=speed_limit_kmh,
            consecutive_frames=VIOLATION_CONSECUTIVE_FRAMES,
        )

    def update(self, detections, frame_width: int = 640, frame_height: int = 480):
        """
        Overloaded: nhận list[dict] (từ camera_monitor) hoặc gọi từ pipeline.
        detections: list of {"class": str, "bbox": [x1,y1,x2,y2], "track_id": int, ...}
        """
        results = []
        with self._lock:
            for det in detections:
                track_id = det.get("track_id")
                if track_id is None:
                    continue
                x1, y1, x2, y2 = det["bbox"]
                cx = int((x1 + x2) / 2)
                cy = int((y1 + y2) / 2)
                cls = det.get("class", "unknown")
                frame_idx = det.get("frame_idx", 0)

                self._update_track(track_id, cx, cy, frame_idx, cls)
                speed = self._speeds.get(track_id, 0.0)

                violation = self._violation_checker.check(track_id, speed, frame_idx)
                results.append({
                    "track_id":   track_id,
                    "class":      cls,
                    "speed_kmh":  speed,
                    "is_overspeed": speed > self.speed_limit_kmh and speed > 0,
                    "violation":  violation,
                    "bbox":       [x1, y1, x2, y2],
                })
        return results

    def _update_track(self, track_id: int, cx: int, cy: int,
                      frame_idx: int, class_name: str = "unknown") -> None:
        """Cập nhật vị trí track và tính lại speed."""
        if track_id not in self._tracks:
            self._tracks[track_id] = deque(maxlen=HISTORY_FRAMES)
        self._tracks[track_id].append((frame_idx, cx, cy))
        self._classes[track_id] = class_name
        if len(self._tracks[track_id]) >= 2:
            self._speeds[track_id] = self._compute_speed(track_id)

    def update_single(self, track_id: int, cx: int, cy: int,
                      frame_idx: int, vehicle_type: str = "unknown") -> float:
        """Cập nhật 1 track, trả về tốc độ km/h."""
        with self._lock:
            self._update_track(track_id, cx, cy, frame_idx, vehicle_type)
            return self._speeds.get(track_id, 0.0)

    def _compute_speed(self, track_id: int) -> float:
        history = list(self._tracks[track_id])
        total_dist_px = 0.0
        total_frames = 0
        for i in range(1, len(history)):
            f0, x0, y0 = history[i - 1]
            f1, x1, y1 = history[i]
            dist = np.sqrt((x1 - x0) ** 2 + (y1 - y0) ** 2)
            total_dist_px += dist
            total_frames += (f1 - f0)
        if total_frames == 0:
            return 0.0
        speed_ms = (total_dist_px * self._scale) / (total_frames / self._fps)
        speed_kmh = speed_ms * 3.6
        return round(float(np.clip(speed_kmh, 0.0, 200.0)), 1)

    def get_speed(self, track_id: int) -> float:
        return self._speeds.get(track_id, 0.0)

    def get_average_speed(self) -> float:
        active = [s for s in self._speeds.values() if s > 0]
        return round(sum(active) / len(active), 1) if active else 0.0

    def get_max_speed(self) -> float:
        active = [s for s in self._speeds.values() if s > 0]
        return round(max(active), 1) if active else 0.0

    def get_all_speeds(self) -> dict:
        return dict(self._speeds)

    def get_current_speeds(self) -> list:
        with self._lock:
            return [
                {"track_id": tid, "speed_kmh": spd, "class": self._classes.get(tid, "unknown")}
                for tid, spd in self._speeds.items()
                if spd > 0
            ]

    def get_stats(self) -> dict:
        with self._lock:
            active = [s for s in self._speeds.values() if s > 0]
            return {
                "avg_speed_kmh": round(sum(active) / len(active), 1) if active else 0.0,
                "max_speed_kmh": round(max(active), 1) if active else 0.0,
                "tracked_count": len(self._speeds),
                "speed_limit_kmh": self.speed_limit_kmh,
            }

    def update_config(self, fps=None, pixels_per_meter=None, speed_limit_kmh=None):
        with self._lock:
            if fps is not None:
                self._fps = max(float(fps), 1.0)
                self.fps = self._fps
            if pixels_per_meter is not None:
                self.pixels_per_meter = float(pixels_per_meter)
                self._scale = 1.0 / max(self.pixels_per_meter, 0.001)
            if speed_limit_kmh is not None:
                self.speed_limit_kmh = float(speed_limit_kmh)
                self._violation_checker.speed_limit_kmh = self.speed_limit_kmh

    def get_violations(self) -> list:
        return self._violation_checker.get_violations()

    def reset(self) -> None:
        with self._lock:
            self._tracks.clear()
            self._speeds.clear()
            self._classes.clear()
            self._violation_checker.reset()

    def remove_track(self, track_id: int) -> None:
        self._tracks.pop(track_id, None)
        self._speeds.pop(track_id, None)
        self._classes.pop(track_id, None)


class SpeedViolationChecker:
    """
    Phát hiện vi phạm tốc độ khi xe vượt ngưỡng N frame liên tiếp.
    Dedup: mỗi track_id chỉ 1 violation per VIOLATION_COOLDOWN_SECONDS.
    """

    def __init__(
        self,
        speed_limit_kmh: float = DEFAULT_SPEED_LIMIT,
        consecutive_frames: int = VIOLATION_CONSECUTIVE_FRAMES,
    ):
        self.speed_limit_kmh = speed_limit_kmh
        self.consecutive_frames = consecutive_frames

        # track_id → số frame liên tiếp vượt ngưỡng
        self._over_count: dict[int, int] = {}
        # Danh sách violations
        self._violations: list[dict] = []
        # Dedup: track_id → timestamp báo lần cuối
        self._last_reported: dict[int, float] = {}
        self._lock = threading.Lock()

    def check(self, track_id: int, speed_kmh: float,
              frame_idx: int) -> Optional[dict]:
        """
        Kiểm tra vi phạm tốc độ.

        Returns
        -------
        dict vi phạm nếu vừa đạt ngưỡng, None nếu không.
        """
        with self._lock:
            if speed_kmh <= 0:
                self._over_count[track_id] = 0
                return None

            if speed_kmh > self.speed_limit_kmh:
                self._over_count[track_id] = self._over_count.get(track_id, 0) + 1
            else:
                self._over_count[track_id] = 0
                return None

            if self._over_count[track_id] < self.consecutive_frames:
                return None

            # Kiểm tra cooldown
            now = time.time()
            last = self._last_reported.get(track_id, 0.0)
            if now - last < VIOLATION_COOLDOWN_SECONDS:
                return None

            self._last_reported[track_id] = now
            self._over_count[track_id] = 0  # reset sau khi báo

            violation = {
                "track_id":       track_id,
                "speed_kmh":      round(speed_kmh, 1),
                "limit_kmh":      self.speed_limit_kmh,
                "excess_kmh":     round(speed_kmh - self.speed_limit_kmh, 1),
                "frame_idx":      frame_idx,
                "timestamp":      now,
            }
            self._violations.append(violation)
            logger.warning(
                "Speed violation: track=%d %.1f km/h (limit %.0f km/h)",
                track_id, speed_kmh, self.speed_limit_kmh,
            )
            return violation

    def get_violations(self) -> list:
        with self._lock:
            return list(self._violations)

    def reset(self) -> None:
        with self._lock:
            self._over_count.clear()
            self._violations.clear()
            self._last_reported.clear()


def annotate_speed_on_frame(
    frame: np.ndarray,
    speed_results: list,
    frame_width: int,
    frame_height: int,
    speed_limit_kmh: float = DEFAULT_SPEED_LIMIT,
) -> np.ndarray:
    """
    Vẽ bbox và nhãn tốc độ lên frame.
    Vi phạm → bbox đỏ + nhãn ⚠.
    """
    for res in speed_results:
        speed = res.get("speed_kmh", 0.0)
        is_over = res.get("is_overspeed", False)
        bbox = res.get("bbox", [])
        if len(bbox) < 4:
            continue
        x1, y1, x2, y2 = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])

        color = (0, 0, 255) if is_over else (0, 200, 100)
        thickness = 3 if is_over else 2
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness)

        if speed > 0:
            label = f"{'⚠ ' if is_over else ''}{speed:.0f} km/h"
            if is_over:
                excess = speed - speed_limit_kmh
                label = f"⚠ {speed:.0f}km/h (+{excess:.0f})"
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            tx, ty = x1, max(y1 - 5, th + 5)
            cv2.rectangle(frame, (tx, ty - th - 4), (tx + tw + 4, ty + 2), color, -1)
            cv2.putText(frame, label, (tx + 2, ty),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
    return frame

"""
analytics.py — Traffic analytics engine cho fisheye_demo

Chức năng:
- Đếm xe theo class, theo giờ, theo nguồn camera
- Line crossing counter (đếm xe qua đường kẻ)
- Heatmap tích lũy vị trí bbox
- Phát hiện giờ cao điểm
- Tổng hợp dữ liệu cho dashboard
"""
from __future__ import annotations

import json
import logging
import math
import threading
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

import numpy as np

logger = logging.getLogger("fisheye_demo.analytics")

CLASS_NAMES = ["Car", "Bus", "Truck", "Pedestrian", "Motorbike"]


# ── Line Counter ─────────────────────────────────────────────────────────────

class LineCrossingCounter:
    """
    Đếm số lượng đối tượng đi qua một đường kẻ ảo.

    Nguyên lý:
    - Mỗi detection có bbox (x1,y1,x2,y2)
    - Tính centroid = ((x1+x2)/2, (y1+y2)/2)
    - Kiểm tra centroid có cắt qua line không (so sánh phía của centroid với line)
    - Dùng tracking ID đơn giản dựa trên IoU để theo dõi object qua frame
    """

    def __init__(
        self,
        line_start: tuple[float, float],
        line_end: tuple[float, float],
        name: str = "line_1",
    ) -> None:
        self.line_start = line_start  # (x, y) normalized 0-1
        self.line_end = line_end
        self.name = name
        self._lock = threading.Lock()
        self._counts: dict[str, int] = {cls: 0 for cls in CLASS_NAMES}
        self._counts["in"] = 0
        self._counts["out"] = 0
        self._total = 0
        # Track previous positions: {track_id: (cx, cy, side)}
        self._tracks: dict[str, dict[str, Any]] = {}
        self._next_track_id = 0

    def _side_of_line(self, px: float, py: float) -> int:
        """Trả về 1 hoặc -1 tùy thuộc vào phía của điểm so với đường kẻ."""
        x1, y1 = self.line_start
        x2, y2 = self.line_end
        cross = (x2 - x1) * (py - y1) - (y2 - y1) * (px - x1)
        return 1 if cross >= 0 else -1

    def _iou(self, box_a: list, box_b: list) -> float:
        """Tính IoU giữa 2 bbox."""
        xa1, ya1, xa2, ya2 = box_a
        xb1, yb1, xb2, yb2 = box_b
        inter_x1 = max(xa1, xb1)
        inter_y1 = max(ya1, yb1)
        inter_x2 = min(xa2, xb2)
        inter_y2 = min(ya2, yb2)
        if inter_x2 <= inter_x1 or inter_y2 <= inter_y1:
            return 0.0
        inter_area = (inter_x2 - inter_x1) * (inter_y2 - inter_y1)
        area_a = (xa2 - xa1) * (ya2 - ya1)
        area_b = (xb2 - xb1) * (yb2 - yb1)
        union_area = area_a + area_b - inter_area
        return inter_area / union_area if union_area > 0 else 0.0

    def update(self, detections: list[dict[str, Any]], frame_width: int = 1, frame_height: int = 1) -> dict[str, Any]:
        """
        Cập nhật với danh sách detections của frame hiện tại.

        detections: list of {"class": str, "bbox": [x1,y1,x2,y2], "confidence": float}
        bbox có thể là pixel hoặc normalized (tùy frame_width/frame_height)
        """
        with self._lock:
            new_crossings: list[dict[str, Any]] = []
            current_boxes = []

            for det in detections:
                bbox = det.get("bbox", [0, 0, 0, 0])
                x1, y1, x2, y2 = bbox
                # Normalize về 0-1
                cx = ((x1 + x2) / 2) / frame_width
                cy = ((y1 + y2) / 2) / frame_height
                norm_box = [x1 / frame_width, y1 / frame_height, x2 / frame_width, y2 / frame_height]
                current_boxes.append({
                    "class": det.get("class", ""),
                    "cx": cx,
                    "cy": cy,
                    "norm_box": norm_box,
                    "side": self._side_of_line(cx, cy),
                })

            # Match với tracks cũ bằng IoU
            matched_track_ids: set[str] = set()
            for box in current_boxes:
                best_iou = 0.3  # ngưỡng tối thiểu
                best_track_id = None
                for track_id, track in self._tracks.items():
                    if track_id in matched_track_ids:
                        continue
                    iou = self._iou(box["norm_box"], track["norm_box"])
                    if iou > best_iou:
                        best_iou = iou
                        best_track_id = track_id

                if best_track_id is not None:
                    # Update track
                    old_side = self._tracks[best_track_id]["side"]
                    new_side = box["side"]
                    if old_side != new_side:
                        # Đã cắt qua line
                        cls = box["class"]
                        direction = "in" if new_side == 1 else "out"
                        self._counts[cls] = self._counts.get(cls, 0) + 1
                        self._counts[direction] = self._counts.get(direction, 0) + 1
                        self._total += 1
                        new_crossings.append({
                            "class": cls,
                            "direction": direction,
                            "cx": box["cx"],
                            "cy": box["cy"],
                        })
                    self._tracks[best_track_id].update({
                        "cx": box["cx"],
                        "cy": box["cy"],
                        "side": new_side,
                        "norm_box": box["norm_box"],
                        "age": 0,
                    })
                    matched_track_ids.add(best_track_id)
                else:
                    # Track mới
                    track_id = str(self._next_track_id)
                    self._next_track_id += 1
                    self._tracks[track_id] = {
                        "cx": box["cx"],
                        "cy": box["cy"],
                        "side": box["side"],
                        "norm_box": box["norm_box"],
                        "class": box["class"],
                        "age": 0,
                    }

            # Tăng age và xóa track cũ (> 30 frame không thấy)
            to_delete = []
            for track_id, track in self._tracks.items():
                if track_id not in matched_track_ids:
                    track["age"] = track.get("age", 0) + 1
                    if track["age"] > 30:
                        to_delete.append(track_id)
            for track_id in to_delete:
                del self._tracks[track_id]

            return {
                "new_crossings": new_crossings,
                "total": self._total,
                "counts": dict(self._counts),
            }

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "name": self.name,
                "line_start": self.line_start,
                "line_end": self.line_end,
                "total_crossings": self._total,
                "counts": dict(self._counts),
                "active_tracks": len(self._tracks),
            }

    def reset(self) -> None:
        with self._lock:
            self._counts = {cls: 0 for cls in CLASS_NAMES}
            self._counts["in"] = 0
            self._counts["out"] = 0
            self._total = 0
            self._tracks = {}


# ── Heatmap Generator ────────────────────────────────────────────────────────

class DetectionHeatmap:
    """
    Tích lũy vị trí bbox để tạo heatmap.
    Lưu dưới dạng grid 2D, có thể export ra base64 JPEG.
    """

    def __init__(self, grid_w: int = 64, grid_h: int = 64) -> None:
        self.grid_w = grid_w
        self.grid_h = grid_h
        self._grid = np.zeros((grid_h, grid_w), dtype=np.float32)
        self._lock = threading.Lock()
        self._total_detections = 0

    def update(self, detections: list[dict[str, Any]], frame_width: int = 1, frame_height: int = 1) -> None:
        """Thêm detections vào heatmap."""
        with self._lock:
            for det in detections:
                bbox = det.get("bbox", [0, 0, 0, 0])
                x1, y1, x2, y2 = bbox
                # Normalize
                cx = ((x1 + x2) / 2) / frame_width
                cy = ((y1 + y2) / 2) / frame_height
                # Map vào grid
                gx = min(int(cx * self.grid_w), self.grid_w - 1)
                gy = min(int(cy * self.grid_h), self.grid_h - 1)
                self._grid[gy, gx] += 1
                self._total_detections += 1

    def get_grid_normalized(self) -> list[list[float]]:
        """Trả về grid normalized 0-1."""
        with self._lock:
            max_val = float(self._grid.max())
            if max_val == 0:
                return self._grid.tolist()
            return (self._grid / max_val).tolist()

    def to_base64_jpeg(self, colormap: str = "hot") -> str | None:
        """Export heatmap thành base64 JPEG."""
        try:
            import base64
            import io as _io
            from PIL import Image

            with self._lock:
                grid = self._grid.copy()

            max_val = grid.max()
            if max_val > 0:
                grid = grid / max_val

            # Áp dụng colormap đơn giản (hot: đen → đỏ → vàng → trắng)
            r = np.clip(grid * 3, 0, 1)
            g = np.clip(grid * 3 - 1, 0, 1)
            b = np.clip(grid * 3 - 2, 0, 1)
            rgb = np.stack([r, g, b], axis=-1)
            rgb_uint8 = (rgb * 255).astype(np.uint8)

            # Resize lên 256x256
            img = Image.fromarray(rgb_uint8, mode="RGB")
            img = img.resize((256, 256), Image.Resampling.NEAREST)

            buf = _io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
        except Exception as exc:
            logger.warning("Heatmap to base64 failed: %s", exc)
            return None

    def reset(self) -> None:
        with self._lock:
            self._grid = np.zeros((self.grid_h, self.grid_w), dtype=np.float32)
            self._total_detections = 0

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "total_detections": self._total_detections,
                "grid_size": f"{self.grid_w}x{self.grid_h}",
                "max_density": float(self._grid.max()),
            }


# ── Traffic Density Analyzer ─────────────────────────────────────────────────

class TrafficDensityAnalyzer:
    """
    Phân tích mật độ giao thông theo thời gian thực.
    Tính toán:
    - Mật độ hiện tại (objects/frame)
    - Xu hướng (tăng/giảm/ổn định)
    - Phát hiện giờ cao điểm
    - Cảnh báo khi vượt ngưỡng
    """

    def __init__(
        self,
        window_size: int = 30,  # số frame để tính trung bình
        alert_threshold: int = 20,  # số object/frame để cảnh báo
    ) -> None:
        self.window_size = window_size
        self.alert_threshold = alert_threshold
        self._lock = threading.Lock()
        self._history: list[dict[str, Any]] = []  # list of {timestamp, total, class_counts}
        self._alert_callbacks: list = []

    def add_alert_callback(self, callback) -> None:
        """Đăng ký callback khi có alert."""
        self._alert_callbacks.append(callback)

    def update(self, total_objects: int, class_counts: dict[str, int]) -> dict[str, Any]:
        """Cập nhật với kết quả detect mới."""
        with self._lock:
            now = datetime.now(timezone.utc).isoformat()
            self._history.append({
                "timestamp": now,
                "total": total_objects,
                "class_counts": dict(class_counts),
            })
            # Giữ window_size * 10 entries
            if len(self._history) > self.window_size * 10:
                self._history = self._history[-self.window_size * 10:]

            # Tính stats
            recent = self._history[-self.window_size:]
            avg_total = sum(h["total"] for h in recent) / len(recent) if recent else 0
            trend = self._compute_trend(recent)
            is_peak = avg_total >= self.alert_threshold

            result = {
                "current_total": total_objects,
                "avg_total": round(avg_total, 1),
                "trend": trend,
                "is_peak_hour": is_peak,
                "alert_threshold": self.alert_threshold,
                "window_size": len(recent),
            }

            # Trigger alert nếu vượt ngưỡng
            if is_peak and total_objects >= self.alert_threshold:
                for cb in self._alert_callbacks:
                    try:
                        cb(total_objects, class_counts, avg_total)
                    except Exception:
                        pass

            return result

    def _compute_trend(self, history: list[dict[str, Any]]) -> str:
        if len(history) < 5:
            return "stable"
        first_half = history[:len(history) // 2]
        second_half = history[len(history) // 2:]
        avg_first = sum(h["total"] for h in first_half) / len(first_half)
        avg_second = sum(h["total"] for h in second_half) / len(second_half)
        diff = avg_second - avg_first
        if diff > 2:
            return "increasing"
        if diff < -2:
            return "decreasing"
        return "stable"

    def get_summary(self) -> dict[str, Any]:
        with self._lock:
            if not self._history:
                return {"total_frames": 0, "avg_objects": 0, "peak_count": 0}

            totals = [h["total"] for h in self._history]
            class_totals: dict[str, int] = defaultdict(int)
            for h in self._history:
                for cls, cnt in h.get("class_counts", {}).items():
                    class_totals[cls] += cnt

            return {
                "total_frames": len(self._history),
                "avg_objects": round(sum(totals) / len(totals), 1),
                "peak_count": max(totals),
                "min_count": min(totals),
                "class_totals": dict(class_totals),
                "trend": self._compute_trend(self._history[-self.window_size:]),
            }

    def reset(self) -> None:
        with self._lock:
            self._history = []


# ── Analytics aggregator ─────────────────────────────────────────────────────

def build_analytics_from_db(hours: int = 24) -> dict[str, Any]:
    """
    Tổng hợp analytics từ DB cho dashboard.
    """
    try:
        try:
            from db import get_dashboard_stats, get_hourly_traffic_chart, list_alerts
        except ImportError:
            from fisheye_demo.db import get_dashboard_stats, get_hourly_traffic_chart, list_alerts

        stats = get_dashboard_stats(hours=hours)
        hourly_chart = get_hourly_traffic_chart(hours=hours)
        recent_alerts = list_alerts(limit=10, unacknowledged_only=False)

        # Tính peak hour
        peak_hour = None
        peak_count = 0
        for bucket in hourly_chart:
            total = sum(bucket.get("counts", {}).values())
            if total > peak_count:
                peak_count = total
                peak_hour = bucket.get("hour")

        return {
            "stats": stats,
            "hourly_chart": hourly_chart,
            "recent_alerts": recent_alerts,
            "peak_hour": peak_hour,
            "peak_count": peak_count,
            "hours_window": hours,
        }
    except Exception as exc:
        logger.error("build_analytics_from_db failed: %s", exc)
        return {
            "stats": {},
            "hourly_chart": [],
            "recent_alerts": [],
            "error": str(exc),
        }


def compute_class_percentages(class_counts: dict[str, int]) -> dict[str, float]:
    """Tính phần trăm từng class."""
    total = sum(class_counts.values())
    if total == 0:
        return {cls: 0.0 for cls in class_counts}
    return {cls: round(cnt / total * 100, 1) for cls, cnt in class_counts.items()}


def detect_peak_hours(hourly_data: list[dict[str, Any]], top_n: int = 3) -> list[dict[str, Any]]:
    """Tìm N giờ cao điểm nhất."""
    scored = []
    for bucket in hourly_data:
        total = sum(bucket.get("counts", {}).values())
        scored.append({"hour": bucket.get("hour"), "total": total, "counts": bucket.get("counts", {})})
    scored.sort(key=lambda x: x["total"], reverse=True)
    return scored[:top_n]

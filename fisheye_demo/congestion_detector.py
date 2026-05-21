"""
congestion_detector.py — Phát hiện ùn tắc theo vùng ROI (Region of Interest)

Nguyên lý:
  - Chia ảnh thành các vùng ROI (có thể tùy chỉnh)
  - Đếm số lượng vehicle trong mỗi ROI mỗi frame
  - Tính mật độ = số xe / diện tích ROI (normalized)
  - So sánh với ngưỡng để phân loại: FREE / SLOW / CONGESTED / JAMMED
  - Theo dõi lịch sử để tính xu hướng (đang tăng/giảm)

Mức độ ùn tắc (Level of Service — LoS):
  A (FREE)      — < 20% capacity  — xanh lá
  B (SLOW)      — 20-50%          — vàng
  C (CONGESTED) — 50-80%          — cam
  D (JAMMED)    — > 80%           — đỏ

Cách dùng:
  detector = CongestionDetector()
  detector.add_roi("intersection", x1=0.1, y1=0.1, x2=0.9, y2=0.9, capacity=15)
  for frame_detections in video_frames:
      status = detector.update(frame_detections, frame_w, frame_h)
"""
from __future__ import annotations

import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any

# Mức độ ùn tắc
LOS_FREE       = "FREE"        # Thông thoáng
LOS_SLOW       = "SLOW"        # Chậm
LOS_CONGESTED  = "CONGESTED"   # Ùn tắc
LOS_JAMMED     = "JAMMED"      # Kẹt xe nặng

LOS_COLORS = {
    LOS_FREE:      "#4CAF50",   # xanh lá
    LOS_SLOW:      "#FFD166",   # vàng
    LOS_CONGESTED: "#FF9800",   # cam
    LOS_JAMMED:    "#F44336",   # đỏ
}

LOS_LABELS_VI = {
    LOS_FREE:      "Thông thoáng",
    LOS_SLOW:      "Chậm",
    LOS_CONGESTED: "Ùn tắc",
    LOS_JAMMED:    "Kẹt xe nặng",
}

VEHICLE_CLASSES = {"Car", "Bus", "Truck", "Motorbike"}

# Trọng số đóng góp vào mật độ theo loại xe
VEHICLE_WEIGHTS = {
    "Car":        1.0,
    "Motorbike":  0.5,
    "Bus":        2.5,
    "Truck":      2.0,
    "Pedestrian": 0.3,
}

HISTORY_SIZE = 60   # số frame lưu lịch sử mỗi ROI


class ROIZone:
    """Một vùng ROI với lịch sử mật độ."""

    def __init__(
        self,
        name: str,
        x1: float, y1: float,
        x2: float, y2: float,
        capacity: int = 10,
    ) -> None:
        self.name = name
        # Tọa độ normalized 0-1
        self.x1 = max(0.0, min(1.0, x1))
        self.y1 = max(0.0, min(1.0, y1))
        self.x2 = max(0.0, min(1.0, x2))
        self.y2 = max(0.0, min(1.0, y2))
        self.capacity = max(1, capacity)

        self._history: deque = deque(maxlen=HISTORY_SIZE)
        self._current_count = 0
        self._current_weighted = 0.0
        self._current_los = LOS_FREE
        self._congestion_start: float | None = None
        self._total_congestion_seconds = 0.0
        self._last_update = time.time()

    def contains(self, cx: float, cy: float) -> bool:
        return self.x1 <= cx <= self.x2 and self.y1 <= cy <= self.y2

    def update(self, count: int, weighted_count: float) -> dict[str, Any]:
        now = time.time()
        dt = now - self._last_update
        self._last_update = now

        self._current_count = count
        self._current_weighted = weighted_count

        # Tính occupancy ratio
        occupancy = weighted_count / self.capacity

        # Phân loại LoS
        if occupancy < 0.2:
            los = LOS_FREE
        elif occupancy < 0.5:
            los = LOS_SLOW
        elif occupancy < 0.8:
            los = LOS_CONGESTED
        else:
            los = LOS_JAMMED

        # Theo dõi thời gian ùn tắc
        if los in (LOS_CONGESTED, LOS_JAMMED):
            if self._congestion_start is None:
                self._congestion_start = now
        else:
            if self._congestion_start is not None:
                self._total_congestion_seconds += now - self._congestion_start
                self._congestion_start = None

        self._current_los = los
        self._history.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "count": count,
            "weighted": round(weighted_count, 2),
            "occupancy": round(occupancy, 3),
            "los": los,
        })

        return self._snapshot(occupancy)

    def _snapshot(self, occupancy: float) -> dict[str, Any]:
        # Tính xu hướng từ lịch sử
        trend = self._compute_trend()
        congestion_duration = 0.0
        if self._congestion_start is not None:
            congestion_duration = time.time() - self._congestion_start

        return {
            "name": self.name,
            "roi": {"x1": self.x1, "y1": self.y1, "x2": self.x2, "y2": self.y2},
            "capacity": self.capacity,
            "current_count": self._current_count,
            "weighted_count": round(self._current_weighted, 2),
            "occupancy_pct": round(occupancy * 100, 1),
            "los": self._current_los,
            "los_label": LOS_LABELS_VI[self._current_los],
            "los_color": LOS_COLORS[self._current_los],
            "trend": trend,
            "congestion_duration_s": round(congestion_duration, 1),
            "total_congestion_s": round(self._total_congestion_seconds, 1),
        }

    def _compute_trend(self) -> str:
        hist = list(self._history)
        if len(hist) < 6:
            return "stable"
        half = len(hist) // 2
        avg_first = sum(h["count"] for h in hist[:half]) / half
        avg_second = sum(h["count"] for h in hist[half:]) / (len(hist) - half)
        diff = avg_second - avg_first
        if diff > 1.5:
            return "increasing"
        if diff < -1.5:
            return "decreasing"
        return "stable"

    def get_history(self, last_n: int = 30) -> list[dict[str, Any]]:
        return list(self._history)[-last_n:]

    def reset_stats(self) -> None:
        self._history.clear()
        self._congestion_start = None
        self._total_congestion_seconds = 0.0


class CongestionDetector:
    """
    Phát hiện ùn tắc theo nhiều vùng ROI.
    Thread-safe.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._zones: dict[str, ROIZone] = {}
        self._frame_count = 0
        self._alert_callbacks: list = []

        # Thêm ROI mặc định: toàn bộ ảnh
        self.add_roi(
            name="full_frame",
            x1=0.0, y1=0.0, x2=1.0, y2=1.0,
            capacity=20,
        )
        # ROI trung tâm (giao lộ)
        self.add_roi(
            name="intersection",
            x1=0.25, y1=0.25, x2=0.75, y2=0.75,
            capacity=10,
        )

    # ── Public API ────────────────────────────────────────────────────────────

    def add_roi(
        self,
        name: str,
        x1: float, y1: float,
        x2: float, y2: float,
        capacity: int = 10,
    ) -> None:
        """Thêm hoặc cập nhật một vùng ROI."""
        with self._lock:
            self._zones[name] = ROIZone(name, x1, y1, x2, y2, capacity)

    def remove_roi(self, name: str) -> bool:
        with self._lock:
            if name in self._zones:
                del self._zones[name]
                return True
            return False

    def list_rois(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                {
                    "name": z.name,
                    "roi": {"x1": z.x1, "y1": z.y1, "x2": z.x2, "y2": z.y2},
                    "capacity": z.capacity,
                }
                for z in self._zones.values()
            ]

    def add_alert_callback(self, callback) -> None:
        self._alert_callbacks.append(callback)

    def update(
        self,
        detections: list[dict[str, Any]],
        frame_width: int,
        frame_height: int,
    ) -> dict[str, Any]:
        """
        Cập nhật với detections của frame hiện tại.

        Returns:
            dict với trạng thái tất cả ROI và overall status
        """
        with self._lock:
            self._frame_count += 1

            # Normalize centroid về 0-1
            norm_dets = []
            for det in detections:
                bbox = det.get("bbox", [0, 0, 0, 0])
                x1, y1, x2, y2 = bbox
                cx = ((x1 + x2) / 2) / frame_width
                cy = ((y1 + y2) / 2) / frame_height
                cls = det.get("class", "")
                weight = VEHICLE_WEIGHTS.get(cls, 1.0)
                norm_dets.append({"cx": cx, "cy": cy, "class": cls, "weight": weight})

            # Đếm xe trong từng ROI
            zone_results: list[dict[str, Any]] = []
            worst_los = LOS_FREE
            los_order = [LOS_FREE, LOS_SLOW, LOS_CONGESTED, LOS_JAMMED]

            for zone in self._zones.values():
                count = 0
                weighted = 0.0
                for det in norm_dets:
                    if zone.contains(det["cx"], det["cy"]):
                        count += 1
                        weighted += det["weight"]

                result = zone.update(count, weighted)
                zone_results.append(result)

                # Track worst LoS
                if los_order.index(result["los"]) > los_order.index(worst_los):
                    worst_los = result["los"]

            # Overall status
            overall = {
                "los": worst_los,
                "los_label": LOS_LABELS_VI[worst_los],
                "los_color": LOS_COLORS[worst_los],
                "total_vehicles": len([d for d in norm_dets if d["class"] in VEHICLE_CLASSES]),
                "frame_count": self._frame_count,
            }

            # Trigger alert nếu ùn tắc
            if worst_los in (LOS_CONGESTED, LOS_JAMMED):
                for cb in self._alert_callbacks:
                    try:
                        cb(worst_los, zone_results, overall)
                    except Exception:
                        pass

            return {
                "overall": overall,
                "zones": zone_results,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

    def get_status(self) -> dict[str, Any]:
        """Trạng thái hiện tại của tất cả ROI."""
        with self._lock:
            zones_info = []
            for zone in self._zones.values():
                snap = zone._snapshot(
                    zone._current_weighted / zone.capacity
                    if zone.capacity > 0 else 0
                )
                zones_info.append(snap)

            return {
                "zones": zones_info,
                "frame_count": self._frame_count,
                "zone_count": len(self._zones),
            }

    def get_zone_history(self, zone_name: str, last_n: int = 30) -> list[dict[str, Any]]:
        with self._lock:
            zone = self._zones.get(zone_name)
            if zone is None:
                return []
            return zone.get_history(last_n)

    def reset_stats(self, zone_name: str | None = None) -> None:
        with self._lock:
            if zone_name:
                zone = self._zones.get(zone_name)
                if zone:
                    zone.reset_stats()
            else:
                for zone in self._zones.values():
                    zone.reset_stats()
            self._frame_count = 0


# ── Annotate frame với congestion overlay ────────────────────────────────────

def annotate_congestion_on_frame(
    frame_bgr: "np.ndarray",
    congestion_result: dict[str, Any],
    frame_width: int,
    frame_height: int,
    show_roi_boxes: bool = True,
) -> "np.ndarray":
    """
    Vẽ overlay ùn tắc lên frame BGR.
    - Vẽ viền màu quanh từng ROI
    - Hiển thị LoS label và occupancy %
    - Vẽ overlay màu mờ nếu ùn tắc
    """
    try:
        import cv2
        import numpy as np
    except ImportError:
        return frame_bgr

    out = frame_bgr.copy()
    overlay = out.copy()

    for zone in congestion_result.get("zones", []):
        roi = zone.get("roi", {})
        los = zone.get("los", LOS_FREE)
        color_hex = zone.get("los_color", "#4CAF50")
        occ = zone.get("occupancy_pct", 0)
        name = zone.get("name", "")
        count = zone.get("current_count", 0)

        # Chuyển hex → BGR
        color_bgr = _hex_to_bgr(color_hex)

        # Tọa độ pixel
        px1 = int(roi.get("x1", 0) * frame_width)
        py1 = int(roi.get("y1", 0) * frame_height)
        px2 = int(roi.get("x2", 1) * frame_width)
        py2 = int(roi.get("y2", 1) * frame_height)

        if show_roi_boxes:
            # Vẽ viền ROI
            thickness = 3 if los in (LOS_CONGESTED, LOS_JAMMED) else 2
            cv2.rectangle(out, (px1, py1), (px2, py2), color_bgr, thickness)

            # Overlay màu mờ nếu ùn tắc
            if los in (LOS_CONGESTED, LOS_JAMMED):
                alpha = 0.15 if los == LOS_CONGESTED else 0.25
                cv2.rectangle(overlay, (px1, py1), (px2, py2), color_bgr, -1)
                cv2.addWeighted(overlay, alpha, out, 1 - alpha, 0, out)
                overlay = out.copy()

            # Label
            label = f"{name}: {LOS_LABELS_VI.get(los, los)} ({occ:.0f}% | {count} xe)"
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 0.45
            (tw, th), _ = cv2.getTextSize(label, font, font_scale, 1)
            lx, ly = px1 + 4, py1 + th + 6
            cv2.rectangle(out, (px1, py1), (px1 + tw + 8, py1 + th + 10), (0, 0, 0), -1)
            cv2.putText(out, label, (lx, ly), font, font_scale, color_bgr, 1, cv2.LINE_AA)

    # Overall status badge (góc trên trái)
    overall = congestion_result.get("overall", {})
    if overall:
        los = overall.get("los", LOS_FREE)
        label = f"Tong the: {LOS_LABELS_VI.get(los, los)}"
        color_bgr = _hex_to_bgr(overall.get("los_color", "#4CAF50"))
        font = cv2.FONT_HERSHEY_SIMPLEX
        (tw, th), _ = cv2.getTextSize(label, font, 0.55, 2)
        cv2.rectangle(out, (8, 8), (tw + 20, th + 20), (0, 0, 0), -1)
        cv2.rectangle(out, (8, 8), (tw + 20, th + 20), color_bgr, 2)
        cv2.putText(out, label, (14, th + 14), font, 0.55, color_bgr, 2, cv2.LINE_AA)

    return out


def _hex_to_bgr(hex_color: str) -> tuple[int, int, int]:
    """Chuyển #RRGGBB → (B, G, R)."""
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return (128, 128, 128)
    r = int(h[0:2], 16)
    g = int(h[2:4], 16)
    b = int(h[4:6], 16)
    return (b, g, r)

"""
congestion_detector.py — ROI-based Congestion Detection

Hỗ trợ 2 chế độ:

1. Named ROI (chuẩn hóa [0,1]) — dùng bởi routes_extended (/api/congestion/*):
   add_roi / remove_roi / list_rois / update / get_status / get_zone_history.
   Mỗi ROI có capacity; occupancy = count / capacity → level low/moderate/high.

2. Grid analyze() — dùng bởi video pipeline (video_detect.py):
   chia frame thành lưới grid_cols×grid_rows, đếm xe theo center point.

Thread-safe.
"""

import threading
import logging
import time
from collections import defaultdict, deque
from typing import Optional

logger = logging.getLogger(__name__)


def _level_from_occupancy(occ: float) -> str:
    if occ < 0.5:
        return "low"
    if occ < 0.85:
        return "moderate"
    return "high"


_LEVEL_RANK = {"low": 0, "moderate": 1, "high": 2}


class CongestionDetector:

    def __init__(
        self,
        frame_width: Optional[int] = None,
        frame_height: Optional[int] = None,
        grid_cols: int = 3,
        grid_rows: int = 3,
        roi_capacity: int = 5,    # xe tối đa trước khi 1 ô lưới coi là ùn tắc
    ):
        self._fw = frame_width
        self._fh = frame_height
        self._cols = grid_cols
        self._rows = grid_rows
        self._capacity = roi_capacity
        self._lock = threading.Lock()

        # Named ROIs (toạ độ chuẩn hoá): name → {x1,y1,x2,y2,capacity}
        self._rois: dict[str, dict] = {}
        # Lịch sử mỗi ROI: name → deque[{count, occupancy, level, timestamp}]
        self._history: dict[str, deque] = defaultdict(lambda: deque(maxlen=300))
        # Snapshot trạng thái gần nhất
        self._last_status: dict = {}

        # Lưới pixel cho analyze() (chỉ khi biết kích thước frame)
        self._grid = self._build_grid() if frame_width and frame_height else []

    # ── Grid helpers (chế độ video) ───────────────────────────────────────────

    def _build_grid(self) -> list[tuple[int, int, int, int]]:
        rois = []
        cell_w = self._fw // self._cols
        cell_h = self._fh // self._rows
        for row in range(self._rows):
            for col in range(self._cols):
                x1 = col * cell_w
                y1 = row * cell_h
                rois.append((x1, y1, x1 + cell_w, y1 + cell_h))
        return rois

    def analyze(self, boxes: dict) -> dict:
        """Phân tích ùn tắc theo lưới. boxes: dict[track_id, (x1,y1,x2,y2)] pixel."""
        if not self._grid:
            return {"score": 0.0, "level": "low", "roi_counts": [],
                    "overloaded": [], "total_vehicles": len(boxes)}

        roi_counts = [0] * len(self._grid)
        for _tid, (bx1, by1, bx2, by2) in boxes.items():
            cx = (bx1 + bx2) // 2
            cy = (by1 + by2) // 2
            for i, (rx1, ry1, rx2, ry2) in enumerate(self._grid):
                if rx1 <= cx <= rx2 and ry1 <= cy <= ry2:
                    roi_counts[i] += 1
                    break

        overloaded = [i for i, c in enumerate(roi_counts) if c >= self._capacity]
        score = len(overloaded) / max(len(self._grid), 1)
        if score < 0.2:
            level = "low"
        elif score < 0.5:
            level = "moderate"
        else:
            level = "high"
        return {
            "score": round(score, 2),
            "level": level,
            "roi_counts": roi_counts,
            "overloaded": overloaded,
            "total_vehicles": sum(roi_counts),
        }

    def get_roi_rects(self) -> list[tuple]:
        """Danh sách rectangles lưới (pixel) để vẽ — backward compat."""
        return self._grid

    # ── Named ROI API (chế độ /api/congestion/*) ──────────────────────────────

    def add_roi(self, name: str, x1: float, y1: float, x2: float, y2: float,
                capacity: int = 10) -> None:
        """Thêm/ghi đè một ROI chuẩn hoá [0,1]."""
        with self._lock:
            self._rois[name] = {
                "x1": max(0.0, min(1.0, float(x1))),
                "y1": max(0.0, min(1.0, float(y1))),
                "x2": max(0.0, min(1.0, float(x2))),
                "y2": max(0.0, min(1.0, float(y2))),
                "capacity": max(1, int(capacity)),
            }

    def remove_roi(self, name: str) -> bool:
        with self._lock:
            existed = name in self._rois
            self._rois.pop(name, None)
            self._history.pop(name, None)
            return existed

    def list_rois(self) -> list[dict]:
        with self._lock:
            return [{"name": n, **cfg} for n, cfg in self._rois.items()]

    def reset_stats(self, name: Optional[str] = None) -> None:
        with self._lock:
            if name:
                self._history.pop(name, None)
            else:
                self._history.clear()
                self._last_status = {}

    def get_zone_history(self, name: str, last_n: int = 30) -> list[dict]:
        with self._lock:
            hist = list(self._history.get(name, []))
            return hist[-last_n:]

    def get_status(self) -> dict:
        with self._lock:
            return dict(self._last_status) if self._last_status else {
                "rois": [], "overall_level": "low", "overall_score": 0.0,
                "total_vehicles": 0,
            }

    def update(self, detections: list, frame_width: int, frame_height: int) -> dict:
        """
        Phân tích ùn tắc theo các named ROI trên 1 frame/ảnh.

        detections : list[{"class", "bbox": [x1,y1,x2,y2] pixel, ...}]
        Returns dict snapshot (cũng lưu vào history + last_status).
        """
        with self._lock:
            if not self._rois:
                # Mặc định 1 ROI phủ toàn khung
                self._rois["full_frame"] = {"x1": 0.0, "y1": 0.0, "x2": 1.0,
                                            "y2": 1.0, "capacity": 15}

            centers = []
            for det in detections:
                bbox = det.get("bbox") or []
                if len(bbox) < 4:
                    continue
                cx = (float(bbox[0]) + float(bbox[2])) / 2.0 / max(frame_width, 1)
                cy = (float(bbox[1]) + float(bbox[3])) / 2.0 / max(frame_height, 1)
                centers.append((cx, cy))

            now = time.time()
            roi_results = []
            worst_rank = 0
            worst_occ = 0.0
            for name, cfg in self._rois.items():
                count = sum(
                    1 for cx, cy in centers
                    if cfg["x1"] <= cx <= cfg["x2"] and cfg["y1"] <= cy <= cfg["y2"]
                )
                occ = count / cfg["capacity"]
                level = _level_from_occupancy(occ)
                worst_rank = max(worst_rank, _LEVEL_RANK[level])
                worst_occ = max(worst_occ, occ)
                snapshot = {
                    "name": name,
                    "count": count,
                    "capacity": cfg["capacity"],
                    "occupancy": round(occ, 2),
                    "level": level,
                    "bbox_norm": [cfg["x1"], cfg["y1"], cfg["x2"], cfg["y2"]],
                }
                roi_results.append(snapshot)
                self._history[name].append({
                    "count": count, "occupancy": round(occ, 2),
                    "level": level, "timestamp": now,
                })

            overall_level = {0: "low", 1: "moderate", 2: "high"}[worst_rank]
            result = {
                "rois": roi_results,
                "overall_level": overall_level,
                "overall_score": round(worst_occ, 2),
                "total_vehicles": len(centers),
            }
            self._last_status = result
            return result


def annotate_congestion_on_frame(frame, result: dict, frame_width: int,
                                 frame_height: int):
    """Vẽ các ROI và mức ùn tắc lên frame BGR (OpenCV)."""
    import cv2

    color_map = {
        "low":      (0, 200, 0),     # xanh
        "moderate": (0, 200, 255),   # vàng
        "high":     (0, 0, 255),     # đỏ
    }
    for roi in result.get("rois", []):
        bx = roi.get("bbox_norm", [0, 0, 1, 1])
        x1 = int(bx[0] * frame_width)
        y1 = int(bx[1] * frame_height)
        x2 = int(bx[2] * frame_width)
        y2 = int(bx[3] * frame_height)
        color = color_map.get(roi.get("level", "low"), (200, 200, 200))
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        label = f"{roi['name']}: {roi['count']}/{roi['capacity']} ({roi['level']})"
        cv2.putText(frame, label, (x1 + 4, max(y1 + 18, 18)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

    overall = result.get("overall_level", "low")
    cv2.putText(frame, f"Congestion: {overall.upper()}", (10, frame_height - 12),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                color_map.get(overall, (255, 255, 255)), 2)
    return frame

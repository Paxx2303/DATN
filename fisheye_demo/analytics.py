"""
analytics.py — Traffic Heatmap & Density Analytics

THIẾT KẾ:
- Grid 64×64 cells tích lũy số lần có xe đi qua.
- _grid[row][col] += 1 mỗi khi center point của một detection rơi vào cell đó.
- get_heatmap_image() render ra ảnh PNG màu (blue→red) để overlay lên UI.
- TrafficDensityAnalyzer: theo dõi lịch sử density theo thời gian.
"""

import numpy as np
import threading
import time
import logging
from typing import Optional
from PIL import Image

logger = logging.getLogger(__name__)

GRID_SIZE = 64   # 64×64 cells


class HeatmapAccumulator:
    """
    Tích lũy vị trí xe trên một lưới 64×64.
    Thread-safe với threading.Lock.
    """
    
    def __init__(self, grid_size: int = GRID_SIZE):
        self._grid_size = grid_size
        self._grid = np.zeros((grid_size, grid_size), dtype=np.float32)
        self._lock = threading.Lock()
        self._total_updates = 0
    
    def update(self, detections: list[dict], frame_width: int, frame_height: int) -> None:
        """
        Cộng dồn các detection vào grid.
        
        detections: list[{"center": [cx, cy], ...}]
        """
        with self._lock:
            for det in detections:
                cx, cy = det.get("center", (0, 0))
                # Ánh xạ tọa độ pixel → ô grid
                col = int(cx / frame_width * self._grid_size)
                row = int(cy / frame_height * self._grid_size)
                col = np.clip(col, 0, self._grid_size - 1)
                row = np.clip(row, 0, self._grid_size - 1)
                self._grid[row, col] += 1.0
            self._total_updates += 1
    
    def get_normalized_grid(self) -> np.ndarray:
        """Trả về grid chuẩn hóa về [0, 1]."""
        with self._lock:
            if self._grid.max() == 0:
                return self._grid.copy()
            return self._grid / self._grid.max()
    
    def get_heatmap_image(self, width: int = 640, height: int = 480, 
                           alpha: float = 0.6) -> Image.Image:
        """
        Render heatmap thành ảnh PIL RGBA (có transparency).
        
        Màu: lạnh (xanh dương, ít xe) → nóng (đỏ, nhiều xe)
        """
        grid_norm = self.get_normalized_grid()
        
        # Resize grid lên kích thước output bằng nearest neighbor
        grid_resized = np.kron(
            grid_norm,
            np.ones((height // self._grid_size + 1, width // self._grid_size + 1))
        )[:height, :width]
        
        # Áp dụng colormap: blue → cyan → green → yellow → red
        # Dùng custom colormap thay vì matplotlib để không cần import matplotlib
        heat_rgba = _apply_heat_colormap(grid_resized, alpha)
        return Image.fromarray(heat_rgba, "RGBA")
    
    def reset(self) -> None:
        """Reset grid về zero."""
        with self._lock:
            self._grid[:] = 0.0
            self._total_updates = 0
    
    def to_json(self) -> dict:
        """Serialize grid cho lưu vào DB."""
        import json
        return {
            "grid": self._grid.tolist(),
            "grid_size": self._grid_size,
            "total_updates": self._total_updates,
        }

    def to_base64_jpeg(self, width: int = 640, height: int = 480) -> str:
        """Render heatmap thành JPEG base64 string."""
        import base64
        import io as _io
        img = self.get_heatmap_image(width=width, height=height)
        # Chuyển RGBA → RGB (JPEG không hỗ trợ alpha)
        rgb = Image.new("RGB", img.size, (0, 0, 0))
        rgb.paste(img, mask=img.split()[3])
        buf = _io.BytesIO()
        rgb.save(buf, format="JPEG", quality=85)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()

    def get_stats(self) -> dict:
        """Trả về thống kê tóm tắt của heatmap."""
        with self._lock:
            return {
                "total_updates": self._total_updates,
                "max_value": float(self._grid.max()),
                "nonzero_cells": int(np.count_nonzero(self._grid)),
            }


def _apply_heat_colormap(grid: np.ndarray, alpha: float) -> np.ndarray:
    """
    Chuyển đổi grid [0,1] → RGBA với colormap heat.
    
    Colormap dải màu: 0→blue(cold), 0.5→yellow(warm), 1→red(hot)
    """
    h, w = grid.shape
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    
    # Kênh alpha: tỷ lệ với intensity, min alpha = 0 (vùng không có xe)
    rgba[:, :, 3] = (grid * alpha * 255).astype(np.uint8)
    
    # Red: tăng khi > 0.5
    rgba[:, :, 0] = np.clip(grid * 2 - 0.5, 0, 1) * 255
    # Green: max ở 0.5, giảm hai bên
    rgba[:, :, 1] = np.clip(1 - np.abs(grid * 2 - 1), 0, 1) * 255
    # Blue: cao khi < 0.5, giảm khi > 0.5
    rgba[:, :, 2] = np.clip(1 - grid * 2, 0, 1) * 255
    
    return rgba


class TrafficDensityAnalyzer:
    """
    Theo dõi lịch sử density qua thời gian.
    Cung cấp: current_count, peak_count, trend (increasing/decreasing/stable).
    """
    
    def __init__(self, window_seconds: float = 60.0):
        self._window = window_seconds
        self._history: list[tuple[float, int]] = []   # (timestamp, count)
        self._lock = threading.Lock()
    
    def record(self, count: int) -> None:
        """Ghi nhận số xe tại thời điểm hiện tại."""
        now = time.time()
        with self._lock:
            self._history.append((now, count))
            # Dọn dẹp lịch sử cũ
            cutoff = now - self._window
            self._history = [(t, c) for t, c in self._history if t >= cutoff]
    
    def get_stats(self) -> dict:
        """Trả về thống kê mật độ giao thông."""
        with self._lock:
            if not self._history:
                return {"current": 0, "peak": 0, "avg": 0, "trend": "stable"}
            
            counts = [c for _, c in self._history]
            current = counts[-1]
            peak    = max(counts)
            avg     = sum(counts) / len(counts)
            
            # Trend: so sánh nửa đầu và nửa sau window
            mid = len(counts) // 2
            if mid > 0:
                first_half_avg = sum(counts[:mid]) / mid
                second_half_avg = sum(counts[mid:]) / max(len(counts[mid:]), 1)
                if second_half_avg > first_half_avg * 1.1:
                    trend = "increasing"
                elif second_half_avg < first_half_avg * 0.9:
                    trend = "decreasing"
                else:
                    trend = "stable"
            else:
                trend = "stable"
            
            return {
                "current": current,
                "peak":    peak,
                "avg":     round(avg, 1),
                "trend":   trend,
            }

    def get_summary(self) -> dict:
        """Alias cho get_stats() — tương thích với routes_extended.py."""
        return self.get_stats()


# Singleton instances
heatmap = HeatmapAccumulator()
density_analyzer = TrafficDensityAnalyzer()


# ── Module-level helper functions ────────────────────────────────────────────

def build_analytics_from_db(hours: int = 24) -> dict:
    """
    Tổng hợp analytics từ DB cho khoảng thời gian `hours` gần nhất.
    """
    try:
        import db as database
        chart = database.get_hourly_traffic_chart(hours=hours)
        class_dist = database.get_class_distribution(hours=hours)
        recent_alerts = database.get_recent_alerts(limit=20)
    except Exception as exc:
        logger.warning("build_analytics_from_db: DB error: %s", exc)
        chart = []
        class_dist = {}
        recent_alerts = []

    total = sum(class_dist.values())
    return {
        "hours":            hours,
        "total_detections": total,
        "class_distribution": class_dist,
        "hourly_chart":     chart,
        "recent_alerts":    recent_alerts,
    }


def compute_class_percentages(dist: dict) -> dict:
    """Tính % của mỗi class trong tổng."""
    total = sum(dist.values())
    if total == 0:
        return {k: 0.0 for k in dist}
    return {k: round(v / total * 100, 1) for k, v in dist.items()}


def detect_peak_hours(chart: list, top_n: int = 3) -> list:
    """
    Tìm top_n giờ cao điểm từ hourly chart.

    Parameters
    ----------
    chart : list[{"hour": str, "counts": {class: N}}]
    top_n : số giờ trả về
    """
    if not chart:
        return []
    scored = []
    for bucket in chart:
        total = sum(bucket.get("counts", {}).values())
        scored.append({"hour": bucket.get("hour", ""), "total": total})
    scored.sort(key=lambda x: x["total"], reverse=True)
    return scored[:top_n]

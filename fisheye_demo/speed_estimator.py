"""
speed_estimator.py — Vehicle Speed Estimation

PHƯƠNG PHÁP:
- Theo dõi lịch sử vị trí center point của mỗi track_id.
- Tính displacement (pixel) giữa các frame.
- Nhân với scale_factor (px → mét) và fps để ra m/s → km/h.

GIỚI HẠN:
- Không có calibration thực tế → kết quả là ước lượng tương đối.
- scale_factor phải được calibrate dựa trên kích thước thực của cảnh quay.
"""

import numpy as np
import time
import logging
from collections import deque
from typing import Optional

logger = logging.getLogger(__name__)

# Số frame giữ trong lịch sử để smooth speed
HISTORY_FRAMES = 10


class SpeedEstimator:
    """
    Theo dõi và ước lượng tốc độ cho nhiều vehicles cùng lúc.
    """
    
    def __init__(self, fps: float = 25.0, scale_factor: float = 0.05):
        """
        Parameters
        ----------
        fps          : FPS của video nguồn
        scale_factor : Tỷ lệ pixel/mét ước lượng.
                       0.05 = 1 pixel ≈ 0.05 mét (cần calibrate cho từng camera)
        """
        self._fps = max(fps, 1.0)
        self._scale = scale_factor
        # track_id → deque[(frame_idx, cx, cy)]
        self._tracks: dict[int, deque] = {}
        # track_id → smoothed speed (km/h)
        self._speeds: dict[int, float] = {}
    
    def update(self, track_id: int, cx: int, cy: int, 
               frame_idx: int, vehicle_type: str = "unknown") -> None:
        """
        Cập nhật vị trí center point của một vehicle.
        
        Parameters
        ----------
        cx, cy      : Center point của bounding box (pixels)
        frame_idx   : Frame hiện tại
        """
        if track_id not in self._tracks:
            self._tracks[track_id] = deque(maxlen=HISTORY_FRAMES)
        
        self._tracks[track_id].append((frame_idx, cx, cy))
        
        # Tính speed nếu có đủ lịch sử (>= 3 điểm)
        if len(self._tracks[track_id]) >= 3:
            self._speeds[track_id] = self._compute_speed(track_id)
    
    def _compute_speed(self, track_id: int) -> float:
        """
        Tính tốc độ trung bình từ lịch sử displacement.
        
        v = displacement_px × scale_factor / (frame_diff / fps) [m/s]
        speed_kmh = v × 3.6
        """
        history = list(self._tracks[track_id])
        
        # Tính tổng displacement và thời gian
        total_dist_px = 0.0
        total_frames = 0
        
        for i in range(1, len(history)):
            f0, x0, y0 = history[i-1]
            f1, x1, y1 = history[i]
            
            dist = np.sqrt((x1 - x0)**2 + (y1 - y0)**2)
            total_dist_px += dist
            total_frames += (f1 - f0)
        
        if total_frames == 0:
            return 0.0
        
        # Tốc độ = (px × scale) / (frames / fps) → m/s
        speed_ms = (total_dist_px * self._scale) / (total_frames / self._fps)
        speed_kmh = speed_ms * 3.6
        
        # Clamp về khoảng hợp lý: 0 – 200 km/h
        return round(np.clip(speed_kmh, 0.0, 200.0), 1)
    
    def get_speed(self, track_id: int) -> float:
        """Trả về tốc độ hiện tại (km/h) của track. 0.0 nếu chưa có."""
        return self._speeds.get(track_id, 0.0)
    
    def get_average_speed(self) -> float:
        """Tốc độ trung bình của tất cả vehicles đang track."""
        active_speeds = [s for s in self._speeds.values() if s > 0]
        if not active_speeds:
            return 0.0
        return round(sum(active_speeds) / len(active_speeds), 1)
    
    def get_all_speeds(self) -> dict[int, float]:
        """Trả về dict {track_id: speed_kmh} cho tất cả."""
        return dict(self._speeds)
    
    def remove_track(self, track_id: int) -> None:
        """Xóa track khi xe rời khỏi frame."""
        self._tracks.pop(track_id, None)
        self._speeds.pop(track_id, None)

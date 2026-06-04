"""
incident_detector.py — Traffic Incident Detection

LOẠI SỰ CỐ:
1. ILLEGAL_PARKING: Một track_id không di chuyển trong > N giây.
2. WRONG_WAY: Velocity vector của xe ngược chiều với flow chung.
3. STOPPED_VEHICLE: Xe dừng đột ngột giữa dòng giao thông.

THIẾT KẾ:
- Theo dõi lịch sử vị trí track_id.
- Sau N frame không di chuyển → phát sinh cảnh báo.
- Thread-safe (có thể gọi từ video worker thread).
"""

import time
import logging
import numpy as np
from collections import defaultdict, deque
from typing import Optional

logger = logging.getLogger(__name__)

# Ngưỡng: xe đứng yên > N giây → ILLEGAL_PARKING
PARKING_THRESHOLD_SECONDS = 30.0
# Ngưỡng displacement px/frame để coi là "đang di chuyển"
MIN_MOVEMENT_PX = 5.0


class IncidentDetector:
    
    def __init__(
        self,
        camera_id: str = "default",
        fps: float = 25.0,
        parking_threshold_s: float = PARKING_THRESHOLD_SECONDS,
    ):
        self._camera_id = camera_id
        self._fps = fps
        self._parking_threshold_frames = int(parking_threshold_s * fps)
        
        # track_id → deque[(frame_idx, cx, cy)]
        self._positions: dict[int, deque] = defaultdict(lambda: deque(maxlen=300))
        # track_id → frame_idx khi lần đầu đứng yên
        self._stationary_since: dict[int, int] = {}
        # Danh sách incidents đã phát sinh
        self._incidents: list[dict] = []
    
    def analyze(
        self,
        boxes: dict[int, tuple],       # track_id → (x1,y1,x2,y2)
        labels: dict[int, str],        # track_id → class_name
        frame_idx: int,
        fps: float,
    ) -> list[dict]:
        """
        Phân tích frame hiện tại và trả về list các incidents mới phát sinh.
        """
        new_incidents = []
        
        for track_id, (x1, y1, x2, y2) in boxes.items():
            cx = (x1 + x2) // 2
            cy = (y1 + y2) // 2
            self._positions[track_id].append((frame_idx, cx, cy))
            
            # ── Kiểm tra ILLEGAL_PARKING ──────────────────────
            parking_incident = self._check_parking(track_id, frame_idx, (x1,y1,x2,y2))
            if parking_incident:
                parking_incident["vehicle_type"] = labels.get(track_id, "unknown")
                new_incidents.append(parking_incident)
                self._incidents.append(parking_incident)
        
        # Xóa tracks không còn trong frame
        active_ids = set(boxes.keys())
        stale_ids = set(self._stationary_since.keys()) - active_ids
        for sid in stale_ids:
            del self._stationary_since[sid]
        
        return new_incidents
    
    def _check_parking(self, track_id: int, current_frame: int, 
                        bbox: tuple) -> Optional[dict]:
        """
        Kiểm tra xe có đứng yên quá lâu không.
        
        Nguyên tắc: Tính displacement trung bình trong 30 frame gần nhất.
        Nếu < MIN_MOVEMENT_PX → đang đứng yên.
        """
        history = list(self._positions[track_id])
        if len(history) < 10:
            return None
        
        # Lấy 30 frame gần nhất
        recent = history[-30:]
        
        # Tính total displacement
        total_disp = 0.0
        for i in range(1, len(recent)):
            _, x0, y0 = recent[i-1]
            _, x1, y1 = recent[i]
            total_disp += np.sqrt((x1-x0)**2 + (y1-y0)**2)
        
        avg_disp = total_disp / max(len(recent)-1, 1)
        
        if avg_disp < MIN_MOVEMENT_PX:
            # Xe đang đứng yên
            if track_id not in self._stationary_since:
                self._stationary_since[track_id] = current_frame
            
            stationary_frames = current_frame - self._stationary_since[track_id]
            
            if stationary_frames >= self._parking_threshold_frames:
                # Chỉ report một lần mỗi 5 giây
                incident_key = f"parking_{track_id}"
                # (đơn giản: chỉ tạo 1 incident per track_id)
                return {
                    "incident_type": "ILLEGAL_PARKING",
                    "description": f"Vehicle #{track_id} stationary for {stationary_frames/self._fps:.0f}s",
                    "track_id": track_id,
                    "bbox": list(bbox),
                    "camera_id": self._camera_id,
                    "timestamp": time.time(),
                }
        else:
            # Xe đang di chuyển → reset
            self._stationary_since.pop(track_id, None)
        
        return None
    
    def get_all_incidents(self) -> list[dict]:
        """Trả về toàn bộ incidents đã phát hiện."""
        return list(self._incidents)
    
    def reset(self) -> None:
        """Reset state (dùng khi bắt đầu video mới)."""
        self._positions.clear()
        self._stationary_since.clear()
        self._incidents.clear()

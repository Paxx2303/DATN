"""
congestion_detector.py — ROI-based Congestion Detection

PHƯƠNG PHÁP:
- Chia frame thành một lưới ROI (mặc định 3×3 = 9 vùng).
- Mỗi ROI có ngưỡng capacity (mặc định: 5 xe/vùng).
- congestion_score = số ROI bị quá tải / tổng ROI.
- Level: "low" (<0.2), "moderate" (0.2-0.5), "high" (>0.5).
"""

import numpy as np
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class CongestionDetector:
    
    def __init__(
        self,
        frame_width: int,
        frame_height: int,
        grid_cols: int = 3,
        grid_rows: int = 3,
        roi_capacity: int = 5,    # xe tối đa trước khi ROI coi là ùn tắc
    ):
        self._fw = frame_width
        self._fh = frame_height
        self._cols = grid_cols
        self._rows = grid_rows
        self._capacity = roi_capacity
        
        # Tạo danh sách ROI rectangles
        self._rois = self._build_rois()
    
    def _build_rois(self) -> list[tuple[int, int, int, int]]:
        """Tạo danh sách (x1,y1,x2,y2) cho từng ROI trong lưới."""
        rois = []
        cell_w = self._fw // self._cols
        cell_h = self._fh // self._rows
        for row in range(self._rows):
            for col in range(self._cols):
                x1 = col * cell_w
                y1 = row * cell_h
                x2 = x1 + cell_w
                y2 = y1 + cell_h
                rois.append((x1, y1, x2, y2))
        return rois
    
    def analyze(self, boxes: dict[int, tuple]) -> dict:
        """
        Phân tích mức độ ùn tắc dựa trên vị trí xe.
        
        Parameters
        ----------
        boxes : dict[track_id, (x1,y1,x2,y2)]
        
        Returns
        -------
        dict:
            score      : float [0.0 – 1.0]
            level      : "low" | "moderate" | "high"
            roi_counts : list[int] — số xe trong từng ROI
            overloaded : list[int] — chỉ số của các ROI quá tải
        """
        roi_counts = [0] * len(self._rois)
        
        for track_id, (bx1, by1, bx2, by2) in boxes.items():
            # Center point của bounding box
            cx = (bx1 + bx2) // 2
            cy = (by1 + by2) // 2
            
            # Tìm ROI chứa center point
            for i, (rx1, ry1, rx2, ry2) in enumerate(self._rois):
                if rx1 <= cx <= rx2 and ry1 <= cy <= ry2:
                    roi_counts[i] += 1
                    break
        
        overloaded = [i for i, cnt in enumerate(roi_counts) if cnt >= self._capacity]
        score = len(overloaded) / max(len(self._rois), 1)
        
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
        """Trả về danh sách rectangles của các ROI để vẽ lên frame."""
        return self._rois

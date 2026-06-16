"""
line_counter.py — Virtual Line Counter for Multi-Direction Traffic Counting

THIẾT KẾ:
- 4 vạch đếm ảo (north, south, east, west) với tọa độ chuẩn hóa [0, 1].
- Phát hiện crossing bằng phương pháp side-of-line (dấu cross product đổi chiều).
- Mỗi track_id chỉ đếm 1 lần per direction (tránh đếm trùng).
- Thread-safe.

TỌA ĐỘ: Chuẩn hóa [0.0, 1.0] so với kích thước frame thực.
  Khi gọi update(), truyền tọa độ pixel thực (cx, cy).
  Khi set_lines(), truyền tọa độ chuẩn hóa.
"""

import threading
import logging
import time
from collections import defaultdict
from typing import Optional

logger = logging.getLogger(__name__)

# Default lines (normalized coords) — chia 4 hướng từ tâm frame
_DEFAULT_LINES = {
    "north": {"start": [0.1, 0.3], "end": [0.9, 0.3]},
    "south": {"start": [0.1, 0.7], "end": [0.9, 0.7]},
    "west":  {"start": [0.3, 0.1], "end": [0.3, 0.9]},
    "east":  {"start": [0.7, 0.1], "end": [0.7, 0.9]},
}

_VALID_DIRECTIONS = {"north", "south", "east", "west"}


def _side_of_line(px: float, py: float,
                  x1: float, y1: float,
                  x2: float, y2: float) -> float:
    """
    Cross product để xác định điểm (px,py) đứng ở phía nào của đoạn thẳng (x1,y1)→(x2,y2).
    > 0: trái / trên;  < 0: phải / dưới;  0: trên đường.
    """
    return (x2 - x1) * (py - y1) - (y2 - y1) * (px - x1)


def _segments_intersect(
    ax1, ay1, ax2, ay2,   # đoạn A
    bx1, by1, bx2, by2    # đoạn B (vạch đếm)
) -> bool:
    """Kiểm tra đoạn thẳng A (quỹ đạo) cắt đoạn B (vạch đếm)."""
    d1 = _side_of_line(ax1, ay1, bx1, by1, bx2, by2)
    d2 = _side_of_line(ax2, ay2, bx1, by1, bx2, by2)
    d3 = _side_of_line(bx1, by1, ax1, ay1, ax2, ay2)
    d4 = _side_of_line(bx2, by2, ax1, ay1, ax2, ay2)

    if d1 * d2 < 0 and d3 * d4 < 0:
        return True
    return False


class LineCounter:
    """
    Đếm lưu lượng xe theo 4 hướng (north / south / east / west).
    Thread-safe.
    """

    def __init__(self, camera_id: str = "default"):
        self.camera_id = camera_id
        self._lock = threading.Lock()

        # Vạch đếm: direction → {start: [nx,ny], end: [nx,ny]}
        self._lines: dict[str, dict] = {}
        self._set_default_lines()

        # Bộ đếm: direction → class_name → count
        self._counts: dict[str, dict[str, int]] = {
            d: defaultdict(int) for d in _VALID_DIRECTIONS
        }

        # Vị trí track trước đó: track_id → (cx_norm, cy_norm)
        self._prev_pos: dict[int, tuple[float, float]] = {}

        # Set track_id đã đếm cho từng direction (tránh đếm 2 lần liên tiếp)
        self._counted: dict[int, set] = defaultdict(set)

        # Crossing events gần nhất để lưu DB
        self._recent_crossings: list[dict] = []

        logger.info("LineCounter initialized for camera: %s", camera_id)

    def _set_default_lines(self) -> None:
        self._lines = {k: dict(v) for k, v in _DEFAULT_LINES.items()}

    def set_lines(self, lines: dict) -> None:
        """
        Cấu hình lại vạch đếm.

        Parameters
        ----------
        lines : {direction: {start: [x,y], end: [x,y]}} — tọa độ normalized [0,1]
        """
        with self._lock:
            for direction, cfg in lines.items():
                direction = direction.lower()
                if direction not in _VALID_DIRECTIONS:
                    continue
                start = cfg.get("start", [0, 0.5])
                end = cfg.get("end", [1, 0.5])
                self._lines[direction] = {
                    "start": [float(start[0]), float(start[1])],
                    "end":   [float(end[0]),   float(end[1])],
                }
            logger.info("LineCounter lines updated: %s", list(lines.keys()))

    def update(self, track_id: int, cx: int, cy: int,
               class_name: str, frame_idx: int,
               frame_width: int = 640, frame_height: int = 480) -> Optional[dict]:
        """
        Cập nhật vị trí và phát hiện crossing.

        Parameters
        ----------
        track_id     : ID duy nhất của object (từ YOLO tracking)
        cx, cy       : Center point trong tọa độ pixel
        class_name   : Tên class ("Car", "Motorbike", ...)
        frame_idx    : Index frame hiện tại
        frame_width, frame_height : Kích thước frame (pixels)

        Returns
        -------
        dict nếu có crossing mới, None nếu không.
        """
        # Chuẩn hóa tọa độ
        nx = cx / max(frame_width, 1)
        ny = cy / max(frame_height, 1)

        with self._lock:
            prev = self._prev_pos.get(track_id)
            self._prev_pos[track_id] = (nx, ny)

            if prev is None:
                return None

            px, py = prev
            crossing = None

            for direction, line_cfg in self._lines.items():
                if direction in self._counted[track_id]:
                    # Đã đếm direction này rồi — reset khi track di chuyển đủ xa
                    # (cho phép xe đi qua 2 lần nếu rời vạch)
                    lx1, ly1 = line_cfg["start"]
                    lx2, ly2 = line_cfg["end"]
                    # Nếu xe không còn gần vạch nữa → xóa lock
                    dist = abs(_side_of_line(nx, ny, lx1, ly1, lx2, ly2))
                    if dist > 0.05:
                        self._counted[track_id].discard(direction)
                    continue

                lx1, ly1 = line_cfg["start"]
                lx2, ly2 = line_cfg["end"]

                if _segments_intersect(px, py, nx, ny, lx1, ly1, lx2, ly2):
                    # Crossing detected!
                    self._counts[direction][class_name] += 1
                    self._counts[direction]["total"] = sum(
                        v for k, v in self._counts[direction].items() if k != "total"
                    )
                    self._counted[track_id].add(direction)

                    event = {
                        "direction":  direction,
                        "track_id":   track_id,
                        "class_name": class_name,
                        "frame_idx":  frame_idx,
                        "timestamp":  time.time(),
                        "camera_id":  self.camera_id,
                    }
                    self._recent_crossings.append(event)
                    # Giữ tối đa 200 events gần nhất
                    if len(self._recent_crossings) > 200:
                        self._recent_crossings = self._recent_crossings[-200:]

                    crossing = event
                    logger.debug("Crossing: track=%d %s → %s", track_id, class_name, direction)
                    break  # Mỗi frame chỉ xử lý 1 crossing per track

            return crossing

    def get_stats(self) -> dict:
        """
        Trả về thống kê đếm lưu lượng.

        Returns
        -------
        {
          "directions": {direction: {class_name: count, "total": N}},
          "grand_total": N,
          "lines": {direction: {start, end}},
          "camera_id": str
        }
        """
        with self._lock:
            dirs = {}
            grand_total = 0
            for direction in _VALID_DIRECTIONS:
                counts = dict(self._counts[direction])
                total = counts.get("total", sum(v for k, v in counts.items() if k != "total"))
                counts["total"] = total
                grand_total += total
                dirs[direction] = counts

            return {
                "directions":  dirs,
                "grand_total": grand_total,
                "lines":       {k: dict(v) for k, v in self._lines.items()},
                "camera_id":   self.camera_id,
            }

    def pop_recent_crossings(self) -> list[dict]:
        """Lấy và xóa danh sách crossings gần nhất (để lưu DB)."""
        with self._lock:
            events = list(self._recent_crossings)
            self._recent_crossings.clear()
            return events

    def reset(self) -> None:
        """Reset tất cả bộ đếm và lịch sử."""
        with self._lock:
            for direction in _VALID_DIRECTIONS:
                self._counts[direction] = defaultdict(int)
            self._prev_pos.clear()
            self._counted.clear()
            self._recent_crossings.clear()
            logger.info("LineCounter reset for camera: %s", self.camera_id)

    def get_line_coords_pixel(self, frame_width: int, frame_height: int) -> dict:
        """Trả về tọa độ vạch đếm trong pixel để vẽ lên frame."""
        with self._lock:
            result = {}
            for direction, cfg in self._lines.items():
                sx, sy = cfg["start"]
                ex, ey = cfg["end"]
                result[direction] = {
                    "start": (int(sx * frame_width), int(sy * frame_height)),
                    "end":   (int(ex * frame_width), int(ey * frame_height)),
                }
            return result


# Singleton instance
line_counter = LineCounter(camera_id="default")

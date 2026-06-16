"""
incident_detector.py — Traffic Incident Detection

LOẠI SỰ CỐ:
1. ILLEGAL_PARKING : Xe đứng yên > 30s
2. STOPPED_VEHICLE : Xe dừng đột ngột giữa làn (> 10s, có xe khác vượt qua)
3. WRONG_WAY       : Xe đi ngược chiều luồng giao thông chính

THIẾT KẾ:
- Theo dõi lịch sử vị trí track_id (deque maxlen=120).
- Thread-safe (gọi từ background camera thread).
- Dedup: mỗi (track_id, incident_type) chỉ báo 1 lần mỗi 30s.
"""

import time
import threading
import logging
import numpy as np
from collections import defaultdict, deque
from typing import Optional

logger = logging.getLogger(__name__)

# Ngưỡng cấu hình
PARKING_THRESHOLD_SECONDS  = 30.0   # ILLEGAL_PARKING
STOPPED_THRESHOLD_SECONDS  = 10.0   # STOPPED_VEHICLE
MIN_MOVEMENT_PX            = 5.0    # px/frame để coi là "di chuyển"
WRONG_WAY_ANGLE_THRESHOLD  = 120.0  # độ — góc lệch > 120° → ngược chiều
WRONG_WAY_MIN_SPEED_PX     = 3.0    # px/frame tối thiểu để kiểm tra hướng
DEDUP_COOLDOWN_SECONDS     = 30.0   # Không báo lại incident cùng track trong N giây

_SEVERITY = {
    "ILLEGAL_PARKING":  "medium",
    "STOPPED_VEHICLE":  "high",
    "WRONG_WAY":        "critical",
}


class IncidentDetector:

    def __init__(
        self,
        camera_id: str = "default",
        fps: float = 25.0,
        parking_threshold_s: float = PARKING_THRESHOLD_SECONDS,
        stopped_threshold_s: float = STOPPED_THRESHOLD_SECONDS,
    ):
        self._camera_id = camera_id
        self._fps = max(fps, 1.0)
        self._parking_frames = int(parking_threshold_s * fps)
        self._stopped_frames = int(stopped_threshold_s * fps)
        self._lock = threading.Lock()

        # track_id → deque[(frame_idx, cx, cy, timestamp)]
        self._positions: dict[int, deque] = defaultdict(
            lambda: deque(maxlen=120)
        )
        # track_id → frame_idx khi bắt đầu đứng yên
        self._stationary_since: dict[int, int] = {}

        # Tất cả incidents đã phát sinh (in-memory)
        self._incidents: list[dict] = []

        # Dedup: (track_id, incident_type) → last_reported_time
        self._last_reported: dict[tuple, float] = {}

        # Hướng dòng chảy chính (tự học từ dữ liệu)
        # _flow_vectors: list of (vx, vy) từ các track đang di chuyển
        self._flow_vectors: deque = deque(maxlen=200)

        logger.info("IncidentDetector initialized for camera: %s", camera_id)

    # ── Public API ────────────────────────────────────────────────────────────

    def analyze(
        self,
        boxes: dict,      # track_id → (x1,y1,x2,y2)
        labels: dict,     # track_id → class_name
        frame_idx: int,
        fps: float = 25.0,
    ) -> list[dict]:
        """
        Phân tích frame hiện tại, trả về list incidents mới phát sinh.
        Gọi mỗi frame từ video pipeline hoặc camera monitor.
        """
        self._fps = max(fps, 1.0)
        new_incidents = []
        now = time.time()

        with self._lock:
            active_ids = set(boxes.keys())

            for track_id, bbox in boxes.items():
                x1, y1, x2, y2 = bbox
                cx = int((x1 + x2) / 2)
                cy = int((y1 + y2) / 2)
                vehicle_type = labels.get(track_id, "unknown")

                self._positions[track_id].append((frame_idx, cx, cy, now))

                # Tính velocity vector để cập nhật flow direction
                vel = self._get_velocity(track_id)
                if vel is not None:
                    vx, vy = vel
                    speed = np.sqrt(vx**2 + vy**2)
                    if speed > WRONG_WAY_MIN_SPEED_PX:
                        self._flow_vectors.append((vx, vy))

                # ── ILLEGAL_PARKING ───────────────────────────────────────
                inc = self._check_parking(track_id, frame_idx, bbox, vehicle_type)
                if inc:
                    new_incidents.append(inc)
                    self._incidents.append(inc)

                # ── STOPPED_VEHICLE ───────────────────────────────────────
                inc = self._check_stopped(track_id, frame_idx, bbox, vehicle_type, active_ids, boxes)
                if inc:
                    new_incidents.append(inc)
                    self._incidents.append(inc)

                # ── WRONG_WAY ─────────────────────────────────────────────
                inc = self._check_wrong_way(track_id, frame_idx, bbox, vehicle_type)
                if inc:
                    new_incidents.append(inc)
                    self._incidents.append(inc)

            # Dọn dẹp tracks đã biến mất
            stale_ids = set(self._stationary_since.keys()) - active_ids
            for sid in stale_ids:
                self._stationary_since.pop(sid, None)

        return new_incidents

    def get_all_incidents(self) -> list[dict]:
        with self._lock:
            return list(self._incidents)

    def reset(self) -> None:
        with self._lock:
            self._positions.clear()
            self._stationary_since.clear()
            self._incidents.clear()
            self._last_reported.clear()
            self._flow_vectors.clear()
            logger.info("IncidentDetector reset for camera: %s", self._camera_id)

    # ── Dedup helper ──────────────────────────────────────────────────────────

    def _can_report(self, track_id: int, incident_type: str) -> bool:
        """Kiểm tra cooldown — True nếu được phép báo incident mới."""
        key = (track_id, incident_type)
        last = self._last_reported.get(key, 0.0)
        now = time.time()
        if now - last >= DEDUP_COOLDOWN_SECONDS:
            self._last_reported[key] = now
            return True
        return False

    # ── Velocity helper ───────────────────────────────────────────────────────

    def _get_velocity(self, track_id: int, n_frames: int = 5) -> Optional[tuple]:
        """
        Tính velocity vector trung bình từ N frame gần nhất.
        Returns (vx, vy) px/frame, hoặc None nếu không đủ data.
        """
        history = list(self._positions[track_id])
        if len(history) < 2:
            return None
        recent = history[-min(n_frames + 1, len(history)):]
        vxs, vys = [], []
        for i in range(1, len(recent)):
            f0, x0, y0, _ = recent[i - 1]
            f1, x1, y1, _ = recent[i]
            df = max(f1 - f0, 1)
            vxs.append((x1 - x0) / df)
            vys.append((y1 - y0) / df)
        if not vxs:
            return None
        return float(np.mean(vxs)), float(np.mean(vys))

    def _get_main_flow_direction(self) -> Optional[tuple]:
        """
        Ước tính hướng dòng chảy chính bằng median của các velocity vector.
        Returns (vx, vy) hoặc None nếu chưa đủ dữ liệu.
        """
        if len(self._flow_vectors) < 10:
            return None
        vecs = list(self._flow_vectors)
        vx = float(np.median([v[0] for v in vecs]))
        vy = float(np.median([v[1] for v in vecs]))
        return vx, vy

    # ── Incident checkers ─────────────────────────────────────────────────────

    def _check_parking(self, track_id: int, current_frame: int,
                       bbox: tuple, vehicle_type: str) -> Optional[dict]:
        """ILLEGAL_PARKING: xe đứng yên > PARKING_THRESHOLD_SECONDS."""
        history = list(self._positions[track_id])
        if len(history) < 10:
            return None

        recent = history[-30:]
        disps = []
        for i in range(1, len(recent)):
            _, x0, y0, _ = recent[i - 1]
            _, x1, y1, _ = recent[i]
            disps.append(np.sqrt((x1 - x0) ** 2 + (y1 - y0) ** 2))

        avg_disp = float(np.mean(disps)) if disps else 0.0

        if avg_disp < MIN_MOVEMENT_PX:
            if track_id not in self._stationary_since:
                self._stationary_since[track_id] = current_frame
            stationary_frames = current_frame - self._stationary_since[track_id]
            if stationary_frames >= self._parking_frames:
                if not self._can_report(track_id, "ILLEGAL_PARKING"):
                    return None
                duration = stationary_frames / self._fps
                return self._make_incident(
                    "ILLEGAL_PARKING",
                    f"Vehicle #{track_id} ({vehicle_type}) stationary for {duration:.0f}s",
                    track_id, vehicle_type, bbox,
                )
        else:
            self._stationary_since.pop(track_id, None)
        return None

    def _check_stopped(self, track_id: int, current_frame: int,
                       bbox: tuple, vehicle_type: str,
                       active_ids: set, all_boxes: dict) -> Optional[dict]:
        """
        STOPPED_VEHICLE: xe dừng đột ngột giữa làn (ngắn hơn parking)
        khi có ít nhất 1 xe khác đang di chuyển gần đó.
        """
        history = list(self._positions[track_id])
        if len(history) < 5:
            return None

        recent = history[-15:]
        disps = []
        for i in range(1, len(recent)):
            _, x0, y0, _ = recent[i - 1]
            _, x1, y1, _ = recent[i]
            disps.append(np.sqrt((x1 - x0) ** 2 + (y1 - y0) ** 2))

        avg_disp = float(np.mean(disps)) if disps else 0.0

        if avg_disp < MIN_MOVEMENT_PX:
            if track_id not in self._stationary_since:
                self._stationary_since[track_id] = current_frame
            stationary_frames = current_frame - self._stationary_since.get(track_id, current_frame)

            if stationary_frames < self._stopped_frames:
                return None

            # Kiểm tra có xe khác di chuyển gần không
            x1b, y1b, x2b, y2b = bbox
            cx_self = (x1b + x2b) / 2
            cy_self = (y1b + y2b) / 2
            nearby_moving = 0
            for other_id in active_ids:
                if other_id == track_id:
                    continue
                other_vel = self._get_velocity(other_id)
                if other_vel is None:
                    continue
                speed_other = np.sqrt(other_vel[0] ** 2 + other_vel[1] ** 2)
                if speed_other < MIN_MOVEMENT_PX:
                    continue
                ox1, oy1, ox2, oy2 = all_boxes[other_id]
                cx_other = (ox1 + ox2) / 2
                cy_other = (oy1 + oy2) / 2
                dist = np.sqrt((cx_other - cx_self) ** 2 + (cy_other - cy_self) ** 2)
                if dist < 200:  # 200px proximity
                    nearby_moving += 1

            if nearby_moving >= 1:
                if not self._can_report(track_id, "STOPPED_VEHICLE"):
                    return None
                return self._make_incident(
                    "STOPPED_VEHICLE",
                    f"Vehicle #{track_id} ({vehicle_type}) blocking lane with traffic nearby",
                    track_id, vehicle_type, bbox,
                )
        return None

    def _check_wrong_way(self, track_id: int, current_frame: int,
                         bbox: tuple, vehicle_type: str) -> Optional[dict]:
        """
        WRONG_WAY: velocity vector ngược chiều với main flow direction.
        Góc lệch > WRONG_WAY_ANGLE_THRESHOLD degrees.
        """
        vel = self._get_velocity(track_id, n_frames=8)
        if vel is None:
            return None
        vx, vy = vel
        speed = np.sqrt(vx ** 2 + vy ** 2)
        if speed < WRONG_WAY_MIN_SPEED_PX:
            return None

        flow = self._get_main_flow_direction()
        if flow is None:
            return None
        fx, fy = flow
        flow_speed = np.sqrt(fx ** 2 + fy ** 2)
        if flow_speed < WRONG_WAY_MIN_SPEED_PX:
            return None

        # Tính góc giữa velocity và flow
        cos_angle = (vx * fx + vy * fy) / (speed * flow_speed)
        cos_angle = np.clip(cos_angle, -1.0, 1.0)
        angle_deg = float(np.degrees(np.arccos(cos_angle)))

        if angle_deg > WRONG_WAY_ANGLE_THRESHOLD:
            if not self._can_report(track_id, "WRONG_WAY"):
                return None
            return self._make_incident(
                "WRONG_WAY",
                f"Vehicle #{track_id} ({vehicle_type}) going wrong way (angle: {angle_deg:.0f}°)",
                track_id, vehicle_type, bbox,
            )
        return None

    def _make_incident(self, incident_type: str, description: str,
                       track_id: int, vehicle_type: str,
                       bbox: tuple) -> dict:
        return {
            "incident_type": incident_type,
            "description":   description,
            "track_id":      track_id,
            "vehicle_type":  vehicle_type,
            "bbox":          list(bbox),
            "camera_id":     self._camera_id,
            "severity":      _SEVERITY.get(incident_type, "medium"),
            "timestamp":     time.time(),
            "acknowledged":  False,
        }

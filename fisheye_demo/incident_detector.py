"""
incident_detector.py — Hệ thống phát hiện sự cố giao thông thời gian thực.
"""
from __future__ import annotations

import os
import json
import time
import math
import logging
import threading
from collections import deque
from datetime import datetime, timezone
from typing import Any, Callable

try:
    import cv2
    import numpy as np
except ImportError:
    cv2 = None
    np = None

try:
    import db
except ImportError:
    from fisheye_demo import db

logger = logging.getLogger("fisheye_demo.incident_detector")

# Các hằng số loại sự cố
INCIDENT_COLLISION = "collision"
INCIDENT_STOPPED_VEHICLE = "stopped_vehicle"
INCIDENT_WRONG_WAY = "wrong_way"
INCIDENT_FALLEN_OBJECT = "fallen_object"
INCIDENT_PEDESTRIAN_DANGER = "pedestrian_danger"
INCIDENT_UNUSUAL_PATTERN = "unusual_pattern"

VEHICLE_CLASSES = {"Car", "Bus", "Truck", "Motorbike"}


# ── Config Parser ────────────────────────────────────────────────────────────

class Config_Parser:
    """Parser và validator cho tệp cấu hình độ nhạy."""
    @staticmethod
    def parse(config_str: str) -> dict[str, Any]:
        try:
            data = json.loads(config_str)
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSON invalid: {exc}")

        # Validate các giá trị
        for key, settings in data.items():
            if not isinstance(settings, dict):
                raise ValueError(f"Settings for '{key}' must be a dictionary")
            
            if "confidence_threshold" in settings:
                val = float(settings["confidence_threshold"])
                if not (0.0 <= val <= 1.0):
                    raise ValueError(f"confidence_threshold in {key} must be in range [0.0, 1.0]")
            
            for dur_key in ("duration_seconds", "time_seconds", "stationary_seconds"):
                if dur_key in settings:
                    val = float(settings[dur_key])
                    if val <= 0:
                        raise ValueError(f"{dur_key} in {key} must be positive")
        return data


class Config_Pretty_Printer:
    """Pretty-printer định dạng cấu hình JSON."""
    @staticmethod
    def print_config(config_obj: dict[str, Any]) -> str:
        return json.dumps(config_obj, indent=2, sort_keys=True)


# ── Component Classes ────────────────────────────────────────────────────────

class ROI_Manager:
    """Quản lý các vùng quan tâm (ROI) phục vụ phát hiện sự cố."""
    def __init__(self) -> None:
        self.rois: dict[str, dict[str, Any]] = {}

    def set_roi(
        self,
        name: str,
        x1: float, y1: float, x2: float, y2: float,
        expected_direction: float | None = None,  # Góc mong muốn (0-360 độ)
        is_parking_zone: bool = False,
        is_dangerous_zone: bool = False,         # Làn đường hoạt động
        is_crosswalk: bool = False,
    ) -> None:
        self.rois[name] = {
            "name": name,
            "x1": x1, "y1": y1, "x2": x2, "y2": y2,
            "expected_direction": expected_direction,
            "is_parking_zone": is_parking_zone,
            "is_dangerous_zone": is_dangerous_zone,
            "is_crosswalk": is_crosswalk,
        }

    def get_roi_containing(self, cx: float, cy: float) -> list[dict[str, Any]]:
        matched = []
        for r in self.rois.values():
            if r["x1"] <= cx <= r["x2"] and r["y1"] <= cy <= r["y2"]:
                matched.append(r)
        return matched


class Object_Tracker:
    """Theo dõi quỹ đạo và thông số các đối tượng qua các khung hình."""
    def __init__(self, max_age: int = 30) -> None:
        self.max_age = max_age
        self.tracks: dict[str, dict[str, Any]] = {}
        self.next_id = 0

    def update(
        self,
        detections: list[dict[str, Any]],
        frame_w: int,
        frame_h: int,
        fps: float,
        ppm: float,
    ) -> dict[str, dict[str, Any]]:
        # Chuẩn hóa detections hiện tại
        norm_dets = []
        for det in detections:
            x1, y1, x2, y2 = det.get("bbox", [0, 0, 0, 0])
            cx = ((x1 + x2) / 2) / frame_w
            cy = ((y1 + y2) / 2) / frame_h
            norm_dets.append({
                "class": det.get("class", "unknown"),
                "confidence": float(det.get("confidence", 0)),
                "bbox": [x1, y1, x2, y2],
                "cx": cx,
                "cy": cy,
                "area_px": (x2 - x1) * (y2 - y1),
            })

        # Khớp với tracks cũ dựa trên IoU / Distance
        matched_track_ids = set()
        now = time.time()

        for det in norm_dets:
            best_iou = 0.20
            best_tid = None

            for tid, track in self.tracks.items():
                if tid in matched_track_ids:
                    continue
                # Chỉ khớp cùng nhóm class hoặc tương đương
                iou = self._iou(det["bbox"], track["bbox"])
                if iou > best_iou:
                    best_iou = iou
                    best_tid = tid

            if best_tid is not None:
                track = self.tracks[best_tid]
                # Tính displacement và speed
                dx = (det["cx"] - track["cx"]) * frame_w
                dy = (det["cy"] - track["cy"]) * frame_h
                dist_px = math.hypot(dx, dy)
                speed_kmh = (dist_px / ppm) * fps * 3.6

                # Tính góc heading (hướng di chuyển)
                heading = track["heading"]
                if dist_px > 2.0:
                    heading = math.degrees(math.atan2(-dy, dx)) % 360.0

                # Tính deceleration
                prev_speed = track["speed"]
                deceleration = (prev_speed - speed_kmh) / (1.0 / fps)  # km/h per second

                track.update({
                    "cx": det["cx"],
                    "cy": det["cy"],
                    "bbox": det["bbox"],
                    "area_px": det["area_px"],
                    "speed": speed_kmh,
                    "heading": heading,
                    "deceleration": deceleration,
                    "age": 0,
                    "last_seen": now,
                })
                # Thêm vào quỹ đạo
                track["trajectory"].append((now, det["cx"], det["cy"], speed_kmh, heading))
                matched_track_ids.add(best_tid)
            else:
                # Tạo track mới
                tid = f"obj_{self.next_id}"
                self.next_id += 1
                self.tracks[tid] = {
                    "id": tid,
                    "class": det["class"],
                    "cx": det["cx"],
                    "cy": det["cy"],
                    "bbox": det["bbox"],
                    "area_px": det["area_px"],
                    "speed": 0.0,
                    "heading": 0.0,
                    "deceleration": 0.0,
                    "age": 0,
                    "first_seen": now,
                    "last_seen": now,
                    "trajectory": deque([(now, det["cx"], det["cy"], 0.0, 0.0)], maxlen=300),
                }

        # Tăng tuổi các track không được khớp và lọc bỏ các track quá tuổi
        expired = []
        for tid, track in self.tracks.items():
            if tid not in matched_track_ids:
                track["age"] += 1
                if track["age"] > self.max_age:
                    expired.append(tid)
        for tid in expired:
            del self.tracks[tid]

        return self.tracks

    @staticmethod
    def _iou(box_a: list[float], box_b: list[float]) -> float:
        xa1, ya1, xa2, ya2 = box_a
        xb1, yb1, xb2, yb2 = box_b
        ix1, iy1 = max(xa1, xb1), max(ya1, yb1)
        ix2, iy2 = min(xa2, xb2), min(ya2, yb2)
        if ix2 <= ix1 or iy2 <= iy1:
            return 0.0
        inter = (ix2 - ix1) * (iy2 - iy1)
        area_a = (xa2 - xa1) * (ya2 - ya1)
        area_b = (xb2 - xb1) * (yb2 - yb1)
        union = area_a + area_b - inter
        return inter / union if union > 0 else 0.0


class Accident_Analyzer:
    """Bộ phân tích phát hiện va chạm xe dựa trên tốc độ và khoảng cách."""
    def __init__(self) -> None:
        pass

    def analyze(
        self,
        tracks: dict[str, dict[str, Any]],
        frame_w: int,
        frame_h: int,
        ppm: float,
        config: dict[str, Any],
    ) -> list[dict[str, Any]]:
        collisions = []
        tids = list(tracks.keys())
        now = time.time()

        for i in range(len(tids)):
            for j in range(i + 1, len(tids)):
                tid1, tid2 = tids[i], tids[j]
                t1, t2 = tracks[tid1], tracks[tid2]

                if t1["class"] not in VEHICLE_CLASSES or t2["class"] not in VEHICLE_CLASSES:
                    continue

                # Khoảng cách giữa 2 xe (mét)
                dx = (t1["cx"] - t2["cx"]) * frame_w
                dy = (t1["cy"] - t2["cy"]) * frame_h
                distance_m = math.hypot(dx, dy) / ppm

                # Relaxed distance threshold for collision detection
                if distance_m <= 10.0:  # Increased from 5.0m to 10.0m
                    # Check for trajectory history
                    if len(t1["trajectory"]) >= 3 and len(t2["trajectory"]) >= 3:
                        # Get recent speeds
                        t1_recent_speeds = [p[3] for p in list(t1["trajectory"])[-5:]]
                        t2_recent_speeds = [p[3] for p in list(t2["trajectory"])[-5:]]
                        
                        # Check if vehicles were moving and then stopped/slowed significantly
                        t1_was_moving = any(s > 5.0 for s in t1_recent_speeds[:-2])  # Was moving before
                        t2_was_moving = any(s > 5.0 for s in t2_recent_speeds[:-2])  # Was moving before
                        
                        t1_now_slow = t1["speed"] < 2.0  # Now slow/stopped
                        t2_now_slow = t2["speed"] < 2.0  # Now slow/stopped
                        
                        # Collision if both were moving and now both are slow/stopped and close
                        collision_detected = False
                        
                        if distance_m <= 2.0 and t1_now_slow and t2_now_slow:
                            collision_detected = True
                        elif (t1_was_moving or t2_was_moving) and (t1_now_slow and t2_now_slow) and distance_m <= 3.0:
                            collision_detected = True
                        
                        if collision_detected:
                            # Calculate confidence based on proximity and speed change
                            proximity_factor = max(0.0, (5.0 - distance_m) / 5.0)  # Closer = higher confidence
                            
                            # Speed change factor
                            t1_speed_change = max(t1_recent_speeds) - t1["speed"] if t1_recent_speeds else 0
                            t2_speed_change = max(t2_recent_speeds) - t2["speed"] if t2_recent_speeds else 0
                            speed_change_factor = min(1.0, (t1_speed_change + t2_speed_change) / 20.0)
                            
                            conf = 0.4 + (proximity_factor * 0.3) + (speed_change_factor * 0.3)
                            conf = min(1.0, max(0.0, conf))

                            if conf >= config.get("confidence_threshold", 0.60):
                                collisions.append({
                                    "type": INCIDENT_COLLISION,
                                    "confidence": conf,
                                    "location": {"cx": (t1["cx"] + t2["cx"]) / 2.0, "cy": (t1["cy"] + t2["cy"]) / 2.0},
                                    "involved_objects": [
                                        {"track_id": tid1, "class": t1["class"]},
                                        {"track_id": tid2, "class": t2["class"]},
                                    ],
                                    "description": f"Collision detected between {t1['class']} ({tid1}) and {t2['class']} ({tid2})",
                                })
        return collisions


class Stopped_Vehicle_Detector:
    """Bộ phát hiện phương tiện dừng đỗ sai quy định."""
    def __init__(self) -> None:
        # track_id -> timestamp bắt đầu dừng
        self.stopped_starts: dict[str, float] = {}

    def analyze(
        self,
        tracks: dict[str, dict[str, Any]],
        roi_manager: ROI_Manager,
        config: dict[str, Any],
    ) -> list[dict[str, Any]]:
        incidents = []
        now = time.time()

        for tid, track in tracks.items():
            if track["class"] not in VEHICLE_CLASSES:
                continue

            # Kiểm tra xem xe có đứng im không (tốc độ < 1 km/h)
            is_stationary = track["speed"] < 1.0

            if is_stationary:
                if tid not in self.stopped_starts:
                    self.stopped_starts[tid] = now
                
                stopped_duration = now - self.stopped_starts[tid]

                # Lấy các vùng ROI chứa xe
                rois = roi_manager.get_roi_containing(track["cx"], track["cy"])
                is_in_parking = any(r.get("is_parking_zone") for r in rois)

                # Bỏ qua nếu nằm trong vùng được phép dừng đỗ
                if is_in_parking:
                    continue

                if stopped_duration >= config.get("duration_seconds", 30.0):
                    # Phân biệt xe dừng hàng chờ và xe đơn độc
                    # Xe đơn độc: không có xe nào khác xung quanh trong bán kính ngắn đang dừng
                    other_stopped_nearby = False
                    for oid, otrack in tracks.items():
                        if oid == tid or otrack["class"] not in VEHICLE_CLASSES:
                            continue
                        if otrack["speed"] < 1.0:
                            dist = math.hypot(track["cx"] - otrack["cx"], track["cy"] - otrack["cy"])
                            if dist < 0.05: # rất gần
                                other_stopped_nearby = True
                                break

                    # Xác định làn hoạt động (active lane) vs shoulder
                    is_in_dangerous = any(r.get("is_dangerous_zone") for r in rois)
                    severity = "severe" if is_in_dangerous and not other_stopped_nearby else "moderate"

                    incidents.append({
                        "type": INCIDENT_STOPPED_VEHICLE,
                        "confidence": min(1.0, 0.65 + (stopped_duration - 30.0) / 120.0),
                        "location": {"cx": track["cx"], "cy": track["cy"]},
                        "involved_objects": [{"track_id": tid, "class": track["class"]}],
                        "severity": severity,
                        "description": f"Stopped vehicle {track['class']} ({tid}) detected for {int(stopped_duration)}s",
                        "metadata": {"stopped_duration": stopped_duration, "is_queue": other_stopped_nearby},
                    })
            else:
                # Nếu di chuyển trở lại trên 10 km/h thì xóa theo dõi dừng
                if track["speed"] > 10.0 and tid in self.stopped_starts:
                    del self.stopped_starts[tid]

        # Cleanup tids đã biến mất
        self.stopped_starts = {tid: val for tid, val in self.stopped_starts.items() if tid in tracks}

        return incidents


class Wrong_Way_Detector:
    """Bộ phát hiện phương tiện đi ngược chiều đường dẫn."""
    def __init__(self) -> None:
        self.wrong_way_starts: dict[str, float] = {}

    def analyze(
        self,
        tracks: dict[str, dict[str, Any]],
        roi_manager: ROI_Manager,
        frame_w: int,
        frame_h: int,
        ppm: float,
        config: dict[str, Any],
    ) -> list[dict[str, Any]]:
        incidents = []
        now = time.time()

        for tid, track in tracks.items():
            if track["class"] not in VEHICLE_CLASSES:
                continue

            rois = roi_manager.get_roi_containing(track["cx"], track["cy"])
            # Bỏ qua khu vực đỗ xe (thường quay đầu lùi xe)
            is_parking = any(r.get("is_parking_zone") for r in rois)
            if is_parking:
                continue

            # Lấy góc luồng giao thông kỳ vọng
            expected_dir = None
            for r in rois:
                if r.get("expected_direction") is not None:
                    expected_dir = r["expected_direction"]
                    break

            if expected_dir is not None and len(track["trajectory"]) >= 3:
                # Độ lệch góc hướng di chuyển của xe so với luồng
                angle_diff = abs(track["heading"] - expected_dir) % 360
                if angle_diff > 180:
                    angle_diff = 360 - angle_diff

                # Relaxed angle deviation threshold
                is_deviating = angle_diff >= config.get("angle_deviation", 90.0)  # Changed > to >=

                # Relaxed trajectory length requirement
                traj_length_px = 0.0
                if len(track["trajectory"]) > 2:
                    p_start = track["trajectory"][0]
                    p_end = track["trajectory"][-1]
                    dx = (p_end[1] - p_start[1]) * frame_w  # Fixed order
                    dy = (p_end[2] - p_start[2]) * frame_h  # Fixed order
                    traj_length_px = math.hypot(dx, dy)

                # Relaxed requirements: lower speed and distance thresholds
                if is_deviating and track["speed"] > 1.0 and traj_length_px >= 20.0:  # Lowered requirements
                    if tid not in self.wrong_way_starts:
                        self.wrong_way_starts[tid] = now

                    duration = now - self.wrong_way_starts[tid]
                    if duration >= config.get("duration_seconds", 2.0):  # Lowered from 3.0
                        conf = min(1.0, 0.60 + (duration - 2.0) / 10.0 + (angle_diff - 90.0) / 270.0)
                        incidents.append({
                            "type": INCIDENT_WRONG_WAY,
                            "confidence": conf,
                            "location": {"cx": track["cx"], "cy": track["cy"]},
                            "involved_objects": [{"track_id": tid, "class": track["class"]}],
                            "severity": "critical",
                            "description": f"Wrong way driving detected for {track['class']} ({tid})",
                            "metadata": {"heading": track["heading"], "expected": expected_dir, "deviation": angle_diff},
                        })
                else:
                    if tid in self.wrong_way_starts:
                        del self.wrong_way_starts[tid]

        # Cleanup
        self.wrong_way_starts = {tid: val for tid, val in self.wrong_way_starts.items() if tid in tracks}

        return incidents


class Fallen_Object_Detector:
    """Bộ phát hiện chướng ngại vật rơi vỡ trên đường."""
    def __init__(self) -> None:
        self.object_starts: dict[str, float] = {}

    def analyze(
        self,
        tracks: dict[str, dict[str, Any]],
        roi_manager: ROI_Manager,
        ppm: float,
        config: dict[str, Any],
    ) -> list[dict[str, Any]]:
        incidents = []
        now = time.time()

        for tid, track in tracks.items():
            # Bỏ qua xe cộ hoặc người đi bộ
            if track["class"] in VEHICLE_CLASSES or track["class"] in {"Pedestrian", "person"}:
                continue

            # Chỉ phát hiện trong các làn đường hoạt động (dangerous zone)
            rois = roi_manager.get_roi_containing(track["cx"], track["cy"])
            is_in_roadway = any(r.get("is_dangerous_zone") for r in rois)
            if not is_in_roadway:
                continue

            # Phải là chướng ngại vật tĩnh (speed < 0.5 km/h)
            if track["speed"] < 0.5:
                if tid not in self.object_starts:
                    self.object_starts[tid] = now

                duration = now - self.object_starts[tid]
                if duration >= config.get("duration_seconds", 10.0):
                    # Tính kích thước vật thể qua calibration (m2)
                    # Giả định kích thước m2 = diện tích pixel / (ppm^2)
                    size_sq_m = track["area_px"] / (ppm ** 2) if ppm > 0 else 0.0
                    severity = "severe" if size_sq_m > config.get("size_threshold", 0.5) else "moderate"

                    # Nhận diện vụ đổ tràn hàng hóa (nhiều vật thể tĩnh xuất hiện đồng thời)
                    is_cargo_spill = False
                    nearby_static_objects = 0
                    for oid, otrack in tracks.items():
                        if oid != tid and otrack["class"] not in VEHICLE_CLASSES and otrack["class"] not in {"Pedestrian", "person"}:
                            if otrack["speed"] < 0.5:
                                dist = math.hypot(track["cx"] - otrack["cx"], track["cy"] - otrack["cy"])
                                if dist < 0.1:
                                    nearby_static_objects += 1

                    if nearby_static_objects >= 2:
                        is_cargo_spill = True
                        severity = "severe"

                    incidents.append({
                        "type": INCIDENT_FALLEN_OBJECT,
                        "confidence": min(1.0, 0.60 + (duration - 10.0) / 60.0),
                        "location": {"cx": track["cx"], "cy": track["cy"]},
                        "involved_objects": [{"track_id": tid, "class": track["class"]}],
                        "severity": severity,
                        "description": "Cargo spill detected" if is_cargo_spill else f"Fallen object detected on roadway",
                        "metadata": {"duration": duration, "size_sq_m": size_sq_m, "is_cargo_spill": is_cargo_spill},
                    })
            else:
                if tid in self.object_starts:
                    del self.object_starts[tid]

        # Cleanup
        self.object_starts = {tid: val for tid, val in self.object_starts.items() if tid in tracks}

        return incidents


class Pedestrian_Zone_Monitor:
    """Bộ giám sát người đi bộ lấn làn nguy hiểm."""
    def __init__(self) -> None:
        self.pedestrian_starts: dict[str, float] = {}

    def analyze(
        self,
        tracks: dict[str, dict[str, Any]],
        roi_manager: ROI_Manager,
        frame_w: int,
        frame_h: int,
        ppm: float,
        config: dict[str, Any],
    ) -> list[dict[str, Any]]:
        incidents = []
        now = time.time()

        for tid, track in tracks.items():
            if track["class"] not in {"Pedestrian", "person"}:
                continue

            rois = roi_manager.get_roi_containing(track["cx"], track["cy"])
            # Nằm trong làn đường hoạt động và KHÔNG nằm trong vạch sang đường
            is_active_lane = any(r.get("is_dangerous_zone") for r in rois)
            is_crosswalk = any(r.get("is_crosswalk") for r in rois)

            if is_active_lane and not is_crosswalk:
                if tid not in self.pedestrian_starts:
                    self.pedestrian_starts[tid] = now

                duration = now - self.pedestrian_starts[tid]
                if duration >= config.get("duration_seconds", 2.0):
                    # Tính khoảng cách gần nhất tới phương tiện đang chạy
                    min_dist_m = 999.0
                    closest_vehicle_speed = 0.0

                    for vid, vtrack in tracks.items():
                        if vid != tid and vtrack["class"] in VEHICLE_CLASSES:
                            dx = (track["cx"] - vtrack["cx"]) * frame_w
                            dy = (track["cy"] - vtrack["cy"]) * frame_h
                            dist_m = math.hypot(dx, dy) / ppm
                            if dist_m < min_dist_m:
                                min_dist_m = dist_m
                                closest_vehicle_speed = vtrack["speed"]

                    # Quy định độ nghiêm trọng
                    severity = "moderate"
                    if min_dist_m <= 3.0 and closest_vehicle_speed > 20.0:
                        severity = "critical"
                    elif min_dist_m <= 5.0:
                        severity = "severe"

                    # Phát hiện nhóm người
                    is_group = False
                    nearby_pedestrians = 0
                    for oid, otrack in tracks.items():
                        if oid != tid and otrack["class"] in {"Pedestrian", "person"}:
                            dist = math.hypot(track["cx"] - otrack["cx"], track["cy"] - otrack["cy"])
                            if dist < 0.05:
                                nearby_pedestrians += 1
                    if nearby_pedestrians >= 2:
                        is_group = True
                        severity = "critical" if severity == "severe" else "severe"

                    incidents.append({
                        "type": INCIDENT_PEDESTRIAN_DANGER,
                        "confidence": min(1.0, 0.70 + (duration - 2.0) / 10.0),
                        "location": {"cx": track["cx"], "cy": track["cy"]},
                        "involved_objects": [{"track_id": tid, "class": "Pedestrian"}],
                        "severity": severity,
                        "description": f"Pedestrians in dangerous zone detected near vehicles (dist={min_dist_m:.1f}m)",
                        "metadata": {"duration": duration, "min_dist_m": min_dist_m, "is_group": is_group},
                    })
            else:
                if tid in self.pedestrian_starts:
                    del self.pedestrian_starts[tid]

        # Cleanup
        self.pedestrian_starts = {tid: val for tid, val in self.pedestrian_starts.items() if tid in tracks}

        return incidents


class Traffic_Pattern_Analyzer:
    """Bộ phân tích bất thường của luồng giao thông tổng thể."""
    def __init__(self) -> None:
        self.history_speeds: deque[float] = deque(maxlen=60)
        self.history_counts: deque[int] = deque(maxlen=120)
        self.speed_reduction_start: float | None = None
        self.baseline_speed = 50.0  # mặc định
        self.baseline_count = 5

    def analyze(
        self,
        tracks: dict[str, dict[str, Any]],
        config: dict[str, Any],
    ) -> list[dict[str, Any]]:
        incidents = []
        now = time.time()

        # Tính tốc độ trung bình hiện tại
        active_vehicles = [t["speed"] for t in tracks.values() if t["class"] in VEHICLE_CLASSES]
        current_avg_speed = sum(active_vehicles) / len(active_vehicles) if active_vehicles else self.baseline_speed
        current_count = len(active_vehicles)

        self.history_speeds.append(current_avg_speed)
        self.history_counts.append(current_count)

        # 1. Phát hiện giảm tốc đột ngột (> 40% trong vòng 30s)
        if len(self.history_speeds) >= 10:
            past_speed = self.history_speeds[0]
            if past_speed > 0:
                drop_pct = (past_speed - current_avg_speed) / past_speed
                if drop_pct >= 0.40:
                    if self.speed_reduction_start is None:
                        self.speed_reduction_start = now
                    
                    duration = now - self.speed_reduction_start
                    if duration >= 3.0: # Giữ trong ít nhất 3 giây để xác nhận
                        incidents.append({
                            "type": INCIDENT_UNUSUAL_PATTERN,
                            "confidence": min(1.0, 0.70 + (duration / 30.0)),
                            "location": {"cx": 0.5, "cy": 0.5},
                            "involved_objects": [],
                            "severity": "minor",
                            "description": f"Sudden slowdown detected (speed dropped by {drop_pct*100:.1f}%)",
                            "metadata": {"speed_drop_pct": drop_pct, "avg_speed": current_avg_speed},
                        })
                else:
                    self.speed_reduction_start = None

        # 2. Phát hiện hành vi lạng lách (erratic movement: đổi hướng > 3 lần trong 5s)
        for tid, track in tracks.items():
            if track["class"] not in VEHICLE_CLASSES:
                continue
            recent_headings = [p[4] for p in track["trajectory"] if now - p[0] <= 5.0]
            if len(recent_headings) >= 6:
                direction_changes = 0
                for idx in range(1, len(recent_headings) - 1):
                    diff1 = (recent_headings[idx] - recent_headings[idx - 1]) % 360
                    diff2 = (recent_headings[idx + 1] - recent_headings[idx]) % 360
                    if (diff1 > 15 and diff2 < -15) or (diff1 < -15 and diff2 > 15):
                        direction_changes += 1

                if direction_changes >= 3:
                    incidents.append({
                        "type": INCIDENT_UNUSUAL_PATTERN,
                        "confidence": 0.80,
                        "location": {"cx": track["cx"], "cy": track["cy"]},
                        "involved_objects": [{"track_id": tid, "class": track["class"]}],
                        "severity": "minor",
                        "description": f"Erratic movement detected for {track['class']} ({tid})",
                        "metadata": {"direction_changes": direction_changes},
                    })

        # 3. Mật độ bất thường (vượt baseline 50% trong 2 phút)
        if len(self.history_counts) >= 60:
            avg_past_count = sum(list(self.history_counts)[:10]) / 10.0
            if avg_past_count > 0:
                increase_pct = (current_count - avg_past_count) / avg_past_count
                if increase_pct >= 0.50:
                    incidents.append({
                        "type": INCIDENT_UNUSUAL_PATTERN,
                        "confidence": 0.75,
                        "location": {"cx": 0.5, "cy": 0.5},
                        "involved_objects": [],
                        "severity": "minor",
                        "description": f"Unusual density increase detected (+{increase_pct*100:.1f}%)",
                        "metadata": {"density_increase_pct": increase_pct, "count": current_count},
                    })

        return incidents


class Incident_Lifecycle_Manager:
    """Hệ thống quản lý vòng đời sự cố."""
    def __init__(self, db_insert_callback: Callable[[dict[str, Any]], None]) -> None:
        self.active_incidents: dict[str, dict[str, Any]] = {}
        self.db_insert_callback = db_insert_callback
        # Để ngăn ngừa sự cố trùng lặp trong 5 phút
        # (type, grid_x, grid_y) -> timestamp phát hiện gần nhất
        self.recent_incidents_cache: dict[tuple[str, int, int], float] = {}

    def process_detected_incidents(
        self,
        detected_list: list[dict[str, Any]],
        camera_id: str,
    ) -> list[dict[str, Any]]:
        now = time.time()
        new_incidents = []

        # Cleanup cache quá 5 phút
        self.recent_incidents_cache = {
            k: t for k, t in self.recent_incidents_cache.items() if now - t < 300.0
        }

        for item in detected_list:
            itype = item["type"]
            loc = item["location"]
            grid_x = int(loc["cx"] * 10)
            grid_y = int(loc["cy"] * 10)
            cache_key = (itype, grid_x, grid_y)

            # Chặn trùng lặp sự cố tại cùng địa điểm trong 5 phút
            if cache_key in self.recent_incidents_cache:
                continue

            # Tạo bản ghi sự cố mới
            inc_id = f"inc_{int(now)}_{camera_id}_{len(self.active_incidents)}"
            incident = {
                "id": inc_id,
                "type": itype,
                "severity": item.get("severity", "minor"),
                "confidence": item["confidence"],
                "camera_id": camera_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "location": loc,
                "state": "active",
                "duration": 0.0,
                "metadata": item.get("metadata", {}),
                "involved_objects": item.get("involved_objects", []),
                "description": item.get("description", ""),
                "first_seen": now,
                "last_seen": now,
            }

            self.active_incidents[inc_id] = incident
            self.recent_incidents_cache[cache_key] = now
            new_incidents.append(incident)

            # Lưu vào DB
            try:
                self.db_insert_callback(incident)
            except Exception as exc:
                logger.error("Failed to insert incident to DB: %s", exc)

        return new_incidents

    def update_lifecycles(self, currently_detected_types: set[str]) -> list[str]:
        """Tự động chuyển sự cố sang 'resolved' nếu điều kiện phát hiện biến mất 60s."""
        now = time.time()
        resolved_ids = []

        for inc_id, incident in list(self.active_incidents.items()):
            # Nếu sự cố vẫn đang được phát hiện, cập nhật last_seen
            if incident["type"] in currently_detected_types:
                incident["last_seen"] = now
                incident["duration"] = now - incident["first_seen"]
                # Cập nhật DB
                try:
                    db.update_incident_state(inc_id, incident["state"], duration=incident["duration"])
                except Exception:
                    pass
            else:
                # Nếu không phát hiện thấy trong 60s
                inactive_duration = now - incident["last_seen"]
                incident["duration"] = now - incident["first_seen"]

                if inactive_duration >= 60.0:
                    incident["state"] = "resolved"
                    try:
                        db.update_incident_state(inc_id, "resolved", duration=incident["duration"])
                    except Exception:
                        pass
                    resolved_ids.append(inc_id)
                    del self.active_incidents[inc_id]

        return resolved_ids


class Confidence_Scorer:
    """Bộ tính toán và hiệu chỉnh độ tin cậy sự cố để tránh cảnh báo ảo."""
    def __init__(self) -> None:
        pass

    def evaluate(self, base_conf: float, persist_duration: float) -> float:
        # Tăng confidence nếu sự cố duy trì lâu dài
        bonus = min(0.2, persist_duration / 60.0)
        return min(1.0, base_conf + bonus)


class Video_Clip_Extractor:
    """Bộ trích xuất và xuất tệp video 60s xung quanh thời điểm phát hiện sự cố."""
    def __init__(self) -> None:
        pass

    def extract_clip(
        self,
        incident_id: str,
        frames_buffer: list[tuple[float, Any]],
        results_dir: str,
    ) -> str:
        # Trích xuất video 50-70s từ buffer
        # frames_buffer chứa (timestamp, frame_image_rgb)
        if not frames_buffer or cv2 is None:
            return ""

        filename = f"clip_{incident_id}.mp4"
        filepath = os.path.join(results_dir, filename)

        h, w = frames_buffer[0][1].shape[:2]
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(filepath, fourcc, 10.0, (w, h))

        for _, img in frames_buffer:
            out.write(img)
        out.release()

        return filepath


class Emergency_Service_Notifier:
    """Bộ tích hợp thông báo khẩn cấp (Emergency Services webhook)."""
    def __init__(self) -> None:
        self.endpoints: list[str] = []

    def register_endpoint(self, url: str) -> None:
        self.endpoints.append(url)

    def notify(self, incident: dict[str, Any]) -> None:
        # Gửi thông tin khẩn cấp khi severity == critical
        if incident.get("severity") != "critical":
            return

        payload = {
            "incident_id": incident["id"],
            "type": incident["type"],
            "severity": incident["severity"],
            "camera_id": incident["camera_id"],
            "timestamp": incident["timestamp"],
            "location": incident["location"],
            "description": incident["description"],
        }

        # Mock webhook gửi (chạy retry tối đa 3 lần)
        def _send():
            for ep in self.endpoints:
                for attempt in range(1, 4):
                    try:
                        logger.info("Sending critical notification to emergency service (attempt %s)", attempt)
                        # requests.post(ep, json=payload, timeout=5)
                        break
                    except Exception as e:
                        time.sleep(attempt * 2)

        threading.Thread(target=_send, daemon=True).start()


class Incident_Severity_Classifier:
    """Bộ phân loại mức độ nghiêm trọng của sự cố giao thông."""
    @staticmethod
    def classify(
        itype: str,
        metadata: dict[str, Any],
        traffic_volume: int,
        is_night: bool,
    ) -> str:
        severity = "minor"

        if itype in (INCIDENT_WRONG_WAY, INCIDENT_PEDESTRIAN_DANGER):
            severity = "critical"
        elif itype == INCIDENT_COLLISION:
            severity = "severe"
        elif itype == INCIDENT_STOPPED_VEHICLE:
            severity = metadata.get("severity", "severe")
        elif itype == INCIDENT_FALLEN_OBJECT:
            severity = metadata.get("severity", "moderate")
        else:
            severity = "minor"

        # Tăng mức độ nếu lưu lượng cao hoặc xảy ra ban đêm
        if traffic_volume > 15 or is_night:
            if severity == "minor":
                severity = "moderate"
            elif severity == "moderate":
                severity = "severe"

        return severity


class Incident_Database:
    """Bộ lưu trữ cơ sở dữ liệu sự cố."""
    @staticmethod
    def save(incident: dict[str, Any]) -> None:
        db.insert_incident(incident)


class Alert_Dispatcher:
    """Bộ truyền tải cảnh báo thời gian thực đến đa kênh."""
    def __init__(self) -> None:
        self.callbacks: list[Callable[[dict[str, Any]], None]] = []

    def register_callback(self, cb: Callable[[dict[str, Any]], None]) -> None:
        self.callbacks.append(cb)

    def dispatch(self, incident: dict[str, Any]) -> None:
        for cb in self.callbacks:
            try:
                cb(incident)
            except Exception as e:
                logger.error("Callback dispatch failed: %s", e)


class Geo_Incident_Mapper:
    """Hệ thống bản đồ hóa địa lý sự cố giao thông."""
    def __init__(self) -> None:
        # Camera ID -> GPS coordinate
        self.camera_gps: dict[str, tuple[float, float]] = {
            "cam_01": (21.0285, 105.8542), # Hà Nội
            "cam_02": (21.0305, 105.8522),
            "cam_03": (10.7769, 106.7009), # TP.HCM
        }

    def get_gps(self, camera_id: str) -> tuple[float, float]:
        return self.camera_gps.get(camera_id, (21.0285, 105.8542))


class Historical_Incident_Analyzer:
    """Bộ phân tích lịch sử dữ liệu sự cố phục vụ báo cáo và lập bản đồ mật độ."""
    @staticmethod
    def get_reports(hours: int = 24) -> dict[str, Any]:
        return db.get_incident_stats(hours=hours)


class Sensitivity_Config_Manager:
    """Quản lý các cấu hình độ nhạy của hệ thống."""
    def __init__(self) -> None:
        self.default_configs = {
            INCIDENT_COLLISION: {"confidence_threshold": 0.60},  # Lowered from 0.75
            INCIDENT_STOPPED_VEHICLE: {"duration_seconds": 5.0, "confidence_threshold": 0.50},  # Lowered from 30s and 0.65
            INCIDENT_WRONG_WAY: {"duration_seconds": 2.0, "angle_deviation": 90.0, "confidence_threshold": 0.60},  # Lowered thresholds
            INCIDENT_FALLEN_OBJECT: {"duration_seconds": 3.0, "size_threshold": 0.1, "confidence_threshold": 0.50},  # Lowered thresholds
            INCIDENT_PEDESTRIAN_DANGER: {"duration_seconds": 1.0, "confidence_threshold": 0.50},  # Lowered from 2s and 0.70
            INCIDENT_UNUSUAL_PATTERN: {"confidence_threshold": 0.50},  # Lowered from 0.70
        }

    def get_config(self, camera_id: str) -> dict[str, Any]:
        db_cfg = db.get_incident_config(camera_id)
        if db_cfg:
            return db_cfg
        return self.default_configs


class Frame_Buffer:
    """Bộ đệm khung hình vòng giữ lịch sử video (60 giây)."""
    def __init__(self, max_seconds: int = 60, fps: float = 10.0) -> None:
        self.max_len = int(max_seconds * fps)
        self.buffer: deque[tuple[float, Any]] = deque(maxlen=self.max_len)

    def append(self, timestamp: float, frame: Any) -> None:
        self.buffer.append((timestamp, frame))

    def get_all(self) -> list[tuple[float, Any]]:
        return list(self.buffer)


# ── Core Orchestrator ────────────────────────────────────────────────────────

class Incident_Detector:
    """Bộ điều phối trung tâm tích hợp toàn bộ giải pháp Incident Detection."""
    def __init__(
        self,
        fps: float = 10.0,
        pixels_per_meter: float = 8.0,
        results_dir: str = "results",
    ) -> None:
        self.fps = fps
        self.pixels_per_meter = pixels_per_meter
        self.results_dir = results_dir

        self.roi_manager = ROI_Manager()
        self.object_tracker = Object_Tracker()
        
        self.accident_analyzer = Accident_Analyzer()
        self.stopped_vehicle_detector = Stopped_Vehicle_Detector()
        self.wrong_way_detector = Wrong_Way_Detector()
        self.fallen_object_detector = Fallen_Object_Detector()
        self.pedestrian_zone_monitor = Pedestrian_Zone_Monitor()
        self.traffic_pattern_analyzer = Traffic_Pattern_Analyzer()

        self.confidence_scorer = Confidence_Scorer()
        self.video_clip_extractor = Video_Clip_Extractor()
        self.emergency_service_notifier = Emergency_Service_Notifier()
        self.alert_dispatcher = Alert_Dispatcher()
        self.geo_mapper = Geo_Incident_Mapper()
        self.config_manager = Sensitivity_Config_Manager()
        
        # Buffer khung hình lưu 60s
        self.frame_buffer = Frame_Buffer(max_seconds=60, fps=fps)

        # Đăng ký lưu DB tự động qua Lifecycle Manager
        self.lifecycle_manager = Incident_Lifecycle_Manager(db_insert_callback=db.insert_incident)

        # Cấu hình mặc định các ROI tiêu chuẩn
        self._init_default_rois()

    def _init_default_rois(self) -> None:
        # ROI mặc định cho toàn bộ ảnh làm làn nguy hiểm (active lanes)
        self.roi_manager.set_roi("active_roadway", 0.0, 0.0, 1.0, 1.0,
                                 expected_direction=90.0, is_dangerous_zone=True)
        # Giao lộ trung tâm
        self.roi_manager.set_roi("intersection", 0.25, 0.25, 0.75, 0.75,
                                 expected_direction=90.0, is_dangerous_zone=True)

    def process_frame(
        self,
        detections: list[dict[str, Any]],
        frame_rgb: Any,
        camera_id: str,
        frame_w: int = 960,
        frame_h: int = 540,
    ) -> list[dict[str, Any]]:
        """Xử lý từng frame hình ảnh và các bounding boxes để phát hiện sự cố."""
        now = time.time()
        self.frame_buffer.append(now, frame_rgb)

        # Cập nhật track đối tượng
        tracks = self.object_tracker.update(detections, frame_w, frame_h, self.fps, self.pixels_per_meter)

        # Lấy configs độ nhạy hiện thời của camera
        configs = self.config_manager.get_config(camera_id)

        detected_list = []

        # Chạy các luồng phân tích sự cố
        # 1. Tai nạn va chạm
        cfg_col = configs.get(INCIDENT_COLLISION, {})
        detected_list.extend(self.accident_analyzer.analyze(tracks, frame_w, frame_h, self.pixels_per_meter, cfg_col))

        # 2. Xe dừng đỗ bất thường
        cfg_stop = configs.get(INCIDENT_STOPPED_VEHICLE, {})
        detected_list.extend(self.stopped_vehicle_detector.analyze(tracks, self.roi_manager, cfg_stop))

        # 3. Đi ngược chiều
        cfg_ww = configs.get(INCIDENT_WRONG_WAY, {})
        detected_list.extend(self.wrong_way_detector.analyze(tracks, self.roi_manager, frame_w, frame_h, self.pixels_per_meter, cfg_ww))

        # 4. Vật thể rơi rớt
        cfg_fall = configs.get(INCIDENT_FALLEN_OBJECT, {})
        detected_list.extend(self.fallen_object_detector.analyze(tracks, self.roi_manager, self.pixels_per_meter, cfg_fall))

        # 5. Người đi bộ nguy hiểm
        cfg_ped = configs.get(INCIDENT_PEDESTRIAN_DANGER, {})
        detected_list.extend(self.pedestrian_zone_monitor.analyze(tracks, self.roi_manager, frame_w, frame_h, self.pixels_per_meter, cfg_ped))

        # 6. Bất thường giao thông
        cfg_pat = configs.get(INCIDENT_UNUSUAL_PATTERN, {})
        detected_list.extend(self.traffic_pattern_analyzer.analyze(tracks, cfg_pat))

        # Lọc theo dõi trạng thái / volume để tính toán mức độ nguy hiểm chi tiết
        is_night = datetime.now().hour in [22, 23, 0, 1, 2, 3, 4, 5]
        traffic_vol = len(tracks)

        for item in detected_list:
            # Phân loại mức độ nghiêm trọng
            item["severity"] = Incident_Severity_Classifier.classify(
                item["type"], item.get("metadata", {}), traffic_vol, is_night
            )

        # Đẩy qua Lifecycle Manager để tạo mới / tránh trùng lặp
        new_incidents = self.lifecycle_manager.process_detected_incidents(detected_list, camera_id)

        # Cập nhật trạng thái vòng đời
        currently_detected_types = {item["type"] for item in detected_list}
        self.lifecycle_manager.update_lifecycles(currently_detected_types)

        # Dispatch alerts đối với các incident mới phát hiện
        for inc in new_incidents:
            # Tạo clip video tóm tắt
            os.makedirs(self.results_dir, exist_ok=True)
            clip_path = self.video_clip_extractor.extract_clip(inc["id"], self.frame_buffer.get_all(), self.results_dir)
            if clip_path:
                inc["video_url"] = f"/static/results/{os.path.basename(clip_path)}"
                inc["thumbnail_url"] = f"/static/results/thumb_{inc['id']}.jpg"
                # Lưu ảnh hiện thời làm thumbnail
                if frame_rgb is not None and cv2 is not None:
                    try:
                        cv2.imwrite(os.path.join(self.results_dir, f"thumb_{inc['id']}.jpg"),
                                    cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR))
                    except Exception:
                        pass
                
                # Cập nhật URL video trong DB
                try:
                    db.update_incident_state(inc["id"], inc["state"], duration=inc["duration"],
                                             video_url=inc["video_url"], thumbnail_url=inc["thumbnail_url"])
                except Exception:
                    pass

            self.alert_dispatcher.dispatch(inc)
            self.emergency_service_notifier.notify(inc)

        return new_incidents

"""
alert_manager.py — Density & Incident Alert Manager

THIẾT KẾ:
- check_and_alert(): kích hoạt khi count > threshold → insert alert DB + ghi in-memory buffer.
- fire_incident_alert(): alert riêng cho sự cố giao thông (incident, speed violation).
- Webhook HTTP POST nếu WEBHOOK_URL được cấu hình.
- Cooldown per (camera_source, alert_type): tránh spam.
- Thread-safe.
"""

import time
import threading
import logging
import json
from collections import deque
from typing import Optional
from config import Config
import db as database

logger = logging.getLogger(__name__)

_COOLDOWN_SECONDS = 60.0       # Khoảng cách tối thiểu giữa 2 alert cùng loại/camera
_INCIDENT_COOLDOWN = 30.0      # Alert sự cố — cooldown ngắn hơn
_MEMORY_BUFFER_SIZE = 100      # Số alert giữ trong RAM


class AlertManager:

    def __init__(self, high_density_threshold: int = None):
        self._threshold = high_density_threshold or Config.ALERT_HIGH_DENSITY
        self._lock = threading.Lock()

        # (camera_source, alert_type) → last timestamp
        self._last_alert: dict[tuple, float] = {}

        # In-memory buffer cho recent alerts (không cần query DB)
        self._buffer: deque[dict] = deque(maxlen=_MEMORY_BUFFER_SIZE)

        # Webhook URL từ config/env
        self._webhook_url: str = Config.WEBHOOK_URL if hasattr(Config, "WEBHOOK_URL") else ""

    # ── Public API ────────────────────────────────────────────────────────────

    def check_and_alert(
        self,
        count: int,
        camera_source: str,
        alert_type: str = "high_density",
    ) -> bool:
        """
        Kiểm tra count và tạo alert nếu vượt ngưỡng.
        Returns True nếu đã tạo alert.
        """
        if count < self._threshold:
            return False

        if not self._can_fire(camera_source, alert_type, _COOLDOWN_SECONDS):
            return False

        message = (
            f"HIGH DENSITY ALERT: {count} vehicles detected "
            f"at {camera_source} (threshold: {self._threshold})"
        )
        logger.warning(message)
        self._save_alert(alert_type, message, camera_source, count)
        self._maybe_webhook({
            "alert_type":  alert_type,
            "severity":    "high",
            "camera_id":   camera_source,
            "message":     message,
            "count":       count,
            "timestamp":   time.time(),
        })
        return True

    def fire_incident_alert(
        self,
        incident_type: str,
        description: str,
        camera_source: str,
        severity: str = "high",
    ) -> bool:
        """Tạo alert cho sự cố giao thông (WRONG_WAY, STOPPED_VEHICLE,...)."""
        cooldown = _INCIDENT_COOLDOWN if severity != "critical" else 10.0
        if not self._can_fire(camera_source, incident_type, cooldown):
            return False

        message = f"[{incident_type}] {description}"
        logger.warning("[INCIDENT] %s — %s", camera_source, message)
        self._save_alert(incident_type, message, camera_source, 0)
        self._maybe_webhook({
            "alert_type":  incident_type,
            "severity":    severity,
            "camera_id":   camera_source,
            "message":     message,
            "timestamp":   time.time(),
        })
        return True

    def fire_speed_violation_alert(
        self,
        track_id: int,
        speed_kmh: float,
        limit_kmh: float,
        camera_source: str,
        vehicle_type: str = "unknown",
    ) -> bool:
        """Alert vi phạm tốc độ."""
        key = f"speed_violation_track_{track_id}"
        if not self._can_fire(camera_source, key, VIOLATION_ALERT_COOLDOWN):
            return False

        excess = speed_kmh - limit_kmh
        message = (
            f"SPEED VIOLATION: vehicle #{track_id} ({vehicle_type}) "
            f"at {speed_kmh:.0f} km/h (limit {limit_kmh:.0f}, +{excess:.0f} km/h) "
            f"at {camera_source}"
        )
        logger.warning(message)
        self._save_alert("speed_violation", message, camera_source, int(speed_kmh))
        self._maybe_webhook({
            "alert_type":    "speed_violation",
            "severity":      "medium",
            "camera_id":     camera_source,
            "message":       message,
            "track_id":      track_id,
            "speed_kmh":     speed_kmh,
            "limit_kmh":     limit_kmh,
            "timestamp":     time.time(),
        })
        return True

    def get_recent_alerts(self, limit: int = 20) -> list[dict]:
        """Trả về alerts từ in-memory buffer."""
        with self._lock:
            items = list(self._buffer)
            items.reverse()
            return items[:limit]

    def get_thresholds(self) -> dict:
        return {
            "total_objects": self._threshold,
            "webhook_url":   "***" if self._webhook_url else "",
        }

    def update_thresholds(self, new_thresholds: dict) -> None:
        with self._lock:
            if "total_objects" in new_thresholds:
                self._threshold = max(1, int(new_thresholds["total_objects"]))
            if "webhook_url" in new_thresholds:
                self._webhook_url = str(new_thresholds["webhook_url"])

    def test_webhook(self) -> dict:
        """Gửi payload mẫu tới webhook để kiểm tra."""
        payload = {
            "alert_type": "test",
            "severity":   "low",
            "camera_id":  "test",
            "message":    "FishEye8K webhook test",
            "timestamp":  time.time(),
        }
        return self._maybe_webhook(payload, force=True) or {"status": "no_webhook"}

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _can_fire(self, camera_source: str, alert_type: str, cooldown: float) -> bool:
        key = (camera_source, alert_type)
        now = time.time()
        with self._lock:
            last = self._last_alert.get(key, 0.0)
            if now - last < cooldown:
                return False
            self._last_alert[key] = now
        return True

    def _save_alert(self, alert_type: str, message: str,
                    camera_source: str, count: int) -> None:
        record = {
            "alert_type":    alert_type,
            "message":       message,
            "camera_source": camera_source,
            "actual_count":  count,
            "timestamp":     time.time(),
        }
        with self._lock:
            self._buffer.append(record)
        try:
            database.insert_alert(alert_type, message, camera_source, count)
        except Exception as exc:
            logger.error("Failed to save alert to DB: %s", exc)

    def _maybe_webhook(self, payload: dict, force: bool = False) -> Optional[dict]:
        """POST payload tới webhook URL nếu được cấu hình."""
        url = self._webhook_url
        if not url and not force:
            return None
        if not url:
            return {"status": "no_url"}
        try:
            import urllib.request
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                status = resp.status
                logger.info("Webhook fired → %s (HTTP %d)", url, status)
                return {"status": "ok", "http_status": status}
        except Exception as exc:
            logger.warning("Webhook failed: %s", exc)
            return {"status": "error", "error": str(exc)}


VIOLATION_ALERT_COOLDOWN = 60.0

# Singleton
alert_manager = AlertManager()

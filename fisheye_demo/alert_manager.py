"""
alert_manager.py — Hệ thống cảnh báo mật độ giao thông

Chức năng:
- Cảnh báo khi số lượng xe vượt ngưỡng
- Cảnh báo khi phát hiện loại xe đặc biệt (Bus, Truck)
- Lưu alert vào DB
- Rate limiting để tránh spam alert
- Hỗ trợ webhook (tùy chọn)
"""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable

logger = logging.getLogger("fisheye_demo.alert_manager")

CLASS_NAMES = ["Car", "Bus", "Truck", "Pedestrian", "Motorbike"]

# Cấu hình ngưỡng mặc định
DEFAULT_THRESHOLDS = {
    "total_objects": int(os.getenv("ALERT_THRESHOLD_TOTAL", "15")),
    "Car": int(os.getenv("ALERT_THRESHOLD_CAR", "10")),
    "Bus": int(os.getenv("ALERT_THRESHOLD_BUS", "3")),
    "Truck": int(os.getenv("ALERT_THRESHOLD_TRUCK", "3")),
    "Pedestrian": int(os.getenv("ALERT_THRESHOLD_PEDESTRIAN", "8")),
    "Motorbike": int(os.getenv("ALERT_THRESHOLD_MOTORBIKE", "12")),
}

# Cooldown giữa các alert cùng loại (giây)
ALERT_COOLDOWN_SECONDS = int(os.getenv("ALERT_COOLDOWN_SECONDS", "60"))


class AlertManager:
    """
    Quản lý và phát sinh cảnh báo giao thông.
    Thread-safe.
    """

    def __init__(
        self,
        thresholds: dict[str, int] | None = None,
        cooldown_seconds: int = ALERT_COOLDOWN_SECONDS,
        persist_to_db: bool = True,
    ) -> None:
        self.thresholds = thresholds or dict(DEFAULT_THRESHOLDS)
        self.cooldown_seconds = cooldown_seconds
        self.persist_to_db = persist_to_db
        self._lock = threading.Lock()
        # {alert_key: last_triggered_timestamp}
        self._last_triggered: dict[str, float] = {}
        # In-memory alert buffer (100 gần nhất)
        self._alert_buffer: list[dict[str, Any]] = []
        self._callbacks: list[Callable] = []

    def add_callback(self, callback: Callable) -> None:
        """Đăng ký callback khi có alert mới."""
        self._callbacks.append(callback)

    def check_and_alert(
        self,
        total_objects: int,
        class_counts: dict[str, int],
        camera_source: str = "upload",
    ) -> list[dict[str, Any]]:
        """
        Kiểm tra ngưỡng và phát sinh alert nếu cần.
        Trả về danh sách alert mới được tạo.
        """
        new_alerts: list[dict[str, Any]] = []
        now = time.time()

        with self._lock:
            # Kiểm tra tổng số object
            total_threshold = self.thresholds.get("total_objects", 999)
            if total_objects >= total_threshold:
                alert_key = f"total:{camera_source}"
                if self._should_trigger(alert_key, now):
                    alert = self._create_alert(
                        alert_type="high_density",
                        message=f"Mật độ cao: {total_objects} đối tượng (ngưỡng: {total_threshold})",
                        camera_source=camera_source,
                        class_name="all",
                        threshold=total_threshold,
                        actual_count=total_objects,
                    )
                    new_alerts.append(alert)
                    self._last_triggered[alert_key] = now

            # Kiểm tra từng class
            for class_name, count in class_counts.items():
                class_threshold = self.thresholds.get(class_name)
                if class_threshold is None:
                    continue
                if count >= class_threshold:
                    alert_key = f"class:{class_name}:{camera_source}"
                    if self._should_trigger(alert_key, now):
                        alert = self._create_alert(
                            alert_type="class_threshold",
                            message=f"{class_name} vượt ngưỡng: {count} (ngưỡng: {class_threshold})",
                            camera_source=camera_source,
                            class_name=class_name,
                            threshold=class_threshold,
                            actual_count=count,
                        )
                        new_alerts.append(alert)
                        self._last_triggered[alert_key] = now

        # Persist và trigger callbacks ngoài lock
        for alert in new_alerts:
            self._persist_alert(alert)
            for cb in self._callbacks:
                try:
                    cb(alert)
                except Exception as exc:
                    logger.warning("Alert callback error: %s", exc)

        return new_alerts

    def _should_trigger(self, alert_key: str, now: float) -> bool:
        last = self._last_triggered.get(alert_key, 0)
        return (now - last) >= self.cooldown_seconds

    def _create_alert(
        self,
        alert_type: str,
        message: str,
        camera_source: str,
        class_name: str,
        threshold: int,
        actual_count: int,
    ) -> dict[str, Any]:
        alert = {
            "alert_type": alert_type,
            "message": message,
            "camera_source": camera_source,
            "class_name": class_name,
            "threshold": threshold,
            "actual_count": actual_count,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "acknowledged": False,
        }
        # Thêm vào buffer
        self._alert_buffer.append(alert)
        if len(self._alert_buffer) > 100:
            self._alert_buffer = self._alert_buffer[-100:]

        logger.warning(
            "ALERT [%s] %s | source=%s count=%d threshold=%d",
            alert_type,
            message,
            camera_source,
            actual_count,
            threshold,
        )
        return alert

    def _persist_alert(self, alert: dict[str, Any]) -> None:
        if not self.persist_to_db:
            return
        try:
            try:
                from db import insert_alert
            except ImportError:
                from fisheye_demo.db import insert_alert

            insert_alert(
                alert_type=alert["alert_type"],
                message=alert["message"],
                camera_source=alert.get("camera_source"),
                class_name=alert.get("class_name"),
                threshold=alert.get("threshold"),
                actual_count=alert.get("actual_count"),
            )
        except Exception as exc:
            logger.error("Alert persist failed: %s", exc)

    def get_recent_alerts(self, limit: int = 20) -> list[dict[str, Any]]:
        """Lấy alerts gần nhất từ buffer in-memory."""
        with self._lock:
            return list(reversed(self._alert_buffer[-limit:]))

    def get_thresholds(self) -> dict[str, int]:
        with self._lock:
            return dict(self.thresholds)

    def update_thresholds(self, new_thresholds: dict[str, int]) -> None:
        with self._lock:
            self.thresholds.update(new_thresholds)
        logger.info("Alert thresholds updated: %s", new_thresholds)

    def reset_cooldowns(self) -> None:
        with self._lock:
            self._last_triggered.clear()


# ── Singleton instance ────────────────────────────────────────────────────────

_alert_manager: AlertManager | None = None
_alert_manager_lock = threading.Lock()


def get_alert_manager() -> AlertManager:
    global _alert_manager
    if _alert_manager is None:
        with _alert_manager_lock:
            if _alert_manager is None:
                _alert_manager = AlertManager()
    return _alert_manager

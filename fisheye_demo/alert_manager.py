"""
alert_manager.py — Density Alert Manager

THIẾT KẾ:
- Kiểm tra count > threshold → insert alert vào DB.
- Cooldown per camera_source: không gửi cảnh báo trùng trong < 60 giây.
- Thread-safe.
"""

import time
import threading
import logging
from config import Config
import db as database

logger = logging.getLogger(__name__)

_COOLDOWN_SECONDS = 60.0   # Minimum thời gian giữa 2 alert cùng camera


class AlertManager:
    
    def __init__(self, high_density_threshold: int = None):
        self._threshold = high_density_threshold or Config.ALERT_HIGH_DENSITY
        self._last_alert: dict[str, float] = {}   # camera_source → timestamp
        self._lock = threading.Lock()
    
    def check_and_alert(
        self,
        count: int,
        camera_source: str,
        alert_type: str = "high_density",
    ) -> bool:
        """
        Kiểm tra count và tạo alert nếu cần.
        
        Returns True nếu đã tạo alert, False nếu không.
        """
        if count < self._threshold:
            return False
        
        now = time.time()
        
        with self._lock:
            last = self._last_alert.get(camera_source, 0.0)
            if now - last < _COOLDOWN_SECONDS:
                return False   # Cooldown chưa hết
            
            self._last_alert[camera_source] = now
        
        message = (
            f"HIGH DENSITY ALERT: {count} vehicles detected "
            f"at {camera_source} (threshold: {self._threshold})"
        )
        logger.warning(message)
        
        try:
            database.insert_alert(
                alert_type=alert_type,
                message=message,
                camera_source=camera_source,
                count=count,
            )
        except Exception as e:
            logger.error(f"Failed to save alert to DB: {e}")
        
        return True


# Singleton
alert_manager = AlertManager()

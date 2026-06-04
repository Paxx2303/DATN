"""
services/model_registry.py — YOLO Model Loader & Cache

THIẾT KẾ:
- _model_cache: dict[str, YOLO] — key là model_key ("best", "nano", ...)
- Lazy loading: model chỉ load khi được yêu cầu lần đầu.
- Thread-safe với threading.Lock.
- Hỗ trợ device switching giữa các request.
"""

import threading
import logging
from pathlib import Path
from typing import Optional
from config import Config

logger = logging.getLogger(__name__)

_model_cache: dict = {}
_lock = threading.Lock()


def load_model(model_key: str = None, device: str = None):
    """
    Tải và cache YOLO model theo model_key.
    
    Parameters
    ----------
    model_key : Key trong Config.AVAILABLE_MODELS (mặc định: DEFAULT_MODEL_KEY)
    device    : "cpu" | "cuda:0" | "mps" (mặc định: DEFAULT_DEVICE)
    
    Returns
    -------
    ultralytics.YOLO instance
    
    Raises
    ------
    FileNotFoundError nếu file .pt không tồn tại
    """
    model_key = model_key or Config.DEFAULT_MODEL_KEY
    device    = device or Config.DEFAULT_DEVICE
    
    cache_key = f"{model_key}_{device}"
    
    with _lock:
        if cache_key in _model_cache:
            logger.debug(f"Model cache hit: {cache_key}")
            return _model_cache[cache_key]
        
        model_path = Config.AVAILABLE_MODELS.get(model_key)
        if not model_path:
            raise KeyError(f"Unknown model key: '{model_key}'. Available: {list(Config.AVAILABLE_MODELS.keys())}")
        
        if not Path(model_path).exists():
            raise FileNotFoundError(
                f"Model file not found: {model_path}\n"
                f"Hãy đặt file .pt vào thư mục: {Config.MODEL_FOLDER}"
            )
        
        logger.info(f"Loading model '{model_key}' from {model_path} on {device}...")
        
        from ultralytics import YOLO
        model = YOLO(model_path)
        model.to(device)
        
        _model_cache[cache_key] = model
        logger.info(f"✅ Model '{model_key}' loaded and cached")
        return model


def get_available_models() -> dict[str, dict]:
    """
    Trả về thông tin các model có sẵn (path, exists, loaded).
    """
    result = {}
    for key, path in Config.AVAILABLE_MODELS.items():
        exists = Path(path).exists()
        cache_key_cpu = f"{key}_cpu"
        loaded = cache_key_cpu in _model_cache or any(
            k.startswith(key) for k in _model_cache
        )
        result[key] = {
            "path": path,
            "exists": exists,
            "loaded": loaded,
        }
    return result


def unload_model(model_key: str = None) -> bool:
    """Giải phóng model khỏi cache (để giải phóng VRAM). Trả về True nếu thành công."""
    with _lock:
        keys_to_remove = [k for k in _model_cache if k.startswith(model_key or "")]
        for k in keys_to_remove:
            del _model_cache[k]
            logger.info(f"Model '{k}' unloaded from cache")
        return len(keys_to_remove) > 0

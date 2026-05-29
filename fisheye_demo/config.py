from __future__ import annotations

import os
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# --- Logger Setup ---
logger = logging.getLogger("fisheye_demo.config")

# --- Constants ---
CLASS_NAMES = ["Car", "Bus", "Truck", "Pedestrian", "Motorbike"]
CLASS_COLORS = {
    "Car": "#4FC3F7",
    "Bus": "#FFB74D",
    "Truck": "#EF5350",
    "Pedestrian": "#A5D6A7",
    "Motorbike": "#CE93D8",
}
NAME_MAP = {
    "car": "Car",
    "bus": "Bus",
    "truck": "Truck",
    "person": "Pedestrian",
    "pedestrian": "Pedestrian",
    "motorcycle": "Motorbike",
    "motorbike": "Motorbike",
    "bicycle": "Motorbike",
}
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".m4v"}
ALLOWED_MEDIA_EXTENSIONS = ALLOWED_IMAGE_EXTENSIONS | ALLOWED_VIDEO_EXTENSIONS
SUPPORTED_SOURCE_LAYOUTS = ("fisheye", "normal")
TRAFFIC_CHECKPOINT_NAME = "traffic.pt"
SUPPORTED_EXTERNAL_CAMERA_SOURCE_MODES = ("snapshot", "stream")

# --- Path Configurations ---
APP_DIR = Path(__file__).resolve().parent
PROJECT_DIR = APP_DIR.parent
STATIC_DIR = APP_DIR / "static"
ENV_PATH = APP_DIR / ".env"

@dataclass
class AppSettings:
    upload_dir: Path
    results_dir: Path
    recent_image_db_path: Path
    max_upload_mb: int
    default_conf: float
    default_iou: float
    history_limit: int
    recent_image_limit: int
    preload_model: bool
    fallback_model_name: str
    model_path_override: str | None
    filter_fallback_to_supported_classes: bool
    device: str
    max_video_seconds: int
    default_fisheye_strength: float
    default_fisheye_radius: float
    default_fisheye_effect: str
    camera_fisheye_strength: float
    camera_fisheye_radius: float
    camera_fisheye_effect: str
    camera_fisheye_center_x: float
    camera_fisheye_center_y: float
    camera_fisheye_axis_scale_x: float
    camera_fisheye_axis_scale_y: float
    camera_fisheye_full_frame: bool
    external_camera_source_mode: str
    external_camera_url: str
    external_camera_stream_url: str
    external_camera_limit: int
    external_camera_live_interval_seconds: float

def load_env_file(env_path: Path) -> None:
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value

def get_compute_device() -> str:
    try:
        import torch
        if torch.cuda.is_available():
            return "0"
    except Exception:
        pass
    return "cpu"

def parse_bool(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}

def coerce_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return parse_bool(str(value))

def clamp_float(value: Any, minimum: float, maximum: float, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, number))

def normalize_source_layout(value: Any) -> str:
    layout = str(value or "fisheye").strip().lower()
    return layout if layout in SUPPORTED_SOURCE_LAYOUTS else "fisheye"

def normalize_external_camera_source_mode(value: Any, source_ref: str | None = None) -> str:
    mode = str(value or "").strip().lower()
    if mode in SUPPORTED_EXTERNAL_CAMERA_SOURCE_MODES:
        return mode

    source_text = str(source_ref or "").strip().lower()
    if source_text.startswith(("rtsp://", "rtmp://", "udp://", "tcp://", "file://")):
        return "stream"
    if any(token in source_text for token in (".m3u8", ".mpd", ".mjpeg", ".mjpg")):
        return "stream"
    return "snapshot"

def build_settings(overrides: dict[str, Any] | None = None) -> AppSettings:
    # Make sure env is loaded
    load_env_file(ENV_PATH)
    
    overrides = overrides or {}

    upload_dir = Path(
        overrides.get("upload_dir")
        or os.getenv("FISHEYE_UPLOAD_DIR")
        or STATIC_DIR / "uploads"
    )
    results_dir = Path(
        overrides.get("results_dir")
        or os.getenv("FISHEYE_RESULTS_DIR")
        or os.getenv("ARTIFACT_DIR")
        or STATIC_DIR / "results"
    )
    recent_image_db_path = Path(
        overrides.get("recent_image_db_path")
        or os.getenv("FISHEYE_RECENT_IMAGE_DB")
        or APP_DIR / "recent_images.sqlite3"
    )
    
    upload_dir.mkdir(parents=True, exist_ok=True)
    results_dir.mkdir(parents=True, exist_ok=True)
    recent_image_db_path.parent.mkdir(parents=True, exist_ok=True)

    # Late import to prevent circular dependency
    try:
        from fisheye import EFFECT_MAP
    except ModuleNotFoundError:
        from fisheye_demo.fisheye import EFFECT_MAP

    default_fisheye_effect = str(
        overrides.get("default_fisheye_effect")
        or os.getenv("FISHEYE_DEFAULT_EFFECT")
        or os.getenv("FISHEYE_EFFECT")
        or "standard"
    )
    if default_fisheye_effect not in EFFECT_MAP:
        default_fisheye_effect = "standard"

    camera_fisheye_effect = str(
        overrides.get("camera_fisheye_effect")
        or os.getenv("FISHEYE_CAMERA_EFFECT")
        or "traffic_camera"
    )
    if camera_fisheye_effect not in EFFECT_MAP:
        camera_fisheye_effect = "traffic_camera"

    external_camera_url = str(
        overrides.get("external_camera_url")
        or os.getenv("FISHEYE_EXTERNAL_CAMERA_URL")
        or "https://camera.0511.vn/camera.html"
    )
    external_camera_stream_url = str(
        overrides.get("external_camera_stream_url")
        or os.getenv("FISHEYE_EXTERNAL_CAMERA_STREAM_URL")
        or ""
    ).strip()
    
    external_camera_source_mode = normalize_external_camera_source_mode(
        overrides.get("external_camera_source_mode")
        or os.getenv("FISHEYE_EXTERNAL_CAMERA_SOURCE_MODE"),
        external_camera_stream_url or external_camera_url,
    )
    if external_camera_source_mode == "stream" and not external_camera_stream_url:
        external_camera_stream_url = external_camera_url

    return AppSettings(
        upload_dir=upload_dir,
        results_dir=results_dir,
        recent_image_db_path=recent_image_db_path,
        max_upload_mb=int(overrides.get("max_upload_mb") or os.getenv("FISHEYE_MAX_UPLOAD_MB", "32")),
        default_conf=float(
            overrides.get("default_conf")
            or os.getenv("FISHEYE_DEFAULT_CONF")
            or os.getenv("CONFIDENCE_THRESHOLD")
            or "0.25"
        ),
        default_iou=float(
            overrides.get("default_iou")
            or os.getenv("FISHEYE_DEFAULT_IOU")
            or os.getenv("IOU_THRESHOLD")
            or "0.45"
        ),
        history_limit=int(overrides.get("history_limit") or os.getenv("FISHEYE_HISTORY_LIMIT", "12")),
        recent_image_limit=max(
            1,
            min(
                1000,
                int(overrides.get("recent_image_limit") or os.getenv("FISHEYE_RECENT_IMAGE_LIMIT", "100")),
            ),
        ),
        preload_model=coerce_bool(overrides.get("preload_model"), parse_bool(os.getenv("FISHEYE_PRELOAD_MODEL", "1"))),
        fallback_model_name=str(overrides.get("fallback_model_name") or os.getenv("FISHEYE_FALLBACK_MODEL", "traffic.pt")),
        model_path_override=overrides.get("model_path_override") or os.getenv("FISHEYE_MODEL_PATH"),
        filter_fallback_to_supported_classes=coerce_bool(
            overrides.get("filter_fallback_to_supported_classes"),
            parse_bool(os.getenv("FISHEYE_FILTER_FALLBACK_CLASSES", "1")),
        ),
        device=str(overrides.get("device") or os.getenv("FISHEYE_DEVICE") or os.getenv("DEVICE") or get_compute_device()),
        max_video_seconds=int(overrides.get("max_video_seconds") or os.getenv("FISHEYE_MAX_VIDEO_SECONDS", "60")),
        default_fisheye_strength=clamp_float(
            overrides.get("default_fisheye_strength") or os.getenv("FISHEYE_DEFAULT_STRENGTH") or os.getenv("FISHEYE_STRENGTH"),
            0.0,
            1.0,
            0.7,
        ),
        default_fisheye_radius=clamp_float(
            overrides.get("default_fisheye_radius") or os.getenv("FISHEYE_DEFAULT_RADIUS") or os.getenv("FISHEYE_RADIUS"),
            0.0,
            1.0,
            0.85,
        ),
        default_fisheye_effect=default_fisheye_effect,
        camera_fisheye_strength=clamp_float(
            overrides.get("camera_fisheye_strength") or os.getenv("FISHEYE_CAMERA_STRENGTH"),
            0.0,
            1.0,
            0.82,
        ),
        camera_fisheye_radius=clamp_float(
            overrides.get("camera_fisheye_radius") or os.getenv("FISHEYE_CAMERA_RADIUS"),
            0.0,
            1.0,
            1.0,
        ),
        camera_fisheye_effect=camera_fisheye_effect,
        camera_fisheye_center_x=clamp_float(
            overrides.get("camera_fisheye_center_x") or os.getenv("FISHEYE_CAMERA_CENTER_X"),
            0.0,
            1.0,
            0.5,
        ),
        camera_fisheye_center_y=clamp_float(
            overrides.get("camera_fisheye_center_y") or os.getenv("FISHEYE_CAMERA_CENTER_Y"),
            0.0,
            1.0,
            0.6,
        ),
        camera_fisheye_axis_scale_x=clamp_float(
            overrides.get("camera_fisheye_axis_scale_x") or os.getenv("FISHEYE_CAMERA_AXIS_SCALE_X"),
            0.35,
            2.5,
            1.18,
        ),
        camera_fisheye_axis_scale_y=clamp_float(
            overrides.get("camera_fisheye_axis_scale_y") or os.getenv("FISHEYE_CAMERA_AXIS_SCALE_Y"),
            0.35,
            2.5,
            0.82,
        ),
        camera_fisheye_full_frame=coerce_bool(
            overrides.get("camera_fisheye_full_frame"),
            parse_bool(os.getenv("FISHEYE_CAMERA_FULL_FRAME", "1")),
        ),
        external_camera_source_mode=external_camera_source_mode,
        external_camera_url=external_camera_url,
        external_camera_stream_url=external_camera_stream_url,
        external_camera_limit=int(overrides.get("external_camera_limit") or os.getenv("FISHEYE_EXTERNAL_CAMERA_LIMIT", "1")),
        external_camera_live_interval_seconds=clamp_float(
            overrides.get("external_camera_live_interval_seconds")
            or os.getenv("FISHEYE_EXTERNAL_CAMERA_LIVE_INTERVAL", "1.0"),
            0.1,
            120.0,
            1.0,
        ),
    )

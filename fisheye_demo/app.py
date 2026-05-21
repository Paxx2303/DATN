from __future__ import annotations

import base64
import io
import json
import logging
import os
import re
import shutil
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from flask import Flask, Response, jsonify, render_template, request, send_from_directory, url_for
from PIL import Image, ImageFile

try:
    from fisheye_demo.fisheye import EFFECT_LABELS_VI, EFFECT_MAP, apply_fisheye
except ModuleNotFoundError:
    from fisheye import EFFECT_LABELS_VI, EFFECT_MAP, apply_fisheye

try:
    from fisheye_demo.external_camera_detector import (
        build_camera_collage,
        capture_stream_frame,
        download_camera_snapshot,
        extract_camera_entries,
    )
except ModuleNotFoundError:
    from external_camera_detector import (
        build_camera_collage,
        capture_stream_frame,
        download_camera_snapshot,
        extract_camera_entries,
    )

try:
    from fisheye_demo.video_detect import run_video_detect
except ModuleNotFoundError:
    from video_detect import run_video_detect

try:
    from fisheye_demo.recent_image_store import RecentImageStore
except ModuleNotFoundError:
    from recent_image_store import RecentImageStore

ImageFile.LOAD_TRUNCATED_IMAGES = True

logger = logging.getLogger("fisheye_demo.live")
if not logger.handlers:
    _live_handler = logging.StreamHandler()
    _live_handler.setFormatter(
        logging.Formatter("[%(asctime)s] %(levelname)s %(name)s: %(message)s", "%H:%M:%S")
    )
    logger.addHandler(_live_handler)
logger.setLevel(logging.INFO)
logger.propagate = False

APP_DIR = Path(__file__).resolve().parent
PROJECT_DIR = APP_DIR.parent
STATIC_DIR = APP_DIR / "static"
ENV_PATH = APP_DIR / ".env"

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


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def utc_now_iso_ms() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def utc_now_iso_from_timestamp(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def pil_to_b64(image: Image.Image, fmt: str = "JPEG", quality: int = 92) -> str:
    buffer = io.BytesIO()
    _fmt = fmt.upper()
    save_kwargs: dict[str, Any] = {"format": _fmt}
    if _fmt in {"JPEG", "WEBP"}:
        save_kwargs["quality"] = quality
    image.save(buffer, **save_kwargs)
    mime = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp", "BMP": "image/bmp"}.get(_fmt, "image/jpeg")
    return f"data:{mime};base64," + base64.b64encode(buffer.getvalue()).decode("utf-8")


def pil_to_jpeg_bytes(image: Image.Image, quality: int = 90) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=quality)
    return buffer.getvalue()


def build_placeholder_jpeg(message: str, size: tuple[int, int] = (960, 540)) -> bytes:
    image = Image.new("RGB", size, "#08131c")
    try:
        from PIL import ImageDraw

        draw = ImageDraw.Draw(image)
        draw.text((24, size[1] // 2 - 10), message[:100], fill="#edf5fb")
    except Exception:
        pass
    return pil_to_jpeg_bytes(image, quality=85)


def build_mjpeg_part(frame_bytes: bytes) -> bytes:
    return (
        b"--frame\r\n"
        b"Content-Type: image/jpeg\r\n"
        + f"Content-Length: {len(frame_bytes)}\r\n".encode("ascii")
        + b"Cache-Control: no-cache\r\n\r\n"
        + frame_bytes
        + b"\r\n"
    )


def secure_filename(filename: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {".", "-", "_"} else "_" for ch in filename)
    return cleaned.strip("._") or "upload.bin"


def normalize_class_name(raw_name: str) -> str:
    return NAME_MAP.get(raw_name.strip().lower(), raw_name.strip())


def to_hex_bgr(color_hex: str) -> tuple[int, int, int]:
    red = int(color_hex[1:3], 16)
    green = int(color_hex[3:5], 16)
    blue = int(color_hex[5:7], 16)
    return blue, green, red


def build_settings(overrides: dict[str, Any] | None = None) -> AppSettings:
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
        fallback_model_name=str(overrides.get("fallback_model_name") or os.getenv("FISHEYE_FALLBACK_MODEL", "yolo11n.pt")),
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


def build_preprocessing_options(
    form: Any,
    settings: AppSettings,
    *,
    default_source_layout: str = "fisheye",
    profile: str = "default",
) -> dict[str, Any]:
    source_layout = normalize_source_layout(form.get("source_layout") or default_source_layout)
    enabled_default = source_layout == "normal"

    use_camera_profile = profile == "external_camera"
    default_effect = settings.camera_fisheye_effect if use_camera_profile else settings.default_fisheye_effect
    default_strength = settings.camera_fisheye_strength if use_camera_profile else settings.default_fisheye_strength
    default_radius = settings.camera_fisheye_radius if use_camera_profile else settings.default_fisheye_radius
    default_center_x = settings.camera_fisheye_center_x if use_camera_profile else 0.5
    default_center_y = settings.camera_fisheye_center_y if use_camera_profile else 0.5
    default_axis_scale_x = settings.camera_fisheye_axis_scale_x if use_camera_profile else 1.0
    default_axis_scale_y = settings.camera_fisheye_axis_scale_y if use_camera_profile else 1.0
    default_full_frame = settings.camera_fisheye_full_frame if use_camera_profile else False

    effect = str(form.get("fisheye_effect") or default_effect).strip().lower()
    if effect not in EFFECT_MAP:
        effect = default_effect

    return {
        "source_layout": source_layout,
        "enabled": coerce_bool(form.get("apply_fisheye"), enabled_default),
        "strength": clamp_float(form.get("fisheye_strength"), 0.0, 1.0, default_strength),
        "radius": clamp_float(form.get("fisheye_radius"), 0.0, 1.0, default_radius),
        "effect": effect,
        "center_x_ratio": clamp_float(form.get("fisheye_center_x"), 0.0, 1.0, default_center_x),
        "center_y_ratio": clamp_float(form.get("fisheye_center_y"), 0.0, 1.0, default_center_y),
        "axis_scale_x": clamp_float(form.get("fisheye_axis_scale_x"), 0.35, 2.5, default_axis_scale_x),
        "axis_scale_y": clamp_float(form.get("fisheye_axis_scale_y"), 0.35, 2.5, default_axis_scale_y),
        "full_frame": coerce_bool(form.get("fisheye_full_frame"), default_full_frame),
        "profile": profile,
    }


def get_request_file(*names: str):
    for name in names:
        upload = request.files.get(name)
        if upload is not None:
            return upload
    return None


def get_video_target_detect_fps(form: Any) -> float | None:
    raw = form.get("video_detect_fps")
    if raw is None or str(raw).strip() == "":
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    return float(min(120.0, max(0.25, value)))


def get_request_float(form: Any, names: tuple[str, ...], minimum: float, maximum: float, default: float) -> float:
    for name in names:
        if form.get(name) is not None:
            return clamp_float(form.get(name), minimum, maximum, default)
    return default


def get_requested_model_key(form: Any, registry: ModelRegistry) -> str | None:
    raw_value = str(form.get("model_key") or "").strip()
    if not raw_value:
        return None
    if registry.get_model_entry(raw_value) is None:
        raise ValueError("Unsupported model checkpoint selected.")
    return raw_value


def get_external_camera_source_config(values: Any, settings: AppSettings) -> dict[str, str]:
    provided_source = str(values.get("external_camera_url") or "").strip()
    provided_stream = str(values.get("external_camera_stream_url") or "").strip()
    source_mode = normalize_external_camera_source_mode(
        values.get("external_camera_source_mode") or settings.external_camera_source_mode,
        provided_stream or provided_source or settings.external_camera_stream_url or settings.external_camera_url,
    )

    if source_mode == "stream":
        stream_url = provided_stream or provided_source or settings.external_camera_stream_url or settings.external_camera_url
        if not stream_url:
            raise ValueError("No external camera stream URL configured.")
        return {
            "source_mode": "stream",
            "source_url": stream_url,
            "stream_url": stream_url,
        }

    source_url = provided_source or settings.external_camera_url
    if not source_url:
        raise ValueError("No external camera source URL configured.")
    return {
        "source_mode": "snapshot",
        "source_url": source_url,
        "stream_url": "",
    }


def apply_preprocessing(image: Image.Image, preprocessing: dict[str, Any]) -> Image.Image:
    if not preprocessing["enabled"]:
        return image.copy()
    return apply_fisheye(
        image,
        strength=preprocessing["strength"],
        radius=preprocessing["radius"],
        effect=preprocessing["effect"],
        center_x_ratio=preprocessing.get("center_x_ratio", 0.5),
        center_y_ratio=preprocessing.get("center_y_ratio", 0.5),
        axis_scale_x=preprocessing.get("axis_scale_x", 1.0),
        axis_scale_y=preprocessing.get("axis_scale_y", 1.0),
        full_frame=preprocessing.get("full_frame", False),
    )


class ModelRegistry:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self._model = None
        self._info = {
            "loaded": False,
            "source": "unloaded",
            "loaded_from": None,
            "loaded_from_name": None,
            "selected_key": None,
            "selected_name": None,
            "candidate": None,
            "device": settings.device,
            "error": None,
            "class_names": [],
            "last_loaded_at": None,
        }
        self._lock = threading.Lock()

    def status_snapshot(self) -> dict[str, Any]:
        selectable_models = self.list_selectable_models()
        snapshot = dict(self._info)
        snapshot["candidate"] = self.resolve_candidate_path()
        snapshot["available_models"] = selectable_models
        if not snapshot.get("selected_key") and selectable_models:
            snapshot["selected_key"] = selectable_models[0]["key"]
            snapshot["selected_name"] = selectable_models[0]["name"]
        return snapshot

    def resolve_candidate_path(self) -> str | None:
        default_entry = self.get_model_entry(None)
        return str(default_entry["path"]) if default_entry else None

    def list_available_models(self) -> list[dict[str, Any]]:
        fallback_name = Path(self.settings.fallback_model_name).name.lower()
        entries: list[dict[str, Any]] = []
        used_keys: set[str] = set()
        for path in self._discover_candidate_paths():
            key = self._build_model_key(path, used_keys)
            entries.append(
                {
                    "key": key,
                    "name": path.name,
                    "path": str(path),
                    "rank": self._score_weight_path(path),
                    "last_modified": utc_now_iso_from_timestamp(path.stat().st_mtime),
                    "is_fallback": path.name.lower() == fallback_name,
                }
            )
        return entries

    def list_selectable_models(self) -> list[dict[str, Any]]:
        available_models = self.list_available_models()
        traffic_models = [entry for entry in available_models if entry["name"].lower() == TRAFFIC_CHECKPOINT_NAME]
        if traffic_models:
            return traffic_models[:1]

        fallback_models = [entry for entry in available_models if entry["is_fallback"]]
        return fallback_models[:1]

    def get_model_entry(self, model_key: str | None, *, selectable_only: bool = True) -> dict[str, Any] | None:
        entries = self.list_selectable_models() if selectable_only else self.list_available_models()
        if model_key:
            for entry in entries:
                if entry["key"] == model_key:
                    return entry
            return None
        return entries[0] if entries else None

    def load(self, model_key: str | None = None):
        selected_entry = self.get_model_entry(model_key, selectable_only=False)
        if model_key and selected_entry is None:
            raise ValueError("Unsupported model checkpoint selected.")

        selected_key = selected_entry["key"] if selected_entry else None
        if self._model is not None and self._info.get("selected_key") == selected_key:
            return self._model, dict(self._info)

        with self._lock:
            if self._model is not None and self._info.get("selected_key") == selected_key:
                return self._model, dict(self._info)

            try:
                from ultralytics import YOLO
            except Exception as exc:
                self._info["error"] = f"Ultralytics import failed: {exc}"
                raise RuntimeError(self._info["error"]) from exc

            loaded_from = None
            source = "fallback"

            try:
                if selected_entry is not None:
                    loaded_from = selected_entry["path"]
                    self._model = YOLO(loaded_from)
                    source = "fallback" if selected_entry["is_fallback"] else "custom"
                else:
                    self._model = YOLO(self.settings.fallback_model_name)
                    loaded_from = self.settings.fallback_model_name
            except Exception as exc:
                self._info["error"] = f"Model load failed: {exc}"
                raise RuntimeError(self._info["error"]) from exc

            class_names = self._extract_model_names(self._model)
            self._info.update(
                {
                    "loaded": True,
                    "source": source,
                    "loaded_from": str(loaded_from),
                    "loaded_from_name": Path(str(loaded_from)).name,
                    "selected_key": selected_key,
                    "selected_name": selected_entry["name"] if selected_entry else Path(str(loaded_from)).name,
                    "candidate": self.resolve_candidate_path(),
                    "device": self.settings.device,
                    "error": None,
                    "class_names": class_names,
                    "last_loaded_at": utc_now_iso(),
                }
            )
            return self._model, dict(self._info)

    def _discover_candidate_paths(self) -> list[Path]:
        candidates: list[Path] = []
        seen: set[Path] = set()

        if self.settings.model_path_override:
            override_path = Path(self.settings.model_path_override)
            if override_path.exists():
                resolved_path = override_path.resolve()
                candidates.append(resolved_path)
                seen.add(resolved_path)

        for root in (PROJECT_DIR, APP_DIR):
            if not root.exists():
                continue
            for file_path in root.glob("*.pt"):
                resolved_path = file_path.resolve()
                if resolved_path in seen:
                    continue
                candidates.append(resolved_path)
                seen.add(resolved_path)

        return sorted(
            candidates,
            key=lambda path: (self._score_weight_path(path), path.stat().st_mtime),
            reverse=True,
        )

    @staticmethod
    def _build_model_key(path: Path, used_keys: set[str]) -> str:
        base_key = re.sub(r"[^a-z0-9]+", "-", path.stem.lower()).strip("-") or "model"
        key = base_key
        suffix = 2
        while key in used_keys:
            key = f"{base_key}-{suffix}"
            suffix += 1
        used_keys.add(key)
        return key

    @staticmethod
    def _extract_model_names(model) -> list[str]:
        names = getattr(getattr(model, "model", None), "names", None) or getattr(model, "names", None) or {}
        if isinstance(names, dict):
            return [str(names[idx]) for idx in sorted(names.keys())]
        if isinstance(names, (list, tuple)):
            return [str(name) for name in names]
        return []

    @staticmethod
    def _score_weight_path(path: Path) -> int:
        name = path.name.lower()
        score = 0
        if "fisheye" in name:
            score += 120
        if "best" in name:
            score += 100
        if "resume" in name:
            score += 40
        if "yolo11" in name:
            score += 25
        if name == "yolo11n.pt":
            score -= 250
        return score


def read_uploaded_image(file_storage) -> Image.Image:
    try:
        image = Image.open(file_storage.stream)
        image.load()
        return image.convert("RGB")
    except Exception as exc:
        raise ValueError(f"Invalid image file: {exc}") from exc


def save_uploaded_file(settings: AppSettings, file_storage, suffix: str) -> Path:
    temp_path = settings.upload_dir / f"upload-{uuid.uuid4().hex}{suffix}"
    file_storage.stream.seek(0)
    file_storage.save(temp_path)
    return temp_path


def inspect_video_duration(video_path: Path) -> dict[str, float]:
    try:
        import cv2
    except Exception as exc:
        raise RuntimeError(f"OpenCV import failed: {exc}") from exc

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise ValueError("Cannot inspect uploaded video.")

    try:
        total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        fps = capture.get(cv2.CAP_PROP_FPS) or 25.0
    finally:
        capture.release()

    duration_seconds = total_frames / fps if fps > 0 else 0.0
    return {
        "total_frames": total_frames,
        "fps": float(fps),
        "duration_seconds": float(duration_seconds),
    }


def create_result_dir(settings: AppSettings) -> tuple[str, Path]:
    result_id = f"{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
    result_dir = settings.results_dir / result_id
    result_dir.mkdir(parents=True, exist_ok=True)
    return result_id, result_dir


def write_record(result_dir: Path, record: dict[str, Any]) -> None:
    (result_dir / "metadata.json").write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")


def build_artifact_urls(record: dict[str, Any]) -> dict[str, str]:
    return {
        key: url_for("artifact_file", result_id=record["id"], filename=value)
        for key, value in record.get("artifacts", {}).items()
    }


def read_record(results_dir: Path, result_id: str) -> dict[str, Any] | None:
    metadata_path = results_dir / result_id / "metadata.json"
    if not metadata_path.exists():
        return None
    return json.loads(metadata_path.read_text(encoding="utf-8"))


def artifact_mime_type(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".png":
        return "image/png"
    if suffix == ".webp":
        return "image/webp"
    if suffix == ".bmp":
        return "image/bmp"
    if suffix in {".tif", ".tiff"}:
        return "image/tiff"
    return "application/octet-stream"


def serialize_pil_image(image: Image.Image, filename: str) -> bytes:
    suffix = Path(filename).suffix.lower()
    buffer = io.BytesIO()
    if suffix == ".png":
        image.save(buffer, format="PNG")
    elif suffix == ".webp":
        image.save(buffer, format="WEBP", quality=90)
    else:
        image.save(buffer, format="JPEG", quality=92)
    return buffer.getvalue()


def recent_image_metadata_from_record(record: dict[str, Any]) -> dict[str, Any]:
    summary = record.get("summary") or {}
    return {
        "filename": record.get("filename"),
        "summary": summary,
        "source_layout": record.get("source_layout"),
    }


def persist_recent_image(
    recent_image_store: RecentImageStore,
    *,
    record: dict[str, Any],
    image_role: str,
    filename: str,
    image: Image.Image,
) -> None:
    recent_image_store.add_image(
        source_key=f"{record['id']}:{image_role}",
        source_result_id=record["id"],
        task=str(record.get("task") or ""),
        media_type=str(record.get("media_type") or ""),
        image_role=image_role,
        filename=filename,
        mime_type=artifact_mime_type(filename),
        width=image.width,
        height=image.height,
        created_at=str(record.get("created_at") or utc_now_iso()),
        metadata=recent_image_metadata_from_record(record),
        image_bytes=serialize_pil_image(image, filename),
    )


def resolve_recent_image_artifact(record: dict[str, Any]) -> tuple[str, str] | None:
    artifacts = record.get("artifacts") or {}
    media_type = str(record.get("media_type") or "")
    task = str(record.get("task") or "")

    if task == "detect" and media_type == "image" and artifacts.get("annotated"):
        return "annotated", artifacts["annotated"]
    if task == "convert" and media_type == "image" and artifacts.get("fisheye_image"):
        return "fisheye_image", artifacts["fisheye_image"]
    if task == "detect" and media_type == "video" and artifacts.get("preview_annotated"):
        return "preview_annotated", artifacts["preview_annotated"]
    if task == "convert" and media_type == "video" and artifacts.get("preview_fisheye"):
        return "preview_fisheye", artifacts["preview_fisheye"]
    if media_type == "external_camera_grid" and artifacts.get("overview_annotated"):
        return "overview_annotated", artifacts["overview_annotated"]
    return None


def backfill_recent_image_store(settings: AppSettings, recent_image_store: RecentImageStore) -> None:
    store_stats = recent_image_store.stats()
    if store_stats["stored_images"] >= recent_image_store.max_images:
        return

    records = list_records(settings.results_dir, recent_image_store.max_images)
    for record in reversed(records):
        resolved_artifact = resolve_recent_image_artifact(record)
        if resolved_artifact is None:
            continue

        image_role, artifact_name = resolved_artifact
        artifact_path = settings.results_dir / record["id"] / artifact_name
        if not artifact_path.exists():
            continue

        try:
            with Image.open(artifact_path) as image:
                image.load()
                persist_recent_image(
                    recent_image_store,
                    record=record,
                    image_role=image_role,
                    filename=artifact_name,
                    image=image.convert("RGB"),
                )
        except Exception:
            continue


def list_records(results_dir: Path, limit: int) -> list[dict[str, Any]]:
    if not results_dir.exists():
        return []

    candidates = sorted(
        [path for path in results_dir.iterdir() if path.is_dir()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    records = []
    for directory in candidates[:limit]:
        record = read_record(results_dir, directory.name)
        if record:
            records.append(record)
    return records


def run_inference(
    registry: ModelRegistry,
    settings: AppSettings,
    image: Image.Image,
    conf_threshold: float,
    iou_threshold: float,
    model_key: str | None = None,
):
    model, model_info = registry.load(model_key)

    try:
        import cv2
    except Exception as exc:
        raise RuntimeError(f"OpenCV import failed: {exc}") from exc

    frame_rgb = np.array(image.convert("RGB"))
    frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)

    started_at = time.perf_counter()
    results = model.predict(
        source=frame_bgr,
        conf=conf_threshold,
        iou=iou_threshold,
        verbose=False,
        device=settings.device,
    )[0]
    elapsed_ms = (time.perf_counter() - started_at) * 1000

    annotated = frame_rgb.copy()
    detections: list[dict[str, Any]] = []
    class_counts = {class_name: 0 for class_name in CLASS_NAMES}
    raw_names = getattr(getattr(model, "model", None), "names", None) or getattr(model, "names", None) or {}

    for box in list(results.boxes or []):
        x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
        confidence = float(box.conf[0])
        class_id = int(box.cls[0])
        raw_label = str(raw_names.get(class_id, class_id))
        label = normalize_class_name(raw_label)

        if model_info["source"] == "fallback" and settings.filter_fallback_to_supported_classes and label not in CLASS_NAMES:
            continue

        color = CLASS_COLORS.get(label, "#FFFFFF")
        color_bgr = to_hex_bgr(color)
        cv2.rectangle(annotated, (x1, y1), (x2, y2), color_bgr, 3)

        box_label = f"{label} {confidence:.0%}"
        (text_width, text_height), baseline = cv2.getTextSize(box_label, cv2.FONT_HERSHEY_SIMPLEX, 0.62, 2)
        label_x = x1
        label_y = max(y1 - 10, text_height + 6)
        cv2.rectangle(
            annotated,
            (label_x, label_y - text_height - 6),
            (label_x + text_width + 8, label_y + baseline),
            color_bgr,
            -1,
        )
        cv2.putText(
            annotated,
            box_label,
            (label_x + 4, label_y - 3),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.62,
            (0, 0, 0),
            2,
        )

        class_counts[label] = class_counts.get(label, 0) + 1
        detections.append(
            {
                "class": label,
                "raw_class": raw_label,
                "confidence": round(confidence, 4),
                "bbox": [x1, y1, x2, y2],
                "color": color,
            }
        )

    detections.sort(key=lambda item: item["confidence"], reverse=True)
    return Image.fromarray(annotated), detections, class_counts, elapsed_ms, model_info


def save_detection_record(
    settings: AppSettings,
    recent_image_store: RecentImageStore,
    filename: str,
    original_image: Image.Image,
    preprocessed_image: Image.Image,
    annotated_image: Image.Image,
    detections: list[dict[str, Any]],
    class_counts: dict[str, int],
    inference_ms: float,
    conf_threshold: float,
    iou_threshold: float,
    model_info: dict[str, Any],
    preprocessing: dict[str, Any],
) -> dict[str, Any]:
    result_id, result_dir = create_result_dir(settings)

    artifacts = {
        "original": "original.jpg",
        "annotated": "annotated.jpg",
        "metadata": "metadata.json",
    }
    original_image.save(result_dir / artifacts["original"], format="JPEG", quality=92)
    annotated_image.save(result_dir / artifacts["annotated"], format="JPEG", quality=92)

    if preprocessing["enabled"]:
        artifacts["preprocessed"] = "preprocessed.jpg"
        preprocessed_image.save(result_dir / artifacts["preprocessed"], format="JPEG", quality=92)

    record = {
        "id": result_id,
        "task": "detect",
        "media_type": "image",
        "filename": secure_filename(filename),
        "created_at": utc_now_iso(),
        "source_layout": preprocessing["source_layout"],
        "preprocessing": preprocessing,
        "image_size": {"width": original_image.width, "height": original_image.height},
        "parameters": {
            "confidence_threshold": round(conf_threshold, 3),
            "iou_threshold": round(iou_threshold, 3),
        },
        "model": {
            "source": model_info.get("source"),
            "loaded_from": model_info.get("loaded_from"),
            "loaded_from_name": model_info.get("loaded_from_name"),
            "device": model_info.get("device"),
            "selected_key": model_info.get("selected_key"),
            "selected_name": model_info.get("selected_name"),
        },
        "summary": {
            "total_objects": len(detections),
            "inference_ms": round(inference_ms, 2),
            "class_counts": class_counts,
        },
        "detections": detections,
        "artifacts": artifacts,
    }
    write_record(result_dir, record)
    persist_recent_image(
        recent_image_store,
        record=record,
        image_role="annotated",
        filename=artifacts["annotated"],
        image=annotated_image,
    )

    # ── Persist to PostgreSQL + GCS ──────────────────────────────────────────
    gcs_urls: dict[str, str] = {}
    try:
        try:
            from cloud_storage import upload_pil_image, build_object_name, is_enabled as gcs_enabled
        except ImportError:
            from fisheye_demo.cloud_storage import upload_pil_image, build_object_name, is_enabled as gcs_enabled

        if gcs_enabled():
            obj_name = build_object_name(result_id, "annotated.jpg")
            gcs_result = upload_pil_image(annotated_image, obj_name, detection_id=result_id, image_role="annotated")
            if gcs_result:
                gcs_urls["annotated"] = gcs_result["gcs_public_url"]
                try:
                    try:
                        from db import insert_cloud_snapshot
                    except ImportError:
                        from fisheye_demo.db import insert_cloud_snapshot
                    insert_cloud_snapshot(
                        detection_id=result_id,
                        gcs_bucket=gcs_result["gcs_bucket"],
                        gcs_object_name=gcs_result["gcs_object_name"],
                        gcs_public_url=gcs_result["gcs_public_url"],
                        image_role="annotated",
                        expires_at=gcs_result["expires_at"],
                    )
                except Exception:
                    pass
    except Exception:
        pass

    try:
        try:
            from db import insert_detection, upsert_traffic_counts
        except ImportError:
            from fisheye_demo.db import insert_detection, upsert_traffic_counts
        insert_detection(record, gcs_urls=gcs_urls)
        upsert_traffic_counts(class_counts, camera_source="upload")
    except Exception:
        pass

    if gcs_urls:
        record["gcs_urls"] = gcs_urls

    return record


def save_image_conversion_record(
    settings: AppSettings,
    recent_image_store: RecentImageStore,
    filename: str,
    original_image: Image.Image,
    fisheye_image: Image.Image,
    preprocessing: dict[str, Any],
) -> dict[str, Any]:
    result_id, result_dir = create_result_dir(settings)
    artifacts = {
        "original": "original.jpg",
        "fisheye_image": "fisheye.jpg",
        "metadata": "metadata.json",
    }

    original_image.save(result_dir / artifacts["original"], format="JPEG", quality=92)
    fisheye_image.save(result_dir / artifacts["fisheye_image"], format="JPEG", quality=92)

    record = {
        "id": result_id,
        "task": "convert",
        "media_type": "image",
        "filename": secure_filename(filename),
        "created_at": utc_now_iso(),
        "source_layout": preprocessing["source_layout"],
        "preprocessing": preprocessing,
        "image_size": {"width": original_image.width, "height": original_image.height},
        "summary": {
            "output_kind": "fisheye_image",
            "width": fisheye_image.width,
            "height": fisheye_image.height,
        },
        "artifacts": artifacts,
    }
    write_record(result_dir, record)
    persist_recent_image(
        recent_image_store,
        record=record,
        image_role="fisheye_image",
        filename=artifacts["fisheye_image"],
        image=fisheye_image,
    )
    return record


def convert_video_to_fisheye(
    settings: AppSettings,
    input_path: Path,
    output_path: Path,
    preprocessing: dict[str, Any],
) -> tuple[dict[str, Any], Image.Image, Image.Image]:
    try:
        import cv2
    except Exception as exc:
        raise RuntimeError(f"OpenCV import failed: {exc}") from exc

    capture = cv2.VideoCapture(str(input_path))
    if not capture.isOpened():
        raise ValueError("Cannot open uploaded video.")

    fps = capture.get(cv2.CAP_PROP_FPS)
    fps = fps if fps and fps > 0 else 25.0
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    declared_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)

    if width <= 0 or height <= 0:
        capture.release()
        raise ValueError("Uploaded video has invalid frame size.")

    writer = cv2.VideoWriter(
        str(output_path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        (width, height),
    )
    if not writer.isOpened():
        capture.release()
        raise RuntimeError("Cannot open output video writer.")

    processed_frames = 0
    preview_original: Image.Image | None = None
    preview_fisheye: Image.Image | None = None

    try:
        while True:
            ok, frame_bgr = capture.read()
            if not ok:
                break

            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            original_image = Image.fromarray(frame_rgb)
            fisheye_image = apply_preprocessing(original_image, preprocessing).convert("RGB")

            if preview_original is None:
                preview_original = original_image.copy()
                preview_fisheye = fisheye_image.copy()

            writer.write(cv2.cvtColor(np.array(fisheye_image), cv2.COLOR_RGB2BGR))
            processed_frames += 1
    finally:
        capture.release()
        writer.release()

    if processed_frames == 0 or preview_original is None or preview_fisheye is None:
        raise ValueError("Uploaded video does not contain readable frames.")

    video_info = {
        "width": width,
        "height": height,
        "fps": round(fps, 3),
        "declared_frames": declared_frames,
        "processed_frames": processed_frames,
        "duration_seconds": round(processed_frames / fps, 3),
    }
    return video_info, preview_original, preview_fisheye


def save_video_conversion_record(
    settings: AppSettings,
    recent_image_store: RecentImageStore,
    filename: str,
    original_video_path: Path,
    fisheye_video_path: Path,
    preview_original: Image.Image,
    preview_fisheye: Image.Image,
    preprocessing: dict[str, Any],
    video_info: dict[str, Any],
) -> dict[str, Any]:
    result_id, result_dir = create_result_dir(settings)

    original_video_name = f"original{original_video_path.suffix.lower() or '.mp4'}"
    fisheye_video_name = "fisheye.mp4"
    artifacts = {
        "original_video": original_video_name,
        "fisheye_video": fisheye_video_name,
        "preview_original": "preview_original.jpg",
        "preview_fisheye": "preview_fisheye.jpg",
        "metadata": "metadata.json",
    }

    shutil.copy2(original_video_path, result_dir / artifacts["original_video"])
    shutil.copy2(fisheye_video_path, result_dir / artifacts["fisheye_video"])
    preview_original.save(result_dir / artifacts["preview_original"], format="JPEG", quality=90)
    preview_fisheye.save(result_dir / artifacts["preview_fisheye"], format="JPEG", quality=90)

    record = {
        "id": result_id,
        "task": "convert",
        "media_type": "video",
        "filename": secure_filename(filename),
        "created_at": utc_now_iso(),
        "source_layout": preprocessing["source_layout"],
        "preprocessing": preprocessing,
        "video_info": video_info,
        "summary": {
            "output_kind": "fisheye_video",
            "processed_frames": video_info["processed_frames"],
            "duration_seconds": video_info["duration_seconds"],
            "fps": video_info["fps"],
        },
        "artifacts": artifacts,
    }
    write_record(result_dir, record)
    persist_recent_image(
        recent_image_store,
        record=record,
        image_role="preview_fisheye",
        filename=artifacts["preview_fisheye"],
        image=preview_fisheye,
    )
    return record


def save_video_detection_record(
    settings: AppSettings,
    recent_image_store: RecentImageStore,
    filename: str,
    preprocessing: dict[str, Any],
    conf_threshold: float,
    iou_threshold: float,
    model_info: dict[str, Any],
    video_summary: dict[str, Any],
    result_dir: Path,
) -> dict[str, Any]:
    artifacts = {
        "annotated_video": "annotated.mp4",
        "metadata": "metadata.json",
    }

    preview_path = result_dir / "preview_annotated.jpg"
    if preview_path.exists():
        artifacts["preview_annotated"] = preview_path.name

    video_timing = {
        "video_detection_stride": video_summary.get("detection_stride"),
        "video_effective_detect_fps": video_summary.get("effective_detect_fps"),
        "video_processing_fps": video_summary.get("processing_fps"),
        "video_inference_fps": video_summary.get("inference_fps"),
    }
    if video_summary.get("target_detect_fps") is not None:
        video_timing["video_target_detect_fps"] = video_summary.get("target_detect_fps")

    record = {
        "id": result_dir.name,
        "task": "detect",
        "media_type": "video",
        "filename": secure_filename(filename),
        "created_at": utc_now_iso(),
        "source_layout": preprocessing["source_layout"],
        "preprocessing": preprocessing,
        "parameters": {
            "confidence_threshold": round(conf_threshold, 3),
            "iou_threshold": round(iou_threshold, 3),
            **{k: v for k, v in video_timing.items() if v is not None},
        },
        "model": {
            "source": model_info.get("source"),
            "loaded_from": model_info.get("loaded_from"),
            "loaded_from_name": model_info.get("loaded_from_name"),
            "device": model_info.get("device"),
            "selected_key": model_info.get("selected_key"),
            "selected_name": model_info.get("selected_name"),
        },
        "summary": video_summary,
        "artifacts": artifacts,
    }
    write_record(result_dir, record)
    if preview_path.exists():
        with Image.open(preview_path) as preview_image:
            preview_image.load()
            persist_recent_image(
                recent_image_store,
                record=record,
                image_role="preview_annotated",
                filename=artifacts["preview_annotated"],
                image=preview_image.convert("RGB"),
            )

    # ── Persist video detection to DB + GCS ──────────────────────────────────
    gcs_urls: dict[str, str] = {}
    try:
        try:
            from cloud_storage import upload_pil_image, build_object_name, is_enabled as gcs_enabled
        except ImportError:
            from fisheye_demo.cloud_storage import upload_pil_image, build_object_name, is_enabled as gcs_enabled

        if gcs_enabled() and preview_path.exists():
            with Image.open(preview_path) as _prev:
                _prev.load()
                obj_name = build_object_name(record["id"], "preview_annotated.jpg")
                gcs_result = upload_pil_image(_prev.convert("RGB"), obj_name,
                                              detection_id=record["id"], image_role="preview_annotated")
                if gcs_result:
                    gcs_urls["preview_annotated"] = gcs_result["gcs_public_url"]
                    try:
                        try:
                            from db import insert_cloud_snapshot
                        except ImportError:
                            from fisheye_demo.db import insert_cloud_snapshot
                        insert_cloud_snapshot(
                            detection_id=record["id"],
                            gcs_bucket=gcs_result["gcs_bucket"],
                            gcs_object_name=gcs_result["gcs_object_name"],
                            gcs_public_url=gcs_result["gcs_public_url"],
                            image_role="preview_annotated",
                            expires_at=gcs_result["expires_at"],
                        )
                    except Exception:
                        pass
    except Exception:
        pass

    try:
        try:
            from db import insert_detection, upsert_traffic_counts
        except ImportError:
            from fisheye_demo.db import insert_detection, upsert_traffic_counts
        insert_detection(record, gcs_urls=gcs_urls)
        class_counts = video_summary.get("class_counts") or {}
        upsert_traffic_counts(class_counts, camera_source="video_upload")
    except Exception:
        pass

    if gcs_urls:
        record["gcs_urls"] = gcs_urls

    return record


def save_external_camera_record(
    settings: AppSettings,
    recent_image_store: RecentImageStore,
    source_url: str,
    preprocessing: dict[str, Any],
    conf_threshold: float,
    iou_threshold: float,
    model_info: dict[str, Any],
    cameras: list[dict[str, Any]],
    average_inference_ms: float,
    result_dir: Path,
    overview_image: Image.Image,
) -> dict[str, Any]:
    artifacts = {
        "overview_annotated": "overview_annotated.jpg",
        "metadata": "metadata.json",
    }

    class_totals: dict[str, int] = {}
    for index, camera in enumerate(cameras, start=1):
        artifacts[f"camera_{index}_original"] = f"camera_{index}_original.jpg"
        artifacts[f"camera_{index}_annotated"] = f"camera_{index}_annotated.jpg"
        if camera["preprocessing_enabled"]:
            artifacts[f"camera_{index}_preprocessed"] = f"camera_{index}_preprocessed.jpg"

        for class_name, count in camera["class_counts"].items():
            class_totals[class_name] = class_totals.get(class_name, 0) + count

    record = {
        "id": result_dir.name,
        "task": "detect",
        "media_type": "external_camera_grid",
        "filename": source_url,
        "created_at": utc_now_iso(),
        "source_layout": preprocessing["source_layout"],
        "preprocessing": preprocessing,
        "parameters": {
            "confidence_threshold": round(conf_threshold, 3),
            "iou_threshold": round(iou_threshold, 3),
        },
        "model": {
            "source": model_info.get("source"),
            "loaded_from": model_info.get("loaded_from"),
            "loaded_from_name": model_info.get("loaded_from_name"),
            "device": model_info.get("device"),
            "selected_key": model_info.get("selected_key"),
            "selected_name": model_info.get("selected_name"),
        },
        "summary": {
            "camera_count": len(cameras),
            "total_objects": sum(camera["total_objects"] for camera in cameras),
            "class_counts": class_totals,
            "inference_ms": round(average_inference_ms, 2),
        },
        "cameras": [
            {
                "index": camera["index"],
                "title": camera["title"],
                "youtube_id": camera["youtube_id"],
                "snapshot_url": camera["snapshot_url"],
                "stream_url": camera.get("stream_url"),
                "total_objects": camera["total_objects"],
                "class_counts": camera["class_counts"],
                "detections": camera["detections"],
            }
            for camera in cameras
        ],
        "artifacts": artifacts,
    }
    write_record(result_dir, record)
    persist_recent_image(
        recent_image_store,
        record=record,
        image_role="overview_annotated",
        filename=artifacts["overview_annotated"],
        image=overview_image,
    )

    # ── Persist external camera detection to DB + GCS ─────────────────────────
    gcs_urls: dict[str, str] = {}
    try:
        try:
            from cloud_storage import upload_pil_image, build_object_name, is_enabled as gcs_enabled
        except ImportError:
            from fisheye_demo.cloud_storage import upload_pil_image, build_object_name, is_enabled as gcs_enabled

        if gcs_enabled():
            obj_name = build_object_name(record["id"], "overview_annotated.jpg")
            gcs_result = upload_pil_image(overview_image, obj_name,
                                          detection_id=record["id"], image_role="overview_annotated")
            if gcs_result:
                gcs_urls["overview_annotated"] = gcs_result["gcs_public_url"]
                try:
                    try:
                        from db import insert_cloud_snapshot
                    except ImportError:
                        from fisheye_demo.db import insert_cloud_snapshot
                    insert_cloud_snapshot(
                        detection_id=record["id"],
                        gcs_bucket=gcs_result["gcs_bucket"],
                        gcs_object_name=gcs_result["gcs_object_name"],
                        gcs_public_url=gcs_result["gcs_public_url"],
                        image_role="overview_annotated",
                        expires_at=gcs_result["expires_at"],
                    )
                except Exception:
                    pass
    except Exception:
        pass

    try:
        try:
            from db import insert_detection, upsert_traffic_counts
        except ImportError:
            from fisheye_demo.db import insert_detection, upsert_traffic_counts
        insert_detection(record, gcs_urls=gcs_urls)
        class_totals_for_db = record.get("summary", {}).get("class_counts") or {}
        upsert_traffic_counts(class_totals_for_db, camera_source="external_camera")
    except Exception:
        pass

    if gcs_urls:
        record["gcs_urls"] = gcs_urls

    return record


def process_external_camera_frames(
    registry: ModelRegistry,
    settings: AppSettings,
    recent_image_store: RecentImageStore,
    source_label: str,
    camera_inputs: list[dict[str, Any]],
    preprocessing: dict[str, Any],
    conf_threshold: float,
    iou_threshold: float,
    model_key: str | None,
    persist_result: bool,
) -> dict[str, Any]:
    result_dir: Path | None = None

    try:
        if persist_result:
            _, result_dir = create_result_dir(settings)

        cameras: list[dict[str, Any]] = []
        model_info: dict[str, Any] = {}
        inference_times: list[float] = []

        for index, camera_input in enumerate(camera_inputs, start=1):
            original_image = camera_input["original_image"].convert("RGB")
            preprocessed_image = apply_preprocessing(original_image, preprocessing)
            annotated_image, detections, class_counts, inference_ms, loaded_model_info = run_inference(
                registry,
                settings,
                preprocessed_image,
                conf_threshold,
                iou_threshold,
                model_key=model_key,
            )
            model_info = loaded_model_info
            inference_times.append(inference_ms)

            if result_dir is not None:
                original_name = f"camera_{index}_original.jpg"
                annotated_name = f"camera_{index}_annotated.jpg"
                original_image.save(result_dir / original_name, format="JPEG", quality=90)
                annotated_image.save(result_dir / annotated_name, format="JPEG", quality=90)
                if preprocessing["enabled"]:
                    preprocessed_name = f"camera_{index}_preprocessed.jpg"
                    preprocessed_image.save(result_dir / preprocessed_name, format="JPEG", quality=90)

            cameras.append(
                {
                    "index": index,
                    "title": str(camera_input.get("title") or f"Camera {index}"),
                    "youtube_id": str(camera_input.get("youtube_id") or ""),
                    "snapshot_url": str(camera_input.get("snapshot_url") or ""),
                    "stream_url": str(camera_input.get("stream_url") or ""),
                    "original_image": original_image,
                    "preprocessed_image": preprocessed_image,
                    "annotated_image": annotated_image,
                    "preprocessing_enabled": preprocessing["enabled"],
                    "detections": detections,
                    "class_counts": class_counts,
                    "total_objects": len(detections),
                }
            )

        overview_image = cameras[0]["annotated_image"].copy() if len(cameras) == 1 else build_camera_collage(cameras)
        average_inference_ms = sum(inference_times) / len(inference_times) if inference_times else 0.0
        summary = build_external_camera_summary(cameras, average_inference_ms)

        record = None
        if result_dir is not None:
            overview_image.save(result_dir / "overview_annotated.jpg", format="JPEG", quality=90)
            record = save_external_camera_record(
                settings,
                recent_image_store,
                source_label,
                preprocessing,
                conf_threshold,
                iou_threshold,
                model_info,
                cameras,
                average_inference_ms,
                result_dir,
                overview_image,
            )
            record["artifact_urls"] = build_artifact_urls(record)

        return {
            "source_url": source_label,
            "camera_count": len(cameras),
            "overview": pil_to_b64(overview_image),
            "summary": record["summary"] if record else summary,
            "preprocessing": preprocessing,
            "model": {
                "source": model_info.get("source"),
                "loaded_from": model_info.get("loaded_from"),
                "loaded_from_name": model_info.get("loaded_from_name"),
                "device": model_info.get("device"),
                "selected_key": model_info.get("selected_key"),
                "selected_name": model_info.get("selected_name"),
            },
            "cameras": [
                {
                    "index": camera["index"],
                    "title": camera["title"],
                    "youtube_id": camera["youtube_id"],
                    "snapshot_url": camera["snapshot_url"],
                    "stream_url": camera["stream_url"],
                    "total_objects": camera["total_objects"],
                    "class_counts": camera["class_counts"],
                    "detections": camera["detections"],
                    "annotated": pil_to_b64(camera["annotated_image"]),
                }
                for camera in cameras
            ],
            "stream_frames": {
                "overview": pil_to_jpeg_bytes(overview_image),
                **{
                    f"camera_{camera['index']}": pil_to_jpeg_bytes(camera["annotated_image"])
                    for camera in cameras
                },
            },
            "record": record,
        }
    except Exception:
        if result_dir and result_dir.exists():
            shutil.rmtree(result_dir, ignore_errors=True)
        raise


def build_external_camera_summary(cameras: list[dict[str, Any]], average_inference_ms: float) -> dict[str, Any]:
    class_totals = {class_name: 0 for class_name in CLASS_NAMES}
    for camera in cameras:
        for class_name, count in camera["class_counts"].items():
            class_totals[class_name] = class_totals.get(class_name, 0) + count

    return {
        "camera_count": len(cameras),
        "total_objects": sum(camera["total_objects"] for camera in cameras),
        "class_counts": class_totals,
        "inference_ms": round(average_inference_ms, 2),
    }


def run_external_camera_pipeline(
    registry: ModelRegistry,
    settings: AppSettings,
    recent_image_store: RecentImageStore,
    source_mode: str,
    source_url: str,
    stream_url: str,
    camera_limit: int,
    preprocessing: dict[str, Any],
    conf_threshold: float,
    iou_threshold: float,
    model_key: str | None,
    persist_result: bool,
) -> dict[str, Any]:
    normalized_mode = normalize_external_camera_source_mode(source_mode, stream_url or source_url)
    if normalized_mode == "stream":
        active_stream_url = stream_url or source_url
        if not active_stream_url:
            raise ValueError("No camera stream URL configured.")
        camera_inputs = [
            {
                "title": "Stream camera 1",
                "youtube_id": "",
                "snapshot_url": "",
                "stream_url": active_stream_url,
                "original_image": capture_stream_frame(active_stream_url),
            }
        ]
        return process_external_camera_frames(
            registry,
            settings,
            recent_image_store,
            active_stream_url,
            camera_inputs,
            preprocessing,
            conf_threshold,
            iou_threshold,
            model_key,
            persist_result,
        )

    entries = extract_camera_entries(source_url, limit=camera_limit)
    if not entries:
        raise ValueError("No camera entries found from the external source.")

    camera_inputs = [
        {
            "title": entry.title,
            "youtube_id": entry.youtube_id,
            "snapshot_url": entry.snapshot_url,
            "stream_url": "",
            "original_image": download_camera_snapshot(entry),
        }
        for entry in entries
    ]
    return process_external_camera_frames(
        registry,
        settings,
        recent_image_store,
        source_url,
        camera_inputs,
        preprocessing,
        conf_threshold,
        iou_threshold,
        model_key,
        persist_result,
    )


def read_stream_frame_from_capture(capture) -> Image.Image:
    try:
        import cv2
    except Exception as exc:
        raise RuntimeError(f"OpenCV import failed while reading stream: {exc}") from exc

    ok, frame = capture.read()
    if not ok or frame is None:
        raise RuntimeError("Unable to read frame from live stream.")
    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    image = Image.fromarray(frame_rgb, mode="RGB")
    image.load()
    return image


class ExternalCameraLiveMonitor:
    def __init__(
        self,
        settings: AppSettings,
        registry: ModelRegistry,
        recent_image_store: RecentImageStore,
    ) -> None:
        self.settings = settings
        self.registry = registry
        self.recent_image_store = recent_image_store
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._stream_frames: dict[str, bytes] = {}
        self._stream_frame_id = 0
        self._session_id: str | None = None
        self._state: dict[str, Any] = {
            "running": False,
            "status": "idle",
            "source_mode": settings.external_camera_source_mode,
            "source_url": settings.external_camera_url,
            "stream_url": settings.external_camera_stream_url,
            "camera_limit": settings.external_camera_limit,
            "interval_seconds": settings.external_camera_live_interval_seconds,
            "conf_threshold": settings.default_conf,
            "iou_threshold": settings.default_iou,
            "model_key": registry.status_snapshot().get("selected_key"),
            "preprocessing": {
                "source_layout": "normal",
                "enabled": True,
                "strength": settings.camera_fisheye_strength,
                "radius": settings.camera_fisheye_radius,
                "effect": settings.camera_fisheye_effect,
                "center_x_ratio": settings.camera_fisheye_center_x,
                "center_y_ratio": settings.camera_fisheye_center_y,
                "axis_scale_x": settings.camera_fisheye_axis_scale_x,
                "axis_scale_y": settings.camera_fisheye_axis_scale_y,
                "full_frame": settings.camera_fisheye_full_frame,
                "profile": "external_camera",
            },
            "started_at": None,
            "last_updated_at": None,
            "error": None,
            "cycle_count": 0,
            "last_cycle_duration_ms": None,
            "actual_cycle_fps": None,
            "stream_ready": False,
            "last_result": None,
        }

    def status_snapshot(self) -> dict[str, Any]:
        with self._lock:
            return json.loads(json.dumps(self._state))

    def get_stream_frame_snapshot(self, view: str) -> tuple[int, bytes | None, bool]:
        with self._lock:
            return self._stream_frame_id, self._stream_frames.get(view), bool(self._state.get("running"))

    def start(
        self,
        source_mode: str,
        source_url: str,
        stream_url: str,
        camera_limit: int,
        preprocessing: dict[str, Any],
        conf_threshold: float,
        iou_threshold: float,
        model_key: str | None,
        interval_seconds: float,
    ) -> dict[str, Any]:
        with self._lock:
            already_running = self._thread is not None and self._thread.is_alive()
            if already_running:
                logger.info(
                    "Live monitor start ignored because worker is already running: source=%s cycle_count=%s status=%s",
                    self._state.get("source_url"),
                    self._state.get("cycle_count"),
                    self._state.get("status"),
                )
                return json.loads(json.dumps(self._state))

            self._stop_event.clear()
            self._state.update(
                {
                    "source_mode": source_mode,
                    "source_url": source_url,
                    "stream_url": stream_url,
                    "camera_limit": camera_limit,
                    "interval_seconds": interval_seconds,
                    "conf_threshold": round(conf_threshold, 3),
                    "iou_threshold": round(iou_threshold, 3),
                    "model_key": model_key,
                    "preprocessing": dict(preprocessing),
                    "error": None,
                    "status": "starting",
                    "running": True,
                    "started_at": utc_now_iso_ms(),
                    "last_updated_at": None,
                    "cycle_count": 0,
                    "last_cycle_duration_ms": None,
                    "actual_cycle_fps": None,
                    "stream_ready": False,
                    "last_result": None,
                }
            )
            self._stream_frames = {}
            self._stream_frame_id = 0
            self._session_id = uuid.uuid4().hex
            worker = threading.Thread(
                target=self._worker_loop,
                kwargs={
                    "source_mode": source_mode,
                    "source_url": source_url,
                    "stream_url": stream_url,
                    "camera_limit": camera_limit,
                    "preprocessing": dict(preprocessing),
                    "conf_threshold": conf_threshold,
                    "iou_threshold": iou_threshold,
                    "model_key": model_key,
                    "interval_seconds": interval_seconds,
                },
                daemon=True,
                name="external-camera-live-monitor",
            )
            self._thread = worker
            logger.info(
                "Live monitor start requested: source=%s camera_limit=%s interval=%.3fs conf=%.2f iou=%.2f fisheye=%s effect=%s center=(%.2f, %.2f) axis=(%.2f, %.2f) full_frame=%s",
                source_url,
                camera_limit,
                interval_seconds,
                conf_threshold,
                iou_threshold,
                preprocessing.get("enabled"),
                preprocessing.get("effect"),
                preprocessing.get("center_x_ratio", 0.5),
                preprocessing.get("center_y_ratio", 0.5),
                preprocessing.get("axis_scale_x", 1.0),
                preprocessing.get("axis_scale_y", 1.0),
                preprocessing.get("full_frame"),
            )
            worker.start()

            # Tạo live session record trong DB
            try:
                try:
                    from db import insert_live_session
                except ImportError:
                    from fisheye_demo.db import insert_live_session
                insert_live_session(self._session_id, source_url, source_mode, conf_threshold, iou_threshold)
            except Exception:
                pass

            return json.loads(json.dumps(self._state))

    def stop(self) -> dict[str, Any]:
        thread = None
        with self._lock:
            thread = self._thread
            self._stop_event.set()
            self._state["status"] = "stopping" if thread and thread.is_alive() else "stopped"
            logger.info(
                "Live monitor stop requested: cycle_count=%s last_cycle_ms=%s stream_ready=%s status=%s",
                self._state.get("cycle_count"),
                self._state.get("last_cycle_duration_ms"),
                self._state.get("stream_ready"),
                self._state.get("status"),
            )

        if thread and thread.is_alive():
            thread.join(timeout=5)

        with self._lock:
            self._thread = None
            self._state["running"] = False
            self._state["status"] = "stopped"
            logger.info(
                "Live monitor stopped: cycle_count=%s last_updated_at=%s error=%s",
                self._state.get("cycle_count"),
                self._state.get("last_updated_at"),
                self._state.get("error"),
            )
            session_id_to_close = self._session_id
            self._session_id = None

        # Đóng live session trong DB ngoài lock để tránh deadlock
        if session_id_to_close:
            try:
                try:
                    from db import close_live_session
                except ImportError:
                    from fisheye_demo.db import close_live_session
                close_live_session(session_id_to_close)
            except Exception:
                pass

        with self._lock:
            return json.loads(json.dumps(self._state))

    def _worker_loop(
        self,
        *,
        source_mode: str,
        source_url: str,
        stream_url: str,
        camera_limit: int,
        preprocessing: dict[str, Any],
        conf_threshold: float,
        iou_threshold: float,
        model_key: str | None,
        interval_seconds: float,
    ) -> None:
        try:
            if normalize_external_camera_source_mode(source_mode, stream_url or source_url) == "stream":
                self._worker_loop_stream(
                    stream_url=stream_url or source_url,
                    preprocessing=preprocessing,
                    conf_threshold=conf_threshold,
                    iou_threshold=iou_threshold,
                    model_key=model_key,
                    interval_seconds=interval_seconds,
                )
            else:
                self._worker_loop_snapshot(
                    source_url=source_url,
                    camera_limit=camera_limit,
                    preprocessing=preprocessing,
                    conf_threshold=conf_threshold,
                    iou_threshold=iou_threshold,
                    model_key=model_key,
                    interval_seconds=interval_seconds,
                )
        finally:
            with self._lock:
                self._thread = None
                self._state["running"] = False
                if self._state.get("status") != "stopped":
                    self._state["status"] = "stopped" if self._stop_event.is_set() else "idle"
                logger.info(
                    "Live worker exit: status=%s cycle_count=%s stream_ready=%s error=%s",
                    self._state.get("status"),
                    self._state.get("cycle_count"),
                    self._state.get("stream_ready"),
                    self._state.get("error"),
                )

    def _worker_loop_snapshot(
        self,
        *,
        source_url: str,
        camera_limit: int,
        preprocessing: dict[str, Any],
        conf_threshold: float,
        iou_threshold: float,
        model_key: str | None,
        interval_seconds: float,
    ) -> None:
        while not self._stop_event.is_set():
            cycle_started_at = time.perf_counter()
            try:
                payload = run_external_camera_pipeline(
                    self.registry,
                    self.settings,
                    self.recent_image_store,
                    "snapshot",
                    source_url,
                    "",
                    camera_limit,
                    preprocessing,
                    conf_threshold,
                    iou_threshold,
                    model_key,
                    persist_result=False,
                )
                self._publish_live_payload(payload, cycle_started_at)
            except Exception as exc:
                logger.exception("Live cycle failed: source=%s", source_url)
                with self._lock:
                    self._state.update(
                        {
                            "running": True,
                            "status": "error",
                            "error": str(exc),
                            "last_updated_at": utc_now_iso_ms(),
                        }
                    )

            if self._stop_event.wait(interval_seconds):
                break

    def _worker_loop_stream(
        self,
        *,
        stream_url: str,
        preprocessing: dict[str, Any],
        conf_threshold: float,
        iou_threshold: float,
        model_key: str | None,
        interval_seconds: float,
    ) -> None:
        try:
            import cv2
        except Exception as exc:
            raise RuntimeError(f"OpenCV import failed while opening live stream: {exc}") from exc

        capture = cv2.VideoCapture(stream_url)
        if not capture.isOpened():
            capture.release()
            raise RuntimeError(f"Unable to open live stream source: {stream_url}")

        try:
            while not self._stop_event.is_set():
                cycle_started_at = time.perf_counter()
                try:
                    original_image = read_stream_frame_from_capture(capture)
                    payload = process_external_camera_frames(
                        self.registry,
                        self.settings,
                        self.recent_image_store,
                        stream_url,
                        [
                            {
                                "title": "Stream camera 1",
                                "youtube_id": "",
                                "snapshot_url": "",
                                "stream_url": stream_url,
                                "original_image": original_image,
                            }
                        ],
                        preprocessing,
                        conf_threshold,
                        iou_threshold,
                        model_key,
                        persist_result=False,
                    )
                    self._publish_live_payload(payload, cycle_started_at)
                except Exception as exc:
                    logger.exception("Live stream cycle failed: stream=%s", stream_url)
                    with self._lock:
                        self._state.update(
                            {
                                "running": True,
                                "status": "error",
                                "error": str(exc),
                                "last_updated_at": utc_now_iso_ms(),
                            }
                        )
                if self._stop_event.wait(interval_seconds):
                    break
        finally:
            capture.release()

    def _publish_live_payload(self, payload: dict[str, Any], cycle_started_at: float) -> None:
        cycle_elapsed_seconds = time.perf_counter() - cycle_started_at
        cycle_elapsed_ms = round(cycle_elapsed_seconds * 1000, 1)
        actual_cycle_fps = round(1.0 / cycle_elapsed_seconds, 2) if cycle_elapsed_seconds > 0 else None
        summary = payload.get("summary") or {}
        next_cycle_count = 1
        with self._lock:
            self._stream_frames = dict(payload.get("stream_frames") or {})
            self._stream_frame_id += 1
            next_cycle_count = int(self._state.get("cycle_count", 0)) + 1
            self._state.update(
                {
                    "running": True,
                    "status": "active",
                    "error": None,
                    "last_updated_at": utc_now_iso_ms(),
                    "cycle_count": next_cycle_count,
                    "last_cycle_duration_ms": cycle_elapsed_ms,
                    "actual_cycle_fps": actual_cycle_fps,
                    "stream_ready": True,
                    "last_result": {
                        "task": "detect",
                        "media_type": "external_camera_grid_live",
                        "source_url": payload["source_url"],
                        "camera_count": payload["camera_count"],
                        "overview": payload["overview"],
                        "summary": payload["summary"],
                        "preprocessing": payload["preprocessing"],
                        "model": payload["model"],
                        "cameras": payload["cameras"],
                    },
                }
            )

        # ── Cập nhật analytics + DB từ live cycle ────────────────────────────
        total_objects = summary.get("total_objects", 0)
        class_counts = summary.get("class_counts") or {}
        try:
            try:
                from db import upsert_traffic_counts, update_live_session
            except ImportError:
                from fisheye_demo.db import upsert_traffic_counts, update_live_session
            upsert_traffic_counts(class_counts, camera_source="live_camera")
            if self._session_id:
                update_live_session(
                    self._session_id,
                    cycle_count=next_cycle_count,
                    total_objects=total_objects,
                    class_counts=class_counts,
                    status="active",
                )
        except Exception:
            pass

        # Upload overview frame lên GCS mỗi 10 cycle
        if next_cycle_count % 10 == 0:
            try:
                try:
                    from cloud_storage import upload_image_bytes, build_object_name, is_enabled as gcs_enabled
                except ImportError:
                    from fisheye_demo.cloud_storage import upload_image_bytes, build_object_name, is_enabled as gcs_enabled

                if gcs_enabled():
                    overview_bytes = payload.get("stream_frames", {}).get("overview")
                    if overview_bytes:
                        ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
                        obj_name = build_object_name(f"live_{ts}", "overview_annotated.jpg")
                        gcs_result = upload_image_bytes(
                            overview_bytes, obj_name,
                            detection_id=None, image_role="live_overview",
                        )
                        if gcs_result:
                            try:
                                try:
                                    from db import insert_cloud_snapshot
                                except ImportError:
                                    from fisheye_demo.db import insert_cloud_snapshot
                                insert_cloud_snapshot(
                                    detection_id=None,
                                    gcs_bucket=gcs_result["gcs_bucket"],
                                    gcs_object_name=gcs_result["gcs_object_name"],
                                    gcs_public_url=gcs_result["gcs_public_url"],
                                    image_role="live_overview",
                                    expires_at=gcs_result["expires_at"],
                                )
                            except Exception:
                                pass
            except Exception:
                pass

        logger.info(
            "Live cycle complete: cycle=%s duration_ms=%s actual_fps=%s camera_count=%s total_objects=%s stream_views=%s",
            next_cycle_count,
            cycle_elapsed_ms,
            actual_cycle_fps,
            summary.get("camera_count"),
            summary.get("total_objects"),
            ",".join(sorted(self._stream_frames.keys())) or "none",
        )


def create_app(config_overrides: dict[str, Any] | None = None) -> Flask:
    config_overrides = config_overrides or {}
    settings = build_settings(config_overrides.get("SETTINGS_OVERRIDES"))
    registry = ModelRegistry(settings)
    recent_image_store = RecentImageStore(settings.recent_image_db_path, settings.recent_image_limit)
    backfill_recent_image_store(settings, recent_image_store)
    live_monitor = ExternalCameraLiveMonitor(settings, registry, recent_image_store)

    try:
        from job_queue import VideoJobQueue
    except ImportError:
        from fisheye_demo.job_queue import VideoJobQueue

    _max_video_workers = int(os.getenv("FISHEYE_VIDEO_WORKERS", "2"))
    _max_video_queue = int(os.getenv("FISHEYE_VIDEO_QUEUE_SIZE", "10"))
    job_queue = VideoJobQueue(max_workers=_max_video_workers, max_queue_size=_max_video_queue)

    # ── Extended modules (DB, GCS, Analytics, Alerts) ────────────────────────
    try:
        try:
            from db import init_db
            from analytics import DetectionHeatmap, TrafficDensityAnalyzer
            from alert_manager import get_alert_manager
            from cloud_storage import start_cleanup_scheduler
            from routes_extended import register_extended_routes
        except ImportError:
            from fisheye_demo.db import init_db
            from fisheye_demo.analytics import DetectionHeatmap, TrafficDensityAnalyzer
            from fisheye_demo.alert_manager import get_alert_manager
            from fisheye_demo.cloud_storage import start_cleanup_scheduler
            from fisheye_demo.routes_extended import register_extended_routes

        _db_backend = init_db()
        logger.info("DB initialized: backend=%s", _db_backend)

        _heatmap = DetectionHeatmap(grid_w=64, grid_h=64)
        _density_analyzer = TrafficDensityAnalyzer(
            window_size=30,
            alert_threshold=int(os.getenv("ALERT_THRESHOLD_TOTAL", "15")),
        )
        _alert_manager = get_alert_manager()

        # Đăng ký alert callback: khi density cao thì lưu DB
        def _on_density_alert(total_objects, class_counts, avg_total):
            try:
                try:
                    from db import insert_alert
                except ImportError:
                    from fisheye_demo.db import insert_alert
                insert_alert(
                    alert_type="high_density",
                    message=f"Mật độ cao: {total_objects} đối tượng (avg={avg_total:.1f})",
                    camera_source="live",
                    actual_count=total_objects,
                )
            except Exception:
                pass

        _density_analyzer.add_alert_callback(_on_density_alert)

        # Line counter mặc định (đường ngang giữa ảnh)
        try:
            try:
                from analytics import LineCrossingCounter
            except ImportError:
                from fisheye_demo.analytics import LineCrossingCounter
            _line_counter = LineCrossingCounter(
                line_start=(0.0, 0.5),
                line_end=(1.0, 0.5),
                name="default_line",
            )
        except Exception:
            _line_counter = None

        # Khởi động GCS cleanup scheduler
        start_cleanup_scheduler(interval_minutes=30)

        _extended_enabled = True
    except Exception as _ext_exc:
        logger.warning("Extended modules init failed (running without DB/GCS/Analytics): %s", _ext_exc)
        _extended_enabled = False
        _heatmap = None
        _density_analyzer = None
        _alert_manager = None
        _line_counter = None

    # ── Incident Detector ─────────────────────────────────────────────────────
    try:
        try:
            from incident_detector import Incident_Detector as _IncidentDetectorClass
        except ImportError:
            from fisheye_demo.incident_detector import Incident_Detector as _IncidentDetectorClass
        _incident_detector_available = True
    except Exception:
        _IncidentDetectorClass = None  # type: ignore[assignment, misc]
        _incident_detector_available = False

    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = settings.max_upload_mb * 1024 * 1024
    app.config.update(config_overrides)
    app.extensions["fisheye_settings"] = settings
    app.extensions["fisheye_model_registry"] = registry
    app.extensions["fisheye_recent_image_store"] = recent_image_store
    app.extensions["fisheye_live_monitor"] = live_monitor
    app.extensions["fisheye_extended_enabled"] = _extended_enabled
    app.extensions["fisheye_heatmap"] = _heatmap
    app.extensions["fisheye_density_analyzer"] = _density_analyzer
    app.extensions["fisheye_alert_manager"] = _alert_manager
    app.extensions["fisheye_line_counter"] = _line_counter
    app.extensions["fisheye_job_queue"] = job_queue

    @app.get("/")
    def index():
        selectable_models = registry.list_selectable_models()
        return render_template(
            "index.html",
            class_names=CLASS_NAMES,
            class_colors=CLASS_COLORS,
            default_conf=settings.default_conf,
            default_iou=settings.default_iou,
            default_fisheye_strength=settings.default_fisheye_strength,
            default_fisheye_radius=settings.default_fisheye_radius,
            default_fisheye_effect=settings.default_fisheye_effect,
            fisheye_effect_choices=[(key, EFFECT_LABELS_VI.get(key, key)) for key in EFFECT_MAP.keys()],
            selectable_models=selectable_models,
            default_model_key=(selectable_models[0]["key"] if selectable_models else ""),
            external_camera_url=(
                settings.external_camera_stream_url
                if settings.external_camera_source_mode == "stream" and settings.external_camera_stream_url
                else settings.external_camera_url
            ),
            external_camera_source_mode=settings.external_camera_source_mode,
            external_camera_live_interval_seconds=settings.external_camera_live_interval_seconds,
            max_upload_mb=settings.max_upload_mb,
        )

    @app.get("/api/config")
    def api_config():
        return jsonify(
            {
                "classes": CLASS_NAMES,
                "class_colors": CLASS_COLORS,
                "defaults": {
                    "confidence_threshold": settings.default_conf,
                    "iou_threshold": settings.default_iou,
                    "fisheye_strength": settings.default_fisheye_strength,
                    "fisheye_radius": settings.default_fisheye_radius,
                    "fisheye_effect": settings.default_fisheye_effect,
                    "camera_fisheye_strength": settings.camera_fisheye_strength,
                    "camera_fisheye_radius": settings.camera_fisheye_radius,
                    "camera_fisheye_effect": settings.camera_fisheye_effect,
                    "camera_fisheye_center_x": settings.camera_fisheye_center_x,
                    "camera_fisheye_center_y": settings.camera_fisheye_center_y,
                    "camera_fisheye_axis_scale_x": settings.camera_fisheye_axis_scale_x,
                    "camera_fisheye_axis_scale_y": settings.camera_fisheye_axis_scale_y,
                    "camera_fisheye_full_frame": settings.camera_fisheye_full_frame,
                },
                "limits": {
                    "max_upload_mb": settings.max_upload_mb,
                    "history_limit": settings.history_limit,
                    "recent_image_limit": settings.recent_image_limit,
                    "max_video_seconds": settings.max_video_seconds,
                    "external_camera_live_interval_seconds": settings.external_camera_live_interval_seconds,
                },
                "fisheye": {
                    "effects": list(EFFECT_MAP.keys()),
                    "effect_labels_vi": dict(EFFECT_LABELS_VI),
                    "source_layouts": list(SUPPORTED_SOURCE_LAYOUTS),
                },
                "media_support": {
                    "images": sorted(ALLOWED_IMAGE_EXTENSIONS),
                    "videos": sorted(ALLOWED_VIDEO_EXTENSIONS),
                },
                "models": {
                    "selectable": registry.list_selectable_models(),
                    "default_key": (registry.get_model_entry(None) or {}).get("key"),
                },
                "external_camera": {
                    "source_mode": settings.external_camera_source_mode,
                    "source_url": settings.external_camera_url,
                    "stream_url": settings.external_camera_stream_url,
                    "supported_source_modes": list(SUPPORTED_EXTERNAL_CAMERA_SOURCE_MODES),
                },
                "external_camera_url": settings.external_camera_url,
                "external_camera_limit": settings.external_camera_limit,
                "external_camera_live_interval_seconds": settings.external_camera_live_interval_seconds,
                "recent_image_store": recent_image_store.stats(),
            }
        )

    @app.get("/api/health")
    def api_health():
        history_items = list_records(settings.results_dir, settings.history_limit)

        # ── DB health ─────────────────────────────────────────────────────────
        db_status: dict[str, Any] = {"status": "disabled"}
        if app.extensions.get("fisheye_extended_enabled"):
            try:
                try:
                    from db import get_dashboard_stats
                except ImportError:
                    from fisheye_demo.db import get_dashboard_stats
                get_dashboard_stats(hours=1)
                db_status = {"status": "ok"}
            except Exception as _db_exc:
                db_status = {"status": "error", "detail": str(_db_exc)[:120]}

        # ── GCS health ────────────────────────────────────────────────────────
        gcs_status: dict[str, Any] = {"status": "disabled"}
        if app.extensions.get("fisheye_extended_enabled"):
            try:
                try:
                    from cloud_storage import is_enabled as _gcs_is_enabled, get_bucket_stats as _gcs_bucket_stats
                except ImportError:
                    from fisheye_demo.cloud_storage import is_enabled as _gcs_is_enabled, get_bucket_stats as _gcs_bucket_stats
                if _gcs_is_enabled():
                    _stats = _gcs_bucket_stats()
                    gcs_status = {"status": "ok", "object_count": _stats.get("object_count", 0)}
                else:
                    gcs_status = {"status": "not_configured"}
            except Exception as _gcs_exc:
                gcs_status = {"status": "error", "detail": str(_gcs_exc)[:120]}

        # ── Disk health ───────────────────────────────────────────────────────
        upload_dir = Path(settings.upload_dir)
        results_dir = Path(settings.results_dir)
        disk_status: dict[str, Any] = {
            "upload_dir_exists": upload_dir.is_dir(),
            "results_dir_exists": results_dir.is_dir(),
        }
        try:
            _st = shutil.disk_usage(str(results_dir if results_dir.is_dir() else Path(".")))
            disk_status["free_gb"] = round(_st.free / 1e9, 2)
            disk_status["total_gb"] = round(_st.total / 1e9, 2)
            disk_status["used_pct"] = round((_st.used / _st.total) * 100, 1)
        except Exception:
            pass

        # ── Job queue health ──────────────────────────────────────────────────
        _jq: VideoJobQueue = app.extensions["fisheye_job_queue"]
        job_stats = _jq.stats()

        overall = "ok"
        if db_status.get("status") == "error" or gcs_status.get("status") == "error":
            overall = "degraded"

        return jsonify(
            {
                "status": overall,
                "server_time": utc_now_iso(),
                "model": registry.status_snapshot(),
                "storage": {
                    "upload_dir": str(settings.upload_dir),
                    "results_dir": str(settings.results_dir),
                    "recent_runs": len(history_items),
                    "disk": disk_status,
                },
                "db": db_status,
                "gcs": gcs_status,
                "job_queue": job_stats,
                "recent_image_store": recent_image_store.stats(),
                "device": settings.device,
                "incident_detector": {"available": _incident_detector_available},
            }
        )

    @app.get("/api/classes")
    def api_classes():
        return jsonify({"classes": CLASS_NAMES, "class_colors": CLASS_COLORS})

    @app.get("/api/history")
    def api_history():
        requested_limit = request.args.get("limit", settings.history_limit)
        try:
            limit = max(1, min(50, int(requested_limit)))
        except ValueError:
            limit = settings.history_limit

        items = list_records(settings.results_dir, limit)
        for item in items:
            item["artifact_urls"] = build_artifact_urls(item)
        return jsonify({"items": items})

    @app.get("/api/recent-images")
    def api_recent_images():
        requested_limit = request.args.get("limit", min(settings.recent_image_limit, 20))
        try:
            limit = max(1, min(settings.recent_image_limit, int(requested_limit)))
        except ValueError:
            limit = min(settings.recent_image_limit, 20)

        items = recent_image_store.list_recent(limit)
        for item in items:
            item["image_url"] = url_for("api_recent_image_file", image_id=item["id"])
        return jsonify(
            {
                "items": items,
                "storage": recent_image_store.stats(),
            }
        )

    @app.get("/api/recent-images/<int:image_id>")
    def api_recent_image_file(image_id: int):
        image_record = recent_image_store.get_image(image_id)
        if image_record is None:
            return jsonify({"error": "Recent image not found"}), 404

        response = Response(image_record["image_bytes"], mimetype=image_record["mime_type"])
        response.headers["Cache-Control"] = "no-store, max-age=0"
        return response

    @app.get("/api/stats")
    def api_stats():
        results_dir = Path(settings.results_dir)

        total_detect = 0
        total_convert = 0
        class_totals: dict[str, int] = {}
        inference_times: list[float] = []

        for metadata_file in sorted(results_dir.glob("*/metadata.json")):
            try:
                run = json.loads(metadata_file.read_text(encoding="utf-8"))
            except Exception:
                continue

            task = str(run.get("task", "")).strip().lower()
            summary = run.get("summary", {}) or {}

            if task == "detect":
                total_detect += 1

                for class_name, count in (summary.get("class_counts", {}) or {}).items():
                    try:
                        class_totals[class_name] = class_totals.get(class_name, 0) + int(count)
                    except (TypeError, ValueError):
                        continue

                if summary.get("inference_ms") is not None:
                    try:
                        inference_times.append(float(summary["inference_ms"]))
                    except (TypeError, ValueError):
                        pass

                if summary.get("inference_ms_avg") is not None:
                    try:
                        inference_times.append(float(summary["inference_ms_avg"]))
                    except (TypeError, ValueError):
                        pass

            elif task == "convert":
                total_convert += 1

        avg_inference_ms = round(sum(inference_times) / len(inference_times), 1) if inference_times else 0

        return jsonify(
            {
                "total_runs": total_detect + total_convert,
                "total_detect": total_detect,
                "total_convert": total_convert,
                "class_totals": class_totals,
                "avg_inference_ms": avg_inference_ms,
            }
        )

    @app.get("/api/history/<result_id>")
    def api_history_detail(result_id: str):
        record = read_record(settings.results_dir, result_id)
        if record is None:
            return jsonify({"error": "Result not found"}), 404
        record["artifact_urls"] = build_artifact_urls(record)
        return jsonify(record)

    @app.get("/api/artifacts/<result_id>/<path:filename>")
    def artifact_file(result_id: str, filename: str):
        target_dir = settings.results_dir / result_id
        if not target_dir.exists():
            return jsonify({"error": "Result not found"}), 404
        return send_from_directory(target_dir, filename, as_attachment=False)

    @app.get("/api/external-camera/source")
    def api_external_camera_source():
        source_config = get_external_camera_source_config(request.args, settings)
        source_mode = source_config["source_mode"]
        source_url = source_config["source_url"]
        stream_url = source_config["stream_url"]
        if source_mode == "stream":
            return jsonify(
                {
                    "source_mode": "stream",
                    "source_page_url": source_url,
                    "embed_url": None,
                    "youtube_id": None,
                    "title": "Configured stream source",
                    "snapshot_url": None,
                    "stream_url": stream_url,
                }
            )
        try:
            entries = extract_camera_entries(source_url, limit=1)
            if not entries:
                return jsonify({"error": "No camera video found from the external source."}), 400
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

        entry = entries[0]
        return jsonify(
            {
                "source_mode": "snapshot",
                "source_page_url": source_url,
                "embed_url": entry.embed_url,
                "youtube_id": entry.youtube_id,
                "title": entry.title,
                "snapshot_url": entry.snapshot_url,
                "stream_url": None,
            }
        )

    @app.get("/api/external-camera/live/status")
    def api_external_camera_live_status():
        return jsonify(live_monitor.status_snapshot())

    @app.get("/api/external-camera/live/stream")
    def api_external_camera_live_stream():
        requested_view = str(request.args.get("view") or "overview").strip().lower()
        # Allow "overview" + "camera_N" for N = 1..8 (max camera_limit)
        _max_cameras = settings.external_camera_limit
        allowed_views = {"overview"} | {f"camera_{i}" for i in range(1, _max_cameras + 1)}
        if requested_view not in allowed_views:
            return jsonify({"error": f"Unsupported stream view. Allowed: {sorted(allowed_views)}"}), 400

        placeholder = build_placeholder_jpeg("Waiting for live detect frame...")
        client_id = uuid.uuid4().hex[:8]
        logger.info(
            "MJPEG client connected: client=%s view=%s remote=%s running=%s",
            client_id,
            requested_view,
            request.remote_addr,
            live_monitor.status_snapshot().get("running"),
        )

        def generate():
            last_frame_id = -1
            idle_cycles = 0
            first_real_frame_logged = False
            try:
                while True:
                    frame_id, frame_bytes, running = live_monitor.get_stream_frame_snapshot(requested_view)
                    if frame_bytes is not None and frame_id != last_frame_id:
                        last_frame_id = frame_id
                        idle_cycles = 0
                        if not first_real_frame_logged:
                            logger.info(
                                "MJPEG first annotated frame ready: client=%s view=%s frame_id=%s",
                                client_id,
                                requested_view,
                                frame_id,
                            )
                            first_real_frame_logged = True
                        yield build_mjpeg_part(frame_bytes)
                        continue

                    if last_frame_id < 0:
                        yield build_mjpeg_part(placeholder)
                    elif not running:
                        logger.info(
                            "MJPEG stream reached final frame: client=%s view=%s frame_id=%s",
                            client_id,
                            requested_view,
                            last_frame_id,
                        )
                        break

                    idle_cycles += 1
                    if idle_cycles > 200 and not running:
                        logger.info(
                            "MJPEG stream idle timeout after stop: client=%s view=%s last_frame_id=%s",
                            client_id,
                            requested_view,
                            last_frame_id,
                        )
                        break
                    time.sleep(0.03)
            except GeneratorExit:
                logger.info(
                    "MJPEG client disconnected: client=%s view=%s last_frame_id=%s",
                    client_id,
                    requested_view,
                    last_frame_id,
                )
                raise
            except Exception:
                logger.exception("MJPEG stream error: client=%s view=%s", client_id, requested_view)
                raise
            finally:
                logger.info(
                    "MJPEG stream closed: client=%s view=%s last_frame_id=%s first_frame=%s idle_cycles=%s",
                    client_id,
                    requested_view,
                    last_frame_id,
                    first_real_frame_logged,
                    idle_cycles,
                )

        response = Response(generate(), mimetype="multipart/x-mixed-replace; boundary=frame")
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        response.headers["X-Accel-Buffering"] = "no"
        return response

    @app.post("/api/external-camera/live/start")
    def api_external_camera_live_start():
        try:
            conf_threshold = get_request_float(request.form, ("conf", "confidence"), 0.01, 0.99, settings.default_conf)
            iou_threshold = get_request_float(request.form, ("iou",), 0.05, 0.95, settings.default_iou)
            preprocessing = build_preprocessing_options(
                request.form,
                settings,
                default_source_layout="normal",
                profile="external_camera",
            )
            model_key = get_requested_model_key(request.form, registry)
            source_config = get_external_camera_source_config(request.form, settings)
            camera_limit = max(1, min(8, int(request.form.get("camera_limit") or settings.external_camera_limit)))
            interval_seconds = max(
                0.1,
                min(
                    120.0,
                    float(request.form.get("interval_seconds") or settings.external_camera_live_interval_seconds),
                ),
            )

            snapshot = live_monitor.start(
                source_mode=source_config["source_mode"],
                source_url=source_config["source_url"],
                stream_url=source_config["stream_url"],
                camera_limit=camera_limit,
                preprocessing=preprocessing,
                conf_threshold=conf_threshold,
                iou_threshold=iou_threshold,
                model_key=model_key,
                interval_seconds=interval_seconds,
            )
            return jsonify(snapshot)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

    @app.post("/api/external-camera/live/stop")
    def api_external_camera_live_stop():
        return jsonify(live_monitor.stop())

    @app.post("/api/external-camera/detect")
    def api_external_camera_detect():
        conf_threshold = get_request_float(request.form, ("conf", "confidence"), 0.01, 0.99, settings.default_conf)
        iou_threshold = get_request_float(request.form, ("iou",), 0.05, 0.95, settings.default_iou)
        preprocessing = build_preprocessing_options(
            request.form,
            settings,
            default_source_layout="normal",
            profile="external_camera",
        )
        camera_limit = max(1, min(8, int(request.form.get("camera_limit") or settings.external_camera_limit)))

        try:
            model_key = get_requested_model_key(request.form, registry)
            source_config = get_external_camera_source_config(request.form, settings)
            payload = run_external_camera_pipeline(
                registry,
                settings,
                recent_image_store,
                source_config["source_mode"],
                source_config["source_url"],
                source_config["stream_url"],
                camera_limit,
                preprocessing,
                conf_threshold,
                iou_threshold,
                model_key,
                persist_result=True,
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

        return jsonify(
            {
                "request_id": payload["record"]["id"],
                "task": "detect",
                "media_type": "external_camera_grid",
                "source_url": payload["source_url"],
                "camera_count": payload["camera_count"],
                "overview": payload["overview"],
                "summary": payload["summary"],
                "preprocessing": payload["preprocessing"],
                "model": payload["model"],
                "cameras": payload["cameras"],
                "record": payload["record"],
            }
        )

    @app.post("/api/detect")
    def api_detect():
        file = get_request_file("image", "file", "video")
        if file is None:
            return jsonify({"error": "No media uploaded"}), 400
        if not file or not file.filename:
            return jsonify({"error": "Empty filename"}), 400

        suffix = Path(file.filename).suffix.lower()
        if suffix in ALLOWED_VIDEO_EXTENSIONS:
            conf_threshold = get_request_float(request.form, ("conf", "confidence"), 0.01, 0.99, settings.default_conf)
            iou_threshold = get_request_float(request.form, ("iou",), 0.05, 0.95, settings.default_iou)
            preprocessing = build_preprocessing_options(request.form, settings)

            temp_input = None
            try:
                model_key = get_requested_model_key(request.form, registry)
                target_video_fps = get_video_target_detect_fps(request.form)

                # Lưu file lên disk ngay trong request (stream không thể đọc sau khi response)
                temp_input = save_uploaded_file(settings, file, suffix)
                duration_info = inspect_video_duration(temp_input)
                if duration_info["duration_seconds"] > settings.max_video_seconds:
                    temp_input.unlink(missing_ok=True)
                    return jsonify(
                        {
                            "error": (
                                f"Video too long ({duration_info['duration_seconds']:.0f}s). "
                                f"Maximum is {settings.max_video_seconds}s."
                            )
                        }
                    ), 400

                original_filename = file.filename

                def _video_job(
                    _temp_input: Path,
                    _original_filename: str,
                    _preprocessing: dict[str, Any],
                    _conf: float,
                    _iou: float,
                    _model_key: str | None,
                    _target_fps: float | None,
                ) -> dict[str, Any]:
                    _result_dir = None
                    try:
                        _result_id, _result_dir = create_result_dir(settings)
                        _annotated_path = _result_dir / "annotated.mp4"
                        _preview_path = _result_dir / "preview_annotated.jpg"
                        _model, _model_info = registry.load(_model_key)

                        # Instantiate per-job incident detector (not shared between jobs)
                        _inc_det = None
                        if _incident_detector_available and _IncidentDetectorClass is not None:
                            try:
                                _inc_det = _IncidentDetectorClass(
                                    results_dir=str(_result_dir),
                                )
                            except Exception:
                                _inc_det = None

                        _summary = run_video_detect(
                            input_path=str(_temp_input),
                            output_path=str(_annotated_path),
                            model=_model,
                            conf=_conf,
                            iou=_iou,
                            device=settings.device,
                            apply_fisheye_transform=_preprocessing["enabled"],
                            fisheye_strength=_preprocessing["strength"],
                            fisheye_radius=_preprocessing["radius"],
                            fisheye_effect=_preprocessing["effect"],
                            preview_path=str(_preview_path),
                            name_map=NAME_MAP,
                            allowed_classes=set(CLASS_NAMES),
                            filter_allowed_classes=(
                                _model_info["source"] == "fallback"
                                and settings.filter_fallback_to_supported_classes
                            ),
                            target_detect_fps=_target_fps,
                            incident_detector=_inc_det,
                            incident_camera_id=f"upload_{_result_id}",
                        )
                        _record = save_video_detection_record(
                            settings,
                            recent_image_store,
                            _original_filename,
                            _preprocessing,
                            _conf,
                            _iou,
                            _model_info,
                            _summary,
                            _result_dir,
                        )
                        _record["artifact_urls"] = build_artifact_urls(_record)
                        return {
                            "request_id": _record["id"],
                            "task": "detect",
                            "media_type": "video",
                            "summary": _summary,
                            "model": _record["model"],
                            "preprocessing": _preprocessing,
                            "record": _record,
                        }
                    except Exception:
                        if _result_dir and _result_dir.exists():
                            shutil.rmtree(_result_dir, ignore_errors=True)
                        raise
                    finally:
                        _temp_input.unlink(missing_ok=True)

                _queue: VideoJobQueue = app.extensions["fisheye_job_queue"]
                job_id = _queue.submit(
                    _video_job,
                    temp_input,
                    original_filename,
                    preprocessing,
                    conf_threshold,
                    iou_threshold,
                    model_key,
                    target_video_fps,
                    job_type="video_detect",
                    meta={
                        "filename": original_filename,
                        "duration_seconds": round(duration_info["duration_seconds"], 1),
                    },
                )
                # temp_input ownership transferred to job — do not delete here
                temp_input = None

            except ValueError as exc:
                if temp_input and temp_input.exists():
                    temp_input.unlink(missing_ok=True)
                return jsonify({"error": str(exc)}), 400
            except RuntimeError as exc:
                if temp_input and temp_input.exists():
                    temp_input.unlink(missing_ok=True)
                return jsonify({"error": str(exc)}), 503
            except Exception as exc:
                if temp_input and temp_input.exists():
                    temp_input.unlink(missing_ok=True)
                return jsonify({"error": str(exc)}), 500

            return jsonify(
                {
                    "job_id": job_id,
                    "status": "pending",
                    "task": "detect",
                    "media_type": "video",
                    "poll_url": f"/api/jobs/{job_id}",
                    "meta": {
                        "filename": original_filename,
                        "duration_seconds": round(duration_info["duration_seconds"], 1),
                    },
                }
            ), 202

        if suffix not in ALLOWED_IMAGE_EXTENSIONS:
            return jsonify({"error": f"Unsupported image file type: {suffix or 'unknown'}"}), 400

        conf_threshold = get_request_float(request.form, ("conf", "confidence"), 0.01, 0.99, settings.default_conf)
        iou_threshold = get_request_float(request.form, ("iou",), 0.05, 0.95, settings.default_iou)
        preprocessing = build_preprocessing_options(request.form, settings)

        try:
            model_key = get_requested_model_key(request.form, registry)
            original_image = read_uploaded_image(file)
            preprocessed_image = apply_preprocessing(original_image, preprocessing)
            annotated_image, detections, class_counts, inference_ms, model_info = run_inference(
                registry,
                settings,
                preprocessed_image,
                conf_threshold,
                iou_threshold,
                model_key=model_key,
            )
            record = save_detection_record(
                settings,
                recent_image_store,
                file.filename,
                original_image,
                preprocessed_image,
                annotated_image,
                detections,
                class_counts,
                inference_ms,
                conf_threshold,
                iou_threshold,
                model_info,
                preprocessing,
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

        record["artifact_urls"] = build_artifact_urls(record)

        # ── Cập nhật analytics in-memory ─────────────────────────────────────
        _hm = app.extensions.get("fisheye_heatmap")
        _da = app.extensions.get("fisheye_density_analyzer")
        _am = app.extensions.get("fisheye_alert_manager")
        if _hm is not None:
            try:
                _hm.update(detections, frame_width=original_image.width, frame_height=original_image.height)
            except Exception:
                pass
        if _da is not None:
            try:
                _da.update(len(detections), class_counts)
            except Exception:
                pass
        if _am is not None:
            try:
                _am.check_and_alert(len(detections), class_counts, camera_source="upload")
            except Exception:
                pass

        return jsonify(
            {
                "request_id": record["id"],
                "task": "detect",
                "media_type": "image",
                "original": pil_to_b64(original_image),
                "preprocessed": pil_to_b64(preprocessed_image),
                "result": pil_to_b64(annotated_image),
                "detections": detections,
                "class_counts": class_counts,
                "inference_ms": round(inference_ms, 1),
                "total_objects": len(detections),
                "model": record["model"],
                "preprocessing": preprocessing,
                "record": record,
                "gcs_urls": record.get("gcs_urls", {}),
            }
        )

    # ── Async job polling endpoints ───────────────────────────────────────────

    @app.get("/api/jobs/<job_id>")
    def api_job_status(job_id: str):
        """Poll status of an async video processing job."""
        _queue: VideoJobQueue = app.extensions["fisheye_job_queue"]
        job = _queue.get(job_id)
        if job is None:
            return jsonify({"error": "Job not found"}), 404

        resp: dict[str, Any] = {
            "job_id": job["job_id"],
            "status": job["status"],
            "job_type": job["job_type"],
            "created_at": job["created_at"],
            "started_at": job["started_at"],
            "finished_at": job["finished_at"],
            "meta": job.get("meta", {}),
        }

        if job["status"] == "done":
            resp["result"] = job.get("result")
        elif job["status"] == "failed":
            resp["error"] = job.get("error")

        return jsonify(resp)

    @app.get("/api/jobs")
    def api_jobs_list():
        """List recent async jobs (without full result payload)."""
        _queue: VideoJobQueue = app.extensions["fisheye_job_queue"]
        limit = min(int(request.args.get("limit", 20)), 100)
        return jsonify(
            {
                "jobs": _queue.list_recent(limit=limit),
                "stats": _queue.stats(),
            }
        )

    @app.delete("/api/jobs/<job_id>")
    def api_job_cancel(job_id: str):
        """Cancel a pending job."""
        _queue: VideoJobQueue = app.extensions["fisheye_job_queue"]
        if _queue.get(job_id) is None:
            return jsonify({"error": "Job not found"}), 404
        cancelled = _queue.cancel(job_id)
        if cancelled:
            return jsonify({"job_id": job_id, "status": "cancelled"})
        return jsonify({"error": "Job cannot be cancelled (not in pending state)"}), 409

    @app.post("/api/convert")
    def api_convert():
        upload = get_request_file("media", "file", "image", "video")
        if upload is None:
            return jsonify({"error": "No media uploaded"}), 400
        if not upload.filename:
            return jsonify({"error": "Empty filename"}), 400

        suffix = Path(upload.filename).suffix.lower()
        if suffix not in ALLOWED_MEDIA_EXTENSIONS:
            return jsonify({"error": f"Unsupported media type: {suffix or 'unknown'}"}), 400

        preprocessing = build_preprocessing_options(request.form, settings)
        preprocessing["enabled"] = True

        if suffix in ALLOWED_IMAGE_EXTENSIONS:
            try:
                original_image = read_uploaded_image(upload)
                fisheye_image = apply_preprocessing(original_image, preprocessing)
                record = save_image_conversion_record(
                    settings,
                    recent_image_store,
                    upload.filename,
                    original_image,
                    fisheye_image,
                    preprocessing,
                )
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400
            except Exception as exc:
                return jsonify({"error": str(exc)}), 500

            record["artifact_urls"] = build_artifact_urls(record)
            return jsonify(
                {
                    "request_id": record["id"],
                    "task": "convert",
                    "media_type": "image",
                    "original": pil_to_b64(original_image),
                    "result": pil_to_b64(fisheye_image),
                    "preprocessing": preprocessing,
                    "record": record,
                }
            )

        temp_input = None
        temp_output = None
        try:
            temp_input = save_uploaded_file(settings, upload, suffix)
            temp_output = settings.upload_dir / f"fisheye-{uuid.uuid4().hex}.mp4"
            video_info, preview_original, preview_fisheye = convert_video_to_fisheye(
                settings,
                temp_input,
                temp_output,
                preprocessing,
            )
            record = save_video_conversion_record(
                settings,
                recent_image_store,
                upload.filename,
                temp_input,
                temp_output,
                preview_original,
                preview_fisheye,
                preprocessing,
                video_info,
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500
        finally:
            if temp_input and temp_input.exists():
                temp_input.unlink(missing_ok=True)
            if temp_output and temp_output.exists():
                temp_output.unlink(missing_ok=True)

        record["artifact_urls"] = build_artifact_urls(record)
        return jsonify(
            {
                "request_id": record["id"],
                "task": "convert",
                "media_type": "video",
                "preview_original": pil_to_b64(preview_original),
                "preview_result": pil_to_b64(preview_fisheye),
                "video_info": video_info,
                "preprocessing": preprocessing,
                "record": record,
            }
        )

    @app.post("/detect")
    def detect_legacy():
        return api_detect()

    @app.errorhandler(413)
    def file_too_large(_error):
        return jsonify({"error": f"File too large. Limit is {settings.max_upload_mb} MB."}), 413

    @app.errorhandler(404)
    def not_found(_error):
        return jsonify({"error": "Not found"}), 404

    @app.errorhandler(500)
    def internal_error(error):
        return jsonify({"error": str(error)}), 500

    # ── Đăng ký extended routes (DB / Analytics / Alerts / Cloud) ────────────
    if _extended_enabled and _heatmap is not None:
        try:
            register_extended_routes(
                app,
                settings,
                registry,
                heatmap=_heatmap,
                density_analyzer=_density_analyzer,
                alert_manager=_alert_manager,
                line_counter=_line_counter,
            )
        except Exception as _reg_exc:
            logger.warning("register_extended_routes failed: %s", _reg_exc)

    if settings.preload_model:
        try:
            registry.load()
        except Exception:
            pass

    return app


load_env_file(ENV_PATH)

app = create_app({"SETTINGS_OVERRIDES": {"preload_model": parse_bool(os.getenv("FISHEYE_IMPORT_PRELOAD_MODEL", "0"))}})


if __name__ == "__main__":
    settings: AppSettings = app.extensions["fisheye_settings"]
    registry: ModelRegistry = app.extensions["fisheye_model_registry"]
    print("=" * 60)
    print("FishEye8K Detection System")
    print("Web UI : http://127.0.0.1:5000")
    print(f"Device : {settings.device}")
    print("=" * 60)
    if parse_bool(os.getenv("FISHEYE_PRELOAD_MODEL", "1")):
        try:
            registry.load()
        except Exception as exc:
            print(f"[WARN] Model preload skipped: {exc}")
    app.run(debug=False, host="0.0.0.0", port=5000)

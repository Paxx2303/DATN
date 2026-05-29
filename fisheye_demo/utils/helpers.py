from __future__ import annotations

import io
import base64
from datetime import datetime, timezone
from typing import Any
from PIL import Image

try:
    from config import NAME_MAP
except ImportError:
    from fisheye_demo.config import NAME_MAP


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


def apply_preprocessing(image: Image.Image, preprocessing: dict[str, Any]) -> Image.Image:
    try:
        from fisheye import apply_fisheye
    except ImportError:
        from fisheye_demo.fisheye import apply_fisheye

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


"""
utils/helpers.py — Shared Utility Functions

Các hàm tiện ích nhỏ dùng trong routes và services.
"""

import uuid
import base64
import io
import logging
from pathlib import Path
from typing import Optional, BinaryIO
import numpy as np
from PIL import Image
from config import Config

logger = logging.getLogger(__name__)


def generate_result_id() -> str:
    """Tạo ID duy nhất cho một kết quả nhận diện."""
    return uuid.uuid4().hex   # 32-char hex string


def safe_upload_filename(original: str, fallback: str = "upload") -> str:
    """Sanitize upload name while preserving the original extension when possible."""
    from werkzeug.utils import secure_filename

    safe = secure_filename(original)
    if not safe:
        safe = fallback

    orig_ext = Path(original).suffix.lower()
    safe_ext = Path(safe).suffix.lower()
    if orig_ext and not safe_ext:
        safe = f"{safe}{orig_ext}"
    return safe


def classify_upload_file(file_storage, filename: str) -> tuple[bool, bool]:
    """Return (is_image, is_video) using extension and MIME type fallback."""
    is_image = allowed_media_file(filename, "image")
    is_video = allowed_media_file(filename, "video")

    if not is_image and not is_video:
        ctype = (getattr(file_storage, "content_type", None) or "").lower()
        if ctype.startswith("image/"):
            is_image = True
        elif ctype.startswith("video/"):
            is_video = True

    return is_image, is_video


def is_fisheye_model(model_key: Optional[str]) -> bool:
    """True when checkpoint expects fisheye-warped input."""
    key = (model_key or "").lower()
    return key in {"best", "fisheye"} or "fisheye" in key


def resolve_fisheye_enabled(
    apply_raw: Optional[str],
    source_layout: str = "normal",
    *,
    auto_apply_for_normal: bool = False,
    model_key: Optional[str] = None,
) -> bool:
    """
    Resolve whether fisheye preprocessing should run.

    - explicit true/false always wins
    - auto / missing:
        upload detect  → warp only for fisheye checkpoints on normal layout
        live/external  → keep raw frames unless user forces enabled
    """
    if apply_raw is not None:
        val = str(apply_raw).strip().lower()
        if val in ("true", "1", "yes", "on"):
            return True
        if val in ("false", "0", "no", "off"):
            return False

    if auto_apply_for_normal:
        if source_layout == "fisheye":
            return False
        return is_fisheye_model(model_key)
    return False


def normalize_bbox(
    bbox: list,
    img_width: int,
    img_height: int,
) -> Optional[tuple[int, int, int, int]]:
    """Clamp bbox to image bounds and reject degenerate / needle-thin boxes."""
    if not bbox or len(bbox) < 4:
        return None

    raw = [float(v) for v in bbox[:4]]

    # Handle accidental normalized coordinates from upstream APIs.
    if img_width > 1 and img_height > 1 and all(0.0 <= v <= 1.0 for v in raw):
        if max(raw) <= 1.0:
            raw = [
                raw[0] * img_width,
                raw[1] * img_height,
                raw[2] * img_width,
                raw[3] * img_height,
            ]

    x1 = max(0, min(int(round(raw[0])), img_width - 1))
    y1 = max(0, min(int(round(raw[1])), img_height - 1))
    x2 = max(0, min(int(round(raw[2])), img_width - 1))
    y2 = max(0, min(int(round(raw[3])), img_height - 1))

    if x2 <= x1 or y2 <= y1:
        return None

    width = x2 - x1
    height = y2 - y1
    min_side = max(8, min(img_width, img_height) // 100)
    if width < min_side or height < min_side:
        return None

    aspect = width / max(height, 1)
    if aspect > 8.0 or aspect < 0.125:
        return None

    return x1, y1, x2, y2


def read_uploaded_image(file_storage) -> Optional[Image.Image]:
    """
    Đọc ảnh từ Flask FileStorage object.
    
    Parameters
    ----------
    file_storage : werkzeug.datastructures.FileStorage
    
    Returns
    -------
    PIL Image (RGB) hoặc None nếu lỗi
    """
    try:
        stream = file_storage.stream
        stream.seek(0)
        img = Image.open(stream).convert("RGB")
        stream.seek(0)
        return img
    except Exception as e:
        logger.error(f"Cannot read uploaded image: {e}")
        return None


def apply_preprocessing(
    image: Image.Image,
    enabled: bool = False,
    strength: float = 0.6,
    radius: float = 0.85,
    effect: str = "standard",
    center_x: float = 0.5,
    center_y: float = 0.5,
) -> Image.Image:
    """
    Apply fisheye preprocessing nếu enabled.
    Wrapper để routes không import trực tiếp fisheye.py.
    """
    if not enabled:
        return image
    
    from fisheye import apply_fisheye
    return apply_fisheye(
        image,
        strength=strength,
        radius=radius,
        effect=effect,
        center_x=center_x,
        center_y=center_y,
    )


def pil_to_base64(image: Image.Image, format: str = "JPEG", quality: int = 85) -> str:
    """Encode PIL Image thành base64 string cho JSON response."""
    buf = io.BytesIO()
    if format == "JPEG" and image.mode in ("RGBA", "P"):
        image = image.convert("RGB")
    image.save(buf, format=format, quality=quality)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def draw_detections_on_image(
    image: Image.Image,
    detections: list[dict],
    name_map: Optional[dict] = None,
    speed_data: Optional[dict] = None,
) -> Image.Image:
    """
    Vẽ bounding boxes và labels lên ảnh PIL.
    Dùng cho image inference (không phải video).
    
    Parameters
    ----------
    speed_data : dict[int, float]
        Mapping từ detection index → speed (km/h)
    
    Returns ảnh PIL mới đã annotated.
    """
    import cv2
    
    name_map = name_map or {}
    speed_data = speed_data or {}
    
    # PIL → OpenCV BGR
    img_array = np.array(image)[..., ::-1].copy()
    img_height, img_width = img_array.shape[:2]
    
    COLOR_MAP = {
        "Car":        (0, 255, 0),
        "Truck":      (255, 128, 0),
        "Bus":        (0, 128, 255),
        "Motorbike":  (255, 0, 255),
        "Pedestrian": (255, 255, 0),
        "Bicycle":    (0, 255, 255),
    }
    
    for idx, det in enumerate(detections):
        label = det.get("class_name", "unknown")
        conf  = det.get("confidence", 0.0)
        coords = normalize_bbox(det.get("bbox", [0, 0, 0, 0]), img_width, img_height)
        if coords is None:
            continue
        x1, y1, x2, y2 = coords

        color = COLOR_MAP.get(label, (200, 200, 200))
        
        # Bounding box
        cv2.rectangle(img_array, (x1, y1), (x2, y2), color, 2)
        
        text = f"{label} {conf:.2f}"
        speed = speed_data.get(idx)
        if speed is None or speed <= 0:
            speed = det.get("speed_kmh", 0.0)
        has_speed = speed is not None and speed > 0

        font_scale = 0.5
        font_thickness = 1
        (tw, th), baseline = cv2.getTextSize(
            text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, font_thickness,
        )

        text_y = max(y1 - 5, th + 5)
        cv2.rectangle(
            img_array,
            (x1, text_y - th - baseline),
            (x1 + tw + 6, text_y + baseline),
            color, -1,
        )
        cv2.putText(
            img_array, text, (x1 + 3, text_y - baseline),
            cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 0, 0), font_thickness,
        )

        if has_speed:
            speed_text = f"{speed:.0f} km/h"
            speed_scale = 0.62
            (sw, sh), sbase = cv2.getTextSize(
                speed_text, cv2.FONT_HERSHEY_SIMPLEX, speed_scale, 2,
            )
            speed_y = min(y2 + sh + 10, img_height - 4)
            speed_bg = (20, 120, 255)  # highlighted orange (BGR)
            cv2.rectangle(
                img_array,
                (x1, speed_y - sh - sbase - 4),
                (x1 + sw + 10, speed_y + 4),
                speed_bg, -1,
            )
            cv2.putText(
                img_array, speed_text, (x1 + 5, speed_y - sbase),
                cv2.FONT_HERSHEY_SIMPLEX, speed_scale, (255, 255, 255), 2,
            )
    
    # OpenCV BGR → PIL RGB
    result = Image.fromarray(img_array[..., ::-1])
    return result


def ensure_result_dir(result_id: str) -> Path:
    """Tạo và trả về thư mục result cho result_id."""
    result_dir = Config.RESULTS_FOLDER / result_id
    result_dir.mkdir(parents=True, exist_ok=True)
    return result_dir


def allowed_media_file(filename: str, media_type: str = "both") -> bool:
    """
    Kiểm tra extension file hợp lệ.
    
    Parameters
    ----------
    media_type : "image" | "video" | "both"
    """
    IMAGE_EXTS = {".jpg", ".jpeg", ".jfif", ".png", ".bmp", ".webp", ".tiff"}
    VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv"}
    
    ext = Path(filename).suffix.lower()
    
    if media_type == "image":
        return ext in IMAGE_EXTS
    elif media_type == "video":
        return ext in VIDEO_EXTS
    else:
        return ext in IMAGE_EXTS | VIDEO_EXTS

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
        img = Image.open(file_storage.stream).convert("RGB")
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
) -> Image.Image:
    """
    Vẽ bounding boxes và labels lên ảnh PIL.
    Dùng cho image inference (không phải video).
    
    Returns ảnh PIL mới đã annotated.
    """
    import cv2
    
    name_map = name_map or {}
    
    # PIL → OpenCV BGR
    img_array = np.array(image)[..., ::-1].copy()
    
    COLOR_MAP = {
        "Car":        (0, 255, 0),
        "Truck":      (255, 128, 0),
        "Bus":        (0, 128, 255),
        "Motorbike":  (255, 0, 255),
        "Pedestrian": (255, 255, 0),
        "Bicycle":    (0, 255, 255),
    }
    
    for det in detections:
        label = det.get("class_name", "unknown")
        conf  = det.get("confidence", 0.0)
        x1, y1, x2, y2 = det.get("bbox", [0, 0, 0, 0])
        
        color = COLOR_MAP.get(label, (200, 200, 200))
        
        # Bounding box
        cv2.rectangle(img_array, (x1, y1), (x2, y2), color, 2)
        
        # Label text
        text = f"{label} {conf:.2f}"
        (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(img_array, (x1, y1-th-8), (x1+tw+6, y1), color, -1)
        cv2.putText(img_array, text, (x1+3, y1-4),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
    
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
    IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff"}
    VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv"}
    
    ext = Path(filename).suffix.lower()
    
    if media_type == "image":
        return ext in IMAGE_EXTS
    elif media_type == "video":
        return ext in VIDEO_EXTS
    else:
        return ext in IMAGE_EXTS | VIDEO_EXTS

"""
config.py — FishEye8K Configuration

THIẾT KẾ:
- Dùng class Config với class attributes để dễ import.
- Tất cả path dùng os.path.abspath để tương thích đa hệ điều hành.
- load_dotenv() gọi ngay khi import module.
- Các tham số có giá trị mặc định hợp lý để chạy được không cần .env.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Nạp .env file ngay lập tức
load_dotenv()

# BASE_DIR = thư mục chứa config.py
BASE_DIR = Path(__file__).parent.resolve()


def _env(*names: str, default: str | None = None) -> str | None:
    """Trả giá trị env var đầu tiên tồn tại trong danh sách tên (hỗ trợ alias).

    Cho phép cùng một thiết lập dùng nhiều tên (ví dụ COMPUTE_DEVICE hoặc
    FISHEYE_DEVICE) để .env và config.py không bị lệch nhau.
    """
    for name in names:
        val = os.getenv(name)
        if val is not None and val != "":
            return val
    return default


def _resolve_dir(value: str | None, fallback: Path) -> Path:
    """Chuyển một path từ env thành Path tuyệt đối (relative → so với BASE_DIR)."""
    if not value:
        return fallback
    p = Path(value)
    return p if p.is_absolute() else (BASE_DIR / p)


def _resolve_device(value: str | None) -> str:
    """
    Chọn thiết bị tính toán: MẶC ĐỊNH dùng GPU nếu có, không thì CPU.

    - Nếu env đặt tường minh ("cpu", "cuda:0", "0", "mps") → tôn trọng.
    - Nếu rỗng / "auto" / "gpu" → tự dò: CUDA → MPS → CPU.
    Không bao giờ ép GPU khi máy không có (tránh lỗi 500 lúc inference).
    """
    v = (value or "").strip().lower()
    if v and v not in ("auto", "gpu"):
        return value  # override tường minh
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda:0"
        mps = getattr(getattr(torch, "backends", None), "mps", None)
        if mps is not None and mps.is_available():
            return "mps"
    except Exception:
        pass
    return "cpu"


class Config:
    # ── Paths ────────────────────────────────────────────────
    UPLOAD_FOLDER     = _resolve_dir(_env("FISHEYE_UPLOAD_DIR"), BASE_DIR / "static" / "uploads")
    RESULTS_FOLDER    = _resolve_dir(_env("FISHEYE_RESULTS_DIR"), BASE_DIR / "static" / "results")
    MODEL_FOLDER      = BASE_DIR                 # Tìm trực tiếp ở thư mục gốc (BASE_DIR) vì checkpoints nằm ở đó
    DB_PATH           = BASE_DIR / "fisheye.db" # SQLite fallback
    RECENT_IMAGE_DB   = _resolve_dir(_env("FISHEYE_RECENT_IMAGE_DB"), BASE_DIR / "recent_images.db")

    # ── Flask ────────────────────────────────────────────────
    SECRET_KEY        = _env("SECRET_KEY", "FISHEYE_SECRET_KEY", default="fisheye8k-dev-secret")
    DEBUG             = _env("FLASK_DEBUG", "FISHEYE_DEBUG", default="0") == "1"
    MAX_CONTENT_LENGTH = int(_env("FISHEYE_MAX_UPLOAD_MB", default="500")) * 1024 * 1024

    # ── Database ─────────────────────────────────────────────
    DATABASE_URL      = os.getenv("DATABASE_URL", "")  # postgresql://...

    # ── YOLO Model ───────────────────────────────────────────
    DEFAULT_MODEL_KEY = os.getenv("DEFAULT_MODEL", "traffic")
    AVAILABLE_MODELS  = {
        "traffic": str(MODEL_FOLDER / "traffic.pt"),
    }
    DEFAULT_CONF      = float(_env("YOLO_CONF", "FISHEYE_DEFAULT_CONF", default="0.35"))
    DEFAULT_IOU       = float(_env("YOLO_IOU", "FISHEYE_DEFAULT_IOU", default="0.45"))
    DEFAULT_DEVICE    = _resolve_device(_env("COMPUTE_DEVICE", "FISHEYE_DEVICE"))  # auto: GPU nếu có, không thì CPU

    # ── Fisheye Defaults ─────────────────────────────────────
    FISHEYE_STRENGTH  = float(os.getenv("FISHEYE_STRENGTH", "0.6"))
    FISHEYE_RADIUS    = float(os.getenv("FISHEYE_RADIUS", "0.85"))
    FISHEYE_EFFECT    = os.getenv("FISHEYE_EFFECT", "standard")  # standard|extreme|subtle

    # ── Job Queue ────────────────────────────────────────────
    JOB_MAX_WORKERS   = int(os.getenv("JOB_WORKERS", "2"))
    TARGET_DETECT_FPS = float(os.getenv("TARGET_DETECT_FPS", "5.0"))  # fps để sample frames

    # ── External Camera Polling ──────────────────────────────
    EXT_CAM_SOURCE_URL = os.getenv("EXT_CAM_SOURCE_URL", "https://camera.0511.vn/camera.html")
    EXT_CAM_INTERVAL   = float(
        os.getenv("EXT_CAM_INTERVAL")
        or os.getenv("FISHEYE_EXTERNAL_CAMERA_LIVE_INTERVAL", "0.3")
    )  # giây/chu kỳ (reader nền cho frame tức thì nên có thể chạy nhanh)
    EXT_CAM_LIMIT      = int(os.getenv("EXT_CAM_LIMIT", "2"))       # xử lý tối đa 2 camera
    EXT_CAM_LIMIT_GPU  = int(os.getenv("EXT_CAM_LIMIT_GPU", "2"))   # cameras in parallel (GPU)
    EXT_CAM_LIMIT_CPU  = int(os.getenv("EXT_CAM_LIMIT_CPU", "1"))   # cameras sequential (CPU)

    # ── ALPR (Nhận diện biển số) trên feed live ──────────────
    ALPR_LIVE_ENABLED = os.getenv("ALPR_LIVE_ENABLED", "true").lower() == "true"
    ALPR_LIVE_EVERY   = int(os.getenv("ALPR_LIVE_EVERY", "3"))   # OCR mỗi N chu kỳ
    ALPR_LIVE_MAX_VEH = int(os.getenv("ALPR_LIVE_MAX_VEH", "6")) # số crop tối đa/cam/chu kỳ

    # ── Speed Estimation ─────────────────────────────────────
    # px→m scale: 1px ≈ SPEED_SCALE_FACTOR metres (calibrate per camera)
    SPEED_SCALE_FACTOR = float(os.getenv("SPEED_SCALE_FACTOR", "0.05"))

    # ── Alert Thresholds ─────────────────────────────────────
    ALERT_HIGH_DENSITY = int(os.getenv("ALERT_HIGH_DENSITY", "20"))  # xe/frame

    # ── Speed Violation ──────────────────────────────────────
    SPEED_LIMIT_KMH    = float(os.getenv("SPEED_LIMIT_KMH", "50.0"))

    # ── Webhook ──────────────────────────────────────────────
    WEBHOOK_URL        = os.getenv("WEBHOOK_URL", "")

    # ── Google Cloud Storage (optional) ─────────────────────
    GCS_BUCKET        = os.getenv("GCS_BUCKET", "")
    GCS_CREDENTIALS   = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")

    # ── Recent Image Buffer ──────────────────────────────────
    RECENT_IMAGE_LIMIT = int(_env("FISHEYE_RECENT_IMAGE_LIMIT", default="100"))

    # ── Vehicle Name Mapping ─────────────────────────────────
    # Map COCO class names → tiếng Việt / custom labels
    VEHICLE_NAME_MAP  = {
        "car":        "Car",
        "truck":      "Truck",
        "bus":        "Bus",
        "motorcycle": "Motorbike",
        "person":     "Pedestrian",
        "bicycle":    "Bicycle",
    }
    # Add values to the set so Title case model names are also accepted
    VEHICLE_CLASSES   = set(VEHICLE_NAME_MAP.keys()).union(set(VEHICLE_NAME_MAP.values()))

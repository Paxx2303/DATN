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


class Config:
    # ── Paths ────────────────────────────────────────────────
    UPLOAD_FOLDER     = BASE_DIR / "static" / "uploads"
    RESULTS_FOLDER    = BASE_DIR / "static" / "results"
    MODEL_FOLDER      = BASE_DIR                 # Tìm trực tiếp ở thư mục gốc (BASE_DIR) vì checkpoints nằm ở đó
    DB_PATH           = BASE_DIR / "fisheye.db" # SQLite fallback

    # ── Flask ────────────────────────────────────────────────
    SECRET_KEY        = os.getenv("SECRET_KEY", "fisheye8k-dev-secret")
    DEBUG             = os.getenv("FLASK_DEBUG", "0") == "1"
    MAX_CONTENT_LENGTH = 500 * 1024 * 1024   # 500 MB upload limit

    # ── Database ─────────────────────────────────────────────
    DATABASE_URL      = os.getenv("DATABASE_URL", "")  # postgresql://...

    # ── YOLO Model ───────────────────────────────────────────
    DEFAULT_MODEL_KEY = os.getenv("DEFAULT_MODEL", "best")
    AVAILABLE_MODELS  = {
        "best":  str(MODEL_FOLDER / "yolo11_fisheye_v5_best.pt"),
        "nano":  str(MODEL_FOLDER / "yolo11n.pt"),
        "small": str(MODEL_FOLDER / "traffic.pt"),
    }
    DEFAULT_CONF      = float(os.getenv("YOLO_CONF", "0.35"))
    DEFAULT_IOU       = float(os.getenv("YOLO_IOU", "0.45"))
    DEFAULT_DEVICE    = os.getenv("COMPUTE_DEVICE", "cpu")  # "cpu" | "cuda:0" | "mps"

    # ── Fisheye Defaults ─────────────────────────────────────
    FISHEYE_STRENGTH  = float(os.getenv("FISHEYE_STRENGTH", "0.6"))
    FISHEYE_RADIUS    = float(os.getenv("FISHEYE_RADIUS", "0.85"))
    FISHEYE_EFFECT    = os.getenv("FISHEYE_EFFECT", "standard")  # standard|extreme|subtle

    # ── Job Queue ────────────────────────────────────────────
    JOB_MAX_WORKERS   = int(os.getenv("JOB_WORKERS", "2"))
    TARGET_DETECT_FPS = float(os.getenv("TARGET_DETECT_FPS", "5.0"))  # fps để sample frames

    # ── External Camera Polling ──────────────────────────────
    EXT_CAM_SOURCE_URL = os.getenv("EXT_CAM_SOURCE_URL", "https://camera.0511.vn/camera.html")
    EXT_CAM_INTERVAL   = float(os.getenv("EXT_CAM_INTERVAL", "10.0"))  # seconds
    EXT_CAM_LIMIT      = int(os.getenv("EXT_CAM_LIMIT", "6"))
    EXT_CAM_LIMIT_GPU  = int(os.getenv("EXT_CAM_LIMIT_GPU", "4"))   # cameras in parallel (GPU)
    EXT_CAM_LIMIT_CPU  = int(os.getenv("EXT_CAM_LIMIT_CPU", "1"))   # cameras sequential (CPU)

    # ── Speed Estimation ─────────────────────────────────────
    # px→m scale: 1px ≈ SPEED_SCALE_FACTOR metres (calibrate per camera)
    SPEED_SCALE_FACTOR = float(os.getenv("SPEED_SCALE_FACTOR", "0.05"))

    # ── Alert Thresholds ─────────────────────────────────────
    ALERT_HIGH_DENSITY = int(os.getenv("ALERT_HIGH_DENSITY", "20"))  # xe/frame

    # ── Google Cloud Storage (optional) ─────────────────────
    GCS_BUCKET        = os.getenv("GCS_BUCKET", "")
    GCS_CREDENTIALS   = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")

    # ── Recent Image Buffer ──────────────────────────────────
    RECENT_IMAGE_LIMIT = 100

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

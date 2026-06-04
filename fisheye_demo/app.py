"""
app.py — Flask Application Factory

THIẾT KẾ:
- create_app() là điểm khởi tạo duy nhất. Không import trực tiếp `app` từ ngoài.
- Thứ tự khởi tạo: Config → Folders → DB → Blueprints → Logging.
- Hỗ trợ graceful shutdown với atexit để dừng background threads.
"""
import logging
import atexit
from flask import Flask
from config import Config
from db import init_db
from routes import register_blueprints


def create_app(config_class=Config) -> Flask:
    app = Flask(__name__, 
                static_folder="static",
                template_folder="templates")
    app.config.from_object(config_class)

    # 1. Đảm bảo thư mục tồn tại
    _ensure_directories(app)

    # 2. Khởi tạo database (SQLite hoặc PostgreSQL)
    db_type = init_db()
    app.logger.info(f"Database initialized: {db_type}")

    # 3. Đăng ký tất cả Blueprints
    register_blueprints(app)

    # 4. Cấu hình logging toàn hệ thống
    _configure_logging(app)

    # 5. Đăng ký cleanup hook khi server dừng
    from services.camera_monitor import camera_monitor
    atexit.register(lambda: camera_monitor.stop())

    return app


def _ensure_directories(app: Flask) -> None:
    """Tạo thư mục cần thiết nếu chưa tồn tại."""
    for folder_key in ("UPLOAD_FOLDER", "RESULTS_FOLDER"):
        path = app.config[folder_key]
        path.mkdir(parents=True, exist_ok=True)
    # Thư mục models
    Config.MODEL_FOLDER.mkdir(parents=True, exist_ok=True)


def _configure_logging(app: Flask) -> None:
    """Cấu hình logging với format đầy đủ timestamp + level."""
    log_level = logging.DEBUG if app.config["DEBUG"] else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # Giảm noise từ thư viện bên ngoài
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("ultralytics").setLevel(logging.WARNING)


# Entry point cho development
if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=5000, debug=Config.DEBUG, use_reloader=False)
    # use_reloader=False vì background threads không tương thích với reloader

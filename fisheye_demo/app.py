"""
app.py — Flask Application Factory

THIẾT KẾ:
- create_app() là điểm khởi tạo duy nhất. Không import trực tiếp `app` từ ngoài.
- Thứ tự khởi tạo: Config → Folders → DB → Blueprints → Extended Routes → Logging.
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

    # 4. Đăng ký extended routes (analytics, alerts, line-counter, speed, congestion...)
    _register_extended(app)

    # 5. Cấu hình logging toàn hệ thống
    _configure_logging(app)

    # 6. Đăng ký cleanup hook khi server dừng
    from services.camera_monitor import camera_monitor
    atexit.register(lambda: camera_monitor.stop())

    return app


def _register_extended(app: Flask) -> None:
    """Import và gọi register_extended_routes() với các singleton cần thiết."""
    try:
        from routes_extended import register_extended_routes
        from analytics import heatmap, density_analyzer
        from alert_manager import alert_manager
        from line_counter import line_counter
        from speed_estimator import SpeedEstimator
        from congestion_detector import CongestionDetector

        # Tạo adapter objects đơn giản cho settings và registry
        # (routes_extended dùng settings.device và registry.load())
        class _Settings:
            device = Config.DEFAULT_DEVICE

        class _Registry:
            def load(self):
                from services.model_registry import load_model, get_available_models
                model_key = Config.DEFAULT_MODEL_KEY
                model = load_model(model_key, Config.DEFAULT_DEVICE)
                avail = get_available_models()
                model_info = avail.get(model_key, {})
                model_info["loaded_from_name"] = model_info.get("name", model_key)
                model_info["device"] = Config.DEFAULT_DEVICE
                return model, model_info

        # Singleton instances cho các API trạng thái toàn cục
        speed_estimator = SpeedEstimator(
            speed_limit_kmh=Config.SPEED_LIMIT_KMH,
        )
        congestion_detector = CongestionDetector()

        register_extended_routes(
            app=app,
            settings=_Settings(),
            registry=_Registry(),
            heatmap=heatmap,
            density_analyzer=density_analyzer,
            alert_manager=alert_manager,
            line_counter=line_counter,
            speed_estimator=speed_estimator,
            congestion_detector=congestion_detector,
        )
        app.logger.info("Extended routes registered successfully")
    except Exception as exc:
        app.logger.error(
            "register_extended_routes FAILED — extended API endpoints "
            "(analytics/alerts/incidents/speed/congestion) will be missing: %s",
            exc, exc_info=True,
        )


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

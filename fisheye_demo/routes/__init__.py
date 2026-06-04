"""
routes/__init__.py — Blueprint Registration

Tất cả Blueprint phải được đăng ký tại đây.
Thứ tự đăng ký không quan trọng nhưng hãy giữ nhất quán.
"""

from flask import Flask


def register_blueprints(app: Flask) -> None:
    from routes.core import core_bp, register_ui_log_handler
    from routes.detect import detect_bp
    from routes.history import history_bp
    from routes.external_camera import ext_cam_bp
    from routes.examples import examples_bp

    app.register_blueprint(core_bp)
    app.register_blueprint(detect_bp)
    app.register_blueprint(history_bp)
    app.register_blueprint(ext_cam_bp)
    app.register_blueprint(examples_bp)
    
    # Kích hoạt UI log handler sau khi app đã có logger
    register_ui_log_handler()
    
    app.logger.info("All blueprints registered successfully")

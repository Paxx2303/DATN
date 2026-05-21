from .app import app as flask_app
from .app import create_app

__all__ = ["create_app", "flask_app"]

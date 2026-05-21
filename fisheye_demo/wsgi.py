from __future__ import annotations

try:
    from fisheye_demo.app import app
except ModuleNotFoundError:
    from app import app


__all__ = ["app"]

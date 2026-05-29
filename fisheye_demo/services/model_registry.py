from __future__ import annotations

import re
import threading
from pathlib import Path
from typing import Any

try:
    from config import AppSettings, TRAFFIC_CHECKPOINT_NAME, PROJECT_DIR, APP_DIR
    from utils.helpers import utc_now_iso, utc_now_iso_from_timestamp
except ImportError:
    from fisheye_demo.config import AppSettings, TRAFFIC_CHECKPOINT_NAME, PROJECT_DIR, APP_DIR
    from fisheye_demo.utils.helpers import utc_now_iso, utc_now_iso_from_timestamp


class ModelRegistry:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self._model = None
        self._info = {
            "loaded": False,
            "source": "unloaded",
            "loaded_from": None,
            "loaded_from_name": None,
            "selected_key": None,
            "selected_name": None,
            "candidate": None,
            "device": settings.device,
            "error": None,
            "class_names": [],
            "last_loaded_at": None,
        }
        self._lock = threading.Lock()

    def status_snapshot(self) -> dict[str, Any]:
        selectable_models = self.list_selectable_models()
        snapshot = dict(self._info)
        snapshot["candidate"] = self.resolve_candidate_path()
        snapshot["available_models"] = selectable_models
        if not snapshot.get("selected_key") and selectable_models:
            snapshot["selected_key"] = selectable_models[0]["key"]
            snapshot["selected_name"] = selectable_models[0]["name"]
        return snapshot

    def resolve_candidate_path(self) -> str | None:
        default_entry = self.get_model_entry(None)
        return str(default_entry["path"]) if default_entry else None

    def list_available_models(self) -> list[dict[str, Any]]:
        fallback_name = Path(self.settings.fallback_model_name).name.lower()
        entries: list[dict[str, Any]] = []
        used_keys: set[str] = set()
        for path in self._discover_candidate_paths():
            key = self._build_model_key(path, used_keys)
            entries.append(
                {
                    "key": key,
                    "name": path.name,
                    "path": str(path),
                    "rank": self._score_weight_path(path),
                    "last_modified": utc_now_iso_from_timestamp(path.stat().st_mtime),
                    "is_fallback": path.name.lower() == fallback_name,
                }
            )
        return entries

    def list_selectable_models(self) -> list[dict[str, Any]]:
        available_models = self.list_available_models()
        traffic_models = [entry for entry in available_models if entry["name"].lower() == TRAFFIC_CHECKPOINT_NAME]
        if traffic_models:
            return traffic_models[:1]

        fallback_models = [entry for entry in available_models if entry["is_fallback"]]
        return fallback_models[:1]

    def get_model_entry(self, model_key: str | None, *, selectable_only: bool = True) -> dict[str, Any] | None:
        entries = self.list_selectable_models() if selectable_only else self.list_available_models()
        if model_key:
            for entry in entries:
                if entry["key"] == model_key:
                    return entry
            return None
        return entries[0] if entries else None

    def load(self, model_key: str | None = None):
        selected_entry = self.get_model_entry(model_key, selectable_only=False)
        if model_key and selected_entry is None:
            raise ValueError("Unsupported model checkpoint selected.")

        selected_key = selected_entry["key"] if selected_entry else None
        if self._model is not None and self._info.get("selected_key") == selected_key:
            return self._model, dict(self._info)

        with self._lock:
            if self._model is not None and self._info.get("selected_key") == selected_key:
                return self._model, dict(self._info)

            try:
                from ultralytics import YOLO
            except Exception as exc:
                self._info["error"] = f"Ultralytics import failed: {exc}"
                raise RuntimeError(self._info["error"]) from exc

            loaded_from = None
            source = "fallback"

            try:
                if selected_entry is not None:
                    loaded_from = selected_entry["path"]
                    self._model = YOLO(loaded_from)
                    source = "fallback" if selected_entry["is_fallback"] else "custom"
                else:
                    self._model = YOLO(self.settings.fallback_model_name)
                    loaded_from = self.settings.fallback_model_name
            except Exception as exc:
                self._info["error"] = f"Model load failed: {exc}"
                raise RuntimeError(self._info["error"]) from exc

            class_names = self._extract_model_names(self._model)
            self._info.update(
                {
                    "loaded": True,
                    "source": source,
                    "loaded_from": str(loaded_from),
                    "loaded_from_name": Path(str(loaded_from)).name,
                    "selected_key": selected_key,
                    "selected_name": selected_entry["name"] if selected_entry else Path(str(loaded_from)).name,
                    "candidate": self.resolve_candidate_path(),
                    "device": self.settings.device,
                    "error": None,
                    "class_names": class_names,
                    "last_loaded_at": utc_now_iso(),
                }
            )
            return self._model, dict(self._info)

    def _discover_candidate_paths(self) -> list[Path]:
        candidates: list[Path] = []
        seen: set[Path] = set()

        if self.settings.model_path_override:
            override_path = Path(self.settings.model_path_override)
            if override_path.exists():
                resolved_path = override_path.resolve()
                candidates.append(resolved_path)
                seen.add(resolved_path)

        for root in (PROJECT_DIR, APP_DIR):
            if not root.exists():
                continue
            for file_path in root.glob("*.pt"):
                resolved_path = file_path.resolve()
                if resolved_path in seen:
                    continue
                candidates.append(resolved_path)
                seen.add(resolved_path)

        return sorted(
            candidates,
            key=lambda path: (self._score_weight_path(path), path.stat().st_mtime),
            reverse=True,
        )

    @staticmethod
    def _build_model_key(path: Path, used_keys: set[str]) -> str:
        base_key = re.sub(r"[^a-z0-9]+", "-", path.stem.lower()).strip("-") or "model"
        key = base_key
        suffix = 2
        while key in used_keys:
            key = f"{base_key}-{suffix}"
            suffix += 1
        used_keys.add(key)
        return key

    @staticmethod
    def _extract_model_names(model) -> list[str]:
        names = getattr(getattr(model, "model", None), "names", None) or getattr(model, "names", None) or {}
        if isinstance(names, dict):
            return [str(names[idx]) for idx in sorted(names.keys())]
        if isinstance(names, (list, tuple)):
            return [str(name) for name in names]
        return []

    @staticmethod
    def _score_weight_path(path: Path) -> int:
        name = path.name.lower()
        score = 0
        if "fisheye" in name:
            score += 120
        if "best" in name:
            score += 100
        if "resume" in name:
            score += 40
        if "yolo11" in name:
            score += 25
        if name == "yolo11n.pt":
            score -= 250
        return score

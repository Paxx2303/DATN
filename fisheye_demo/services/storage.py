from __future__ import annotations

import io
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from PIL import Image
from flask import url_for

try:
    from config import AppSettings
    from utils.helpers import utc_now_iso, utc_now_iso_from_timestamp
    from recent_image_store import RecentImageStore
except ImportError:
    from fisheye_demo.config import AppSettings
    from fisheye_demo.utils.helpers import utc_now_iso, utc_now_iso_from_timestamp
    from fisheye_demo.recent_image_store import RecentImageStore


def read_uploaded_image(file_storage) -> Image.Image:
    try:
        image = Image.open(file_storage.stream)
        image.load()
        return image.convert("RGB")
    except Exception as exc:
        raise ValueError(f"Invalid image file: {exc}") from exc


def save_uploaded_file(settings: AppSettings, file_storage, suffix: str) -> Path:
    temp_path = settings.upload_dir / f"upload-{uuid.uuid4().hex}{suffix}"
    file_storage.stream.seek(0)
    file_storage.save(temp_path)
    return temp_path


def inspect_video_duration(video_path: Path) -> dict[str, float]:
    try:
        import cv2
    except Exception as exc:
        raise RuntimeError(f"OpenCV import failed: {exc}") from exc

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise ValueError("Cannot inspect uploaded video.")

    try:
        total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        fps = capture.get(cv2.CAP_PROP_FPS) or 25.0
    finally:
        capture.release()

    duration_seconds = total_frames / fps if fps > 0 else 0.0
    return {
        "total_frames": total_frames,
        "fps": float(fps),
        "duration_seconds": float(duration_seconds),
    }


def create_result_dir(settings: AppSettings) -> tuple[str, Path]:
    result_id = f"{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
    result_dir = settings.results_dir / result_id
    result_dir.mkdir(parents=True, exist_ok=True)
    return result_id, result_dir


def write_record(result_dir: Path, record: dict[str, Any]) -> None:
    (result_dir / "metadata.json").write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")


def build_artifact_urls(record: dict[str, Any]) -> dict[str, str]:
    return {
        key: url_for("core.artifact_file", result_id=record["id"], filename=value)
        for key, value in record.get("artifacts", {}).items()
    }


def read_record(results_dir: Path, result_id: str) -> dict[str, Any] | None:
    metadata_path = results_dir / result_id / "metadata.json"
    if not metadata_path.exists():
        return None
    try:
        return json.loads(metadata_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def artifact_mime_type(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".png":
        return "image/png"
    if suffix == ".webp":
        return "image/webp"
    if suffix == ".bmp":
        return "image/bmp"
    if suffix in {".tif", ".tiff"}:
        return "image/tiff"
    return "application/octet-stream"


def serialize_pil_image(image: Image.Image, filename: str) -> bytes:
    suffix = Path(filename).suffix.lower()
    buffer = io.BytesIO()
    if suffix == ".png":
        image.save(buffer, format="PNG")
    elif suffix == ".webp":
        image.save(buffer, format="WEBP", quality=90)
    else:
        image.save(buffer, format="JPEG", quality=92)
    return buffer.getvalue()


def recent_image_metadata_from_record(record: dict[str, Any]) -> dict[str, Any]:
    summary = record.get("summary") or {}
    return {
        "filename": record.get("filename"),
        "summary": summary,
        "source_layout": record.get("source_layout"),
    }


def persist_recent_image(
    recent_image_store: RecentImageStore,
    *,
    record: dict[str, Any],
    image_role: str,
    filename: str,
    image: Image.Image,
) -> None:
    recent_image_store.add_image(
        source_key=f"{record['id']}:{image_role}",
        source_result_id=record["id"],
        task=str(record.get("task") or ""),
        media_type=str(record.get("media_type") or ""),
        image_role=image_role,
        filename=filename,
        mime_type=artifact_mime_type(filename),
        width=image.width,
        height=image.height,
        created_at=str(record.get("created_at") or utc_now_iso()),
        metadata=recent_image_metadata_from_record(record),
        image_bytes=serialize_pil_image(image, filename),
    )


def resolve_recent_image_artifact(record: dict[str, Any]) -> tuple[str, str] | None:
    artifacts = record.get("artifacts") or {}
    media_type = str(record.get("media_type") or "")
    task = str(record.get("task") or "")

    if task == "detect" and media_type == "image" and artifacts.get("annotated"):
        return "annotated", artifacts["annotated"]
    if task == "convert" and media_type == "image" and artifacts.get("fisheye_image"):
        return "fisheye_image", artifacts["fisheye_image"]
    if task == "detect" and media_type == "video" and artifacts.get("preview_annotated"):
        return "preview_annotated", artifacts["preview_annotated"]
    if task == "convert" and media_type == "video" and artifacts.get("preview_fisheye"):
        return "preview_fisheye", artifacts["preview_fisheye"]
    if media_type == "external_camera_grid" and artifacts.get("overview_annotated"):
        return "overview_annotated", artifacts["overview_annotated"]
    return None


def backfill_recent_image_store(settings: AppSettings, recent_image_store: RecentImageStore) -> None:
    store_stats = recent_image_store.stats()
    if store_stats["stored_images"] >= recent_image_store.max_images:
        return

    records = list_records(settings.results_dir, recent_image_store.max_images)
    for record in reversed(records):
        resolved_artifact = resolve_recent_image_artifact(record)
        if resolved_artifact is None:
            continue

        image_role, artifact_name = resolved_artifact
        artifact_path = settings.results_dir / record["id"] / artifact_name
        if not artifact_path.exists():
            continue

        try:
            with Image.open(artifact_path) as image:
                image.load()
                persist_recent_image(
                    recent_image_store,
                    record=record,
                    image_role=image_role,
                    filename=artifact_name,
                    image=image.convert("RGB"),
                )
        except Exception:
            continue


def list_records(results_dir: Path, limit: int) -> list[dict[str, Any]]:
    if not results_dir.exists():
        return []

    candidates = sorted(
        [path for path in results_dir.iterdir() if path.is_dir()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    records = []
    for directory in candidates[:limit]:
        record = read_record(results_dir, directory.name)
        if record:
            records.append(record)
    return records

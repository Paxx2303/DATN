"""
cloud_storage.py — Google Cloud Storage (GCS) integration cho fisheye_demo

Chức năng:
- Upload ảnh annotated lên GCS bucket
- Tự động đặt metadata expires_at = now + 6h
- Xóa ảnh hết hạn (cleanup job)
- Tạo signed URL hoặc public URL
- Fallback graceful khi không có GCS credentials

Cấu hình qua env vars:
  GCS_BUCKET_NAME          — tên bucket (bắt buộc khi dùng GCS)
  GCS_PROJECT_ID           — GCP project ID
  GCS_CREDENTIALS_JSON     — JSON string của service account key (optional, dùng ADC nếu không có)
  FISHEYE_SNAPSHOT_TTL_HOURS — số giờ giữ ảnh (mặc định 6)
  FISHEYE_CLOUD_STORAGE    — "1" để bật, "0" để tắt (mặc định tắt nếu không có bucket)
"""
from __future__ import annotations

import io
import json
import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("fisheye_demo.cloud_storage")

_gcs_client: Any = None
_gcs_bucket: Any = None
_gcs_lock = threading.Lock()
_gcs_enabled: bool | None = None  # None = chưa kiểm tra


def _get_ttl_hours() -> int:
    try:
        return max(1, int(os.getenv("FISHEYE_SNAPSHOT_TTL_HOURS", "6")))
    except (ValueError, TypeError):
        return 6


def _get_bucket_name() -> str | None:
    return os.getenv("GCS_BUCKET_NAME") or os.getenv("FISHEYE_GCS_BUCKET")


def is_enabled() -> bool:
    """Kiểm tra GCS có được bật và cấu hình đúng không."""
    global _gcs_enabled
    if _gcs_enabled is not None:
        return _gcs_enabled

    # Kiểm tra explicit disable
    if os.getenv("FISHEYE_CLOUD_STORAGE", "").strip().lower() in ("0", "false", "no", "off"):
        _gcs_enabled = False
        return False

    bucket_name = _get_bucket_name()
    if not bucket_name:
        _gcs_enabled = False
        return False

    _gcs_enabled = True
    return True


def _init_client() -> tuple[Any, Any]:
    """Khởi tạo GCS client. Thread-safe."""
    global _gcs_client, _gcs_bucket

    with _gcs_lock:
        if _gcs_client is not None and _gcs_bucket is not None:
            return _gcs_client, _gcs_bucket

        try:
            from google.cloud import storage as gcs
        except ImportError:
            raise RuntimeError(
                "google-cloud-storage chưa được cài. Chạy: pip install google-cloud-storage"
            )

        bucket_name = _get_bucket_name()
        if not bucket_name:
            raise RuntimeError("GCS_BUCKET_NAME chưa được cấu hình.")

        credentials_json = os.getenv("GCS_CREDENTIALS_JSON")
        project_id = os.getenv("GCS_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")

        if credentials_json:
            try:
                from google.oauth2 import service_account
                creds_dict = json.loads(credentials_json)
                credentials = service_account.Credentials.from_service_account_info(creds_dict)
                client = gcs.Client(project=project_id, credentials=credentials)
            except Exception as exc:
                logger.warning("GCS credentials JSON parse failed: %s, falling back to ADC", exc)
                client = gcs.Client(project=project_id)
        else:
            # Application Default Credentials (ADC) — tự động trên GCE VM
            client = gcs.Client(project=project_id)

        bucket = client.bucket(bucket_name)
        _gcs_client = client
        _gcs_bucket = bucket
        logger.info("GCS client initialized: bucket=%s project=%s", bucket_name, project_id)
        return client, bucket


def upload_image_bytes(
    image_bytes: bytes,
    object_name: str,
    content_type: str = "image/jpeg",
    detection_id: str | None = None,
    image_role: str = "annotated",
) -> dict[str, Any] | None:
    """
    Upload ảnh lên GCS.

    Returns:
        dict với gcs_public_url, gcs_object_name, expires_at
        hoặc None nếu GCS không được bật
    """
    if not is_enabled():
        return None

    try:
        _, bucket = _init_client()
    except Exception as exc:
        logger.error("GCS init failed: %s", exc)
        return None

    ttl_hours = _get_ttl_hours()
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=ttl_hours)

    try:
        blob = bucket.blob(object_name)
        blob.metadata = {
            "detection_id": detection_id or "",
            "image_role": image_role,
            "expires_at": expires_at.isoformat(),
            "uploaded_at": now.isoformat(),
        }
        blob.upload_from_string(image_bytes, content_type=content_type)

        # Tạo public URL (bucket phải có allUsers read permission)
        public_url = f"https://storage.googleapis.com/{bucket.name}/{object_name}"

        logger.info(
            "GCS upload OK: object=%s size=%d bytes expires=%s",
            object_name,
            len(image_bytes),
            expires_at.isoformat(),
        )

        return {
            "gcs_bucket": bucket.name,
            "gcs_object_name": object_name,
            "gcs_public_url": public_url,
            "expires_at": expires_at.isoformat(),
            "image_role": image_role,
            "detection_id": detection_id,
        }
    except Exception as exc:
        logger.error("GCS upload failed: object=%s error=%s", object_name, exc)
        return None


def upload_pil_image(
    image,  # PIL.Image.Image
    object_name: str,
    quality: int = 88,
    detection_id: str | None = None,
    image_role: str = "annotated",
) -> dict[str, Any] | None:
    """Upload PIL Image lên GCS."""
    if not is_enabled():
        return None

    try:
        import io as _io
        buf = _io.BytesIO()
        image.save(buf, format="JPEG", quality=quality)
        image_bytes = buf.getvalue()
    except Exception as exc:
        logger.error("PIL to bytes failed: %s", exc)
        return None

    return upload_image_bytes(
        image_bytes,
        object_name,
        content_type="image/jpeg",
        detection_id=detection_id,
        image_role=image_role,
    )


def delete_object(object_name: str) -> bool:
    """Xóa một object khỏi GCS."""
    if not is_enabled():
        return False

    try:
        _, bucket = _init_client()
        blob = bucket.blob(object_name)
        blob.delete()
        logger.info("GCS delete OK: object=%s", object_name)
        return True
    except Exception as exc:
        logger.warning("GCS delete failed: object=%s error=%s", object_name, exc)
        return False


def build_object_name(result_id: str, filename: str) -> str:
    """Tạo tên object GCS theo cấu trúc: snapshots/{date}/{result_id}/{filename}"""
    date_prefix = datetime.now(timezone.utc).strftime("%Y/%m/%d")
    return f"snapshots/{date_prefix}/{result_id}/{filename}"


def cleanup_expired_snapshots() -> dict[str, Any]:
    """
    Xóa các ảnh đã hết hạn khỏi GCS và đánh dấu trong DB.
    Nên gọi định kỳ (ví dụ mỗi 30 phút).
    """
    if not is_enabled():
        return {"skipped": True, "reason": "GCS not enabled"}

    try:
        from db import list_expired_cloud_snapshots, mark_cloud_snapshot_deleted
    except ImportError:
        try:
            from fisheye_demo.db import list_expired_cloud_snapshots, mark_cloud_snapshot_deleted
        except ImportError:
            return {"error": "db module not available"}

    expired = list_expired_cloud_snapshots()
    deleted_count = 0
    error_count = 0

    for snapshot in expired:
        object_name = snapshot.get("gcs_object_name", "")
        snapshot_id = snapshot.get("id")
        if not object_name or not snapshot_id:
            continue

        success = delete_object(object_name)
        if success:
            mark_cloud_snapshot_deleted(snapshot_id)
            deleted_count += 1
        else:
            error_count += 1

    logger.info(
        "GCS cleanup: expired=%d deleted=%d errors=%d",
        len(expired),
        deleted_count,
        error_count,
    )
    return {
        "expired_found": len(expired),
        "deleted": deleted_count,
        "errors": error_count,
    }


def get_bucket_stats() -> dict[str, Any]:
    """Thống kê bucket (số object, dung lượng ước tính)."""
    if not is_enabled():
        return {"enabled": False}

    try:
        _, bucket = _init_client()
        blobs = list(bucket.list_blobs(prefix="snapshots/"))
        total_size = sum(b.size or 0 for b in blobs)
        return {
            "enabled": True,
            "bucket": bucket.name,
            "object_count": len(blobs),
            "total_size_mb": round(total_size / 1024 / 1024, 2),
            "ttl_hours": _get_ttl_hours(),
        }
    except Exception as exc:
        return {"enabled": True, "error": str(exc)}


# ── Background cleanup thread ────────────────────────────────────────────────

_cleanup_thread: threading.Thread | None = None
_cleanup_stop = threading.Event()


def start_cleanup_scheduler(interval_minutes: int = 30) -> None:
    """Khởi động background thread tự động xóa ảnh hết hạn."""
    global _cleanup_thread

    if not is_enabled():
        logger.info("GCS cleanup scheduler skipped (GCS not enabled)")
        return

    if _cleanup_thread is not None and _cleanup_thread.is_alive():
        return

    _cleanup_stop.clear()

    def _loop():
        logger.info("GCS cleanup scheduler started (interval=%dm)", interval_minutes)
        while not _cleanup_stop.wait(timeout=interval_minutes * 60):
            try:
                result = cleanup_expired_snapshots()
                logger.info("GCS cleanup cycle: %s", result)
            except Exception as exc:
                logger.error("GCS cleanup error: %s", exc)

    _cleanup_thread = threading.Thread(
        target=_loop,
        daemon=True,
        name="gcs-cleanup-scheduler",
    )
    _cleanup_thread.start()


def stop_cleanup_scheduler() -> None:
    _cleanup_stop.set()

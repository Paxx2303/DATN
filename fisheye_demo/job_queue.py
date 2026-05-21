"""
job_queue.py — Async background job queue for video processing.

Sử dụng ThreadPoolExecutor để xử lý video ở background thay vì block HTTP request.
Job states: pending → running → done | failed
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Callable

logger = logging.getLogger("fisheye_demo.job_queue")

_JOB_RETENTION_SECONDS = 3600  # Giữ job result trong 1 giờ


class JobState:
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class VideoJobQueue:
    """Thread-safe job queue cho video processing với giới hạn concurrency."""

    def __init__(self, max_workers: int = 2, max_queue_size: int = 10) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="video-job")
        self._max_queue_size = max_queue_size
        self._jobs: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._futures: dict[str, Future] = {}  # type: ignore[type-arg]

        # Cleanup thread để xóa job cũ
        self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True, name="job-cleanup")
        self._cleanup_thread.start()

    # ── Public API ────────────────────────────────────────────────────────────

    def submit(
        self,
        fn: Callable[..., Any],
        *args: Any,
        job_type: str = "video_detect",
        meta: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> str:
        """Submit một job vào queue. Trả về job_id ngay lập tức."""
        with self._lock:
            pending_count = sum(
                1 for j in self._jobs.values()
                if j["status"] in (JobState.PENDING, JobState.RUNNING)
            )
            if pending_count >= self._max_queue_size:
                raise RuntimeError(
                    f"Job queue full ({pending_count}/{self._max_queue_size} active jobs). "
                    "Try again later."
                )

            job_id = uuid.uuid4().hex
            self._jobs[job_id] = {
                "job_id": job_id,
                "job_type": job_type,
                "status": JobState.PENDING,
                "created_at": _utc_iso(),
                "started_at": None,
                "finished_at": None,
                "result": None,
                "error": None,
                "meta": meta or {},
            }

        future = self._executor.submit(self._run_job, job_id, fn, args, kwargs)
        with self._lock:
            self._futures[job_id] = future

        logger.info("Job submitted: job_id=%s type=%s", job_id, job_type)
        return job_id

    def get(self, job_id: str) -> dict[str, Any] | None:
        """Lấy trạng thái và kết quả của job. Trả về None nếu không tồn tại."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            return dict(job)

    def list_recent(self, limit: int = 20) -> list[dict[str, Any]]:
        """Danh sách các jobs gần nhất, không bao gồm result payload (để giảm payload)."""
        with self._lock:
            jobs = sorted(
                self._jobs.values(),
                key=lambda j: j["created_at"],
                reverse=True,
            )[:limit]
        return [
            {k: v for k, v in j.items() if k != "result"}
            for j in jobs
        ]

    def cancel(self, job_id: str) -> bool:
        """Hủy job đang pending. Trả về True nếu cancel thành công."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job["status"] != JobState.PENDING:
                return False
            future = self._futures.get(job_id)
            if future and future.cancel():
                job["status"] = JobState.FAILED
                job["error"] = "Cancelled by user"
                job["finished_at"] = _utc_iso()
                logger.info("Job cancelled: job_id=%s", job_id)
                return True
        return False

    def stats(self) -> dict[str, int]:
        with self._lock:
            counts: dict[str, int] = {
                JobState.PENDING: 0,
                JobState.RUNNING: 0,
                JobState.DONE: 0,
                JobState.FAILED: 0,
            }
            for job in self._jobs.values():
                counts[job["status"]] = counts.get(job["status"], 0) + 1
        return counts

    def shutdown(self, wait: bool = True) -> None:
        self._executor.shutdown(wait=wait)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _run_job(self, job_id: str, fn: Callable[..., Any], args: tuple, kwargs: dict) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job["status"] = JobState.RUNNING
            job["started_at"] = _utc_iso()

        logger.info("Job started: job_id=%s", job_id)
        try:
            result = fn(*args, **kwargs)
            with self._lock:
                job = self._jobs[job_id]
                job["status"] = JobState.DONE
                job["result"] = result
                job["finished_at"] = _utc_iso()
            logger.info("Job done: job_id=%s", job_id)
        except Exception as exc:
            with self._lock:
                job = self._jobs.get(job_id)
                if job:
                    job["status"] = JobState.FAILED
                    job["error"] = str(exc)
                    job["finished_at"] = _utc_iso()
            logger.exception("Job failed: job_id=%s error=%s", job_id, exc)

    def _cleanup_loop(self) -> None:
        while True:
            time.sleep(300)  # Run every 5 minutes
            try:
                self._evict_old_jobs()
            except Exception:
                pass

    def _evict_old_jobs(self) -> None:
        now = time.time()
        with self._lock:
            to_delete = []
            for job_id, job in self._jobs.items():
                if job["status"] not in (JobState.DONE, JobState.FAILED):
                    continue
                finished = job.get("finished_at")
                if finished:
                    try:
                        finished_ts = datetime.fromisoformat(finished.replace("Z", "+00:00")).timestamp()
                        if now - finished_ts > _JOB_RETENTION_SECONDS:
                            to_delete.append(job_id)
                    except Exception:
                        pass
            for job_id in to_delete:
                del self._jobs[job_id]
                self._futures.pop(job_id, None)
        if to_delete:
            logger.info("Evicted %d old jobs", len(to_delete))


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

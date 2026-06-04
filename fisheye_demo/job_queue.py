"""
job_queue.py — Async Video Processing Queue

THIẾT KẾ:
- VideoJobQueue là singleton, khởi tạo một lần khi import.
- _jobs: dict[str, JobRecord] — lưu trạng thái trong RAM (đủ cho demo).
- ThreadPoolExecutor với max_workers = Config.JOB_MAX_WORKERS.
- submit_job() trả về job_id ngay lập tức (non-blocking).
- get_status() trả về dict với progress%, eta, error_message.
"""

import uuid
import time
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from config import Config

logger = logging.getLogger(__name__)


@dataclass
class JobRecord:
    job_id: str
    status: str = "pending"        # pending | running | done | failed
    progress: float = 0.0          # 0.0 – 100.0
    result_id: Optional[str] = None
    error_message: Optional[str] = None
    submitted_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    params: dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "progress": round(self.progress, 1),
            "result_id": self.result_id,
            "error_message": self.error_message,
            "submitted_at": self.submitted_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "elapsed": (
                (self.finished_at or time.time()) - (self.started_at or self.submitted_at)
            ),
        }


class VideoJobQueue:
    """
    Thread-safe job queue cho video processing.
    """

    def __init__(self, max_workers: int = 2):
        self._jobs: dict[str, JobRecord] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="video_worker",
        )
        logger.info(f"VideoJobQueue initialized (max_workers={max_workers})")

    def submit_job(self, worker_fn: Callable, params: dict) -> str:
        """
        Submit một job mới.
        
        Parameters
        ----------
        worker_fn : Hàm xử lý video, signature: (job_id, params, progress_cb) -> str
                    Phải nhận progress_callback để báo cáo tiến độ.
        params    : Dict tham số cho worker (input_path, output_path, model_key, ...)
        
        Returns
        -------
        str : job_id (UUID4 string)
        """
        job_id = str(uuid.uuid4())
        record = JobRecord(job_id=job_id, params=params)
        
        with self._lock:
            self._jobs[job_id] = record
        
        # Submit vào thread pool — non-blocking
        future = self._executor.submit(self._run_job, job_id, worker_fn, params)
        # Log lỗi nếu future raise exception
        future.add_done_callback(lambda f: self._on_future_done(job_id, f))
        
        logger.info(f"Job {job_id} submitted (pending)")
        return job_id

    def _run_job(self, job_id: str, worker_fn: Callable, params: dict) -> None:
        """Chạy trong worker thread. Cập nhật status → running → done/failed."""
        record = self._jobs[job_id]
        record.status = "running"
        record.started_at = time.time()
        logger.info(f"Job {job_id} started")

        def progress_callback(pct: float) -> None:
            """Worker gọi hàm này để báo tiến độ (0–100)."""
            record.progress = min(pct, 99.0)  # 100.0 chỉ set khi done

        try:
            result_id = worker_fn(job_id=job_id, params=params, progress_cb=progress_callback)
            record.status = "done"
            record.progress = 100.0
            record.result_id = result_id
            record.finished_at = time.time()
            logger.info(f"Job {job_id} done → result_id={result_id}")
        except Exception as exc:
            record.status = "failed"
            record.error_message = str(exc)
            record.finished_at = time.time()
            logger.error(f"Job {job_id} failed: {exc}", exc_info=True)

    def _on_future_done(self, job_id: str, future) -> None:
        """Callback khi future hoàn thành (catch unhandled exceptions)."""
        exc = future.exception()
        if exc:
            record = self._jobs.get(job_id)
            if record and record.status != "failed":
                record.status = "failed"
                record.error_message = str(exc)

    def get_status(self, job_id: str) -> Optional[dict]:
        """Trả về trạng thái job. None nếu không tìm thấy."""
        record = self._jobs.get(job_id)
        return record.to_dict() if record else None

    def get_all_jobs(self) -> list[dict]:
        """Trả về tất cả jobs, mới nhất trước."""
        with self._lock:
            jobs = list(self._jobs.values())
        return sorted(
            [j.to_dict() for j in jobs],
            key=lambda x: x["submitted_at"],
            reverse=True,
        )

    def cleanup_old_jobs(self, max_age_seconds: int = 3600) -> int:
        """Xóa các job cũ hơn max_age_seconds khỏi RAM. Trả về số job đã xóa."""
        cutoff = time.time() - max_age_seconds
        with self._lock:
            old_ids = [
                jid for jid, rec in self._jobs.items()
                if rec.finished_at and rec.finished_at < cutoff
            ]
            for jid in old_ids:
                del self._jobs[jid]
        return len(old_ids)

    def shutdown(self) -> None:
        """Graceful shutdown — đợi jobs đang chạy hoàn thành."""
        logger.info("Shutting down VideoJobQueue...")
        self._executor.shutdown(wait=True)


# Singleton instance
video_job_queue = VideoJobQueue(max_workers=Config.JOB_MAX_WORKERS)

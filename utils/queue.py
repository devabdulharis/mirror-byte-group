"""
Download Queue System — manajemen download task dengan support:
- Multiple concurrent downloads (per-user dan global)
- Pause / Resume (untuk aiohttp-based downloads)
- Stop / Cancel (semua jenis download)
- Tracking status per task
"""

import os
import time
import uuid
import asyncio
import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    PAUSED = "paused"
    RESUMING = "resuming"
    STOPPED = "stopped"
    COMPLETED = "completed"
    FAILED = "failed"

    def emoji(self) -> str:
        return {
            "pending": "⏳",
            "downloading": "⬇️",
            "paused": "⏸️",
            "resuming": "▶️",
            "stopped": "🛑",
            "completed": "✅",
            "failed": "❌",
        }.get(self.value, "❓")


@dataclass
class DownloadTask:
    """Representasi satu task download"""
    id: str
    user_id: int
    chat_id: int
    url: str
    platform: str
    filename_hint: str = ""
    status: TaskStatus = TaskStatus.PENDING
    progress_pct: float = 0.0          # 0.0 – 100.0
    downloaded_bytes: int = 0
    total_bytes: int = 0
    speed_bps: float = 0.0
    eta_secs: float = 0.0
    file_paths: list = field(default_factory=list)
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None

    # Internal control events
    _stop_event: asyncio.Event = field(default_factory=asyncio.Event)
    _pause_event: asyncio.Event = field(default_factory=asyncio.Event)

    # ── control ──────────────────────────────────────────────────────
    def request_stop(self):
        self._stop_event.set()

    def request_pause(self):
        self._pause_event.set()

    def request_resume(self):
        self._pause_event.clear()

    @property
    def should_stop(self) -> bool:
        return self._stop_event.is_set()

    @property
    def is_paused(self) -> bool:
        return self._pause_event.is_set() and not self._stop_event.is_set()

    async def checkpoint(self):
        """
        Panggil secara periodik di dalam loop download.
        - Jika ada sinyal stop → raise TaskStopped
        - Jika ada sinyal pause → sleep sampai resume atau stop
        """
        if self._stop_event.is_set():
            raise TaskStoppedError("Download dihentikan oleh user")

        while self._pause_event.is_set() and not self._stop_event.is_set():
            self.status = TaskStatus.PAUSED
            await asyncio.sleep(0.5)

        if self._stop_event.is_set():
            raise TaskStoppedError("Download dihentikan oleh user")
        if self.status == TaskStatus.PAUSED:
            self.status = TaskStatus.DOWNLOADING  # balik ke downloading setelah resume

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "url_short": self.url[:60] + ("…" if len(self.url) > 60 else ""),
            "platform": self.platform,
            "filename_hint": self.filename_hint,
            "status": self.status.value,
            "status_emoji": self.status.emoji(),
            "progress": f"{self.progress_pct:.1f}%",
            "downloaded": self.downloaded_bytes,
            "total": self.total_bytes,
            "speed": self.speed_bps,
            "eta": self.eta_secs,
            "error": self.error,
            "file_paths": self.file_paths,
        }


class TaskStoppedError(Exception):
    """Raise ketika user meminta stop."""
    pass


class DownloadQueue:
    """
    Queue manager global.

    Fitur:
    - Buat task baru → auto-antri
    - Batasi max concurrent download GLOBAL
    - Batasi max concurrent PER-USER
    - Kontrol pause/resume/stop per task
    """

    def __init__(self, max_concurrent_global: int = 3, max_per_user: int = 2):
        self._tasks: dict[str, DownloadTask] = {}
        self._user_tasks: dict[int, list[str]] = {}
        self._semaphore = asyncio.Semaphore(max_concurrent_global)
        self._max_global = max_concurrent_global
        self._max_per_user = max_per_user
        self._active_count = 0

    # ── CRUD ─────────────────────────────────────────────────────────

    def create_task(self, user_id: int, chat_id: int,
                    url: str, platform: str, filename_hint: str = "") -> DownloadTask:
        task = DownloadTask(
            id=uuid.uuid4().hex[:8],
            user_id=user_id,
            chat_id=chat_id,
            url=url,
            platform=platform,
            filename_hint=filename_hint,
        )
        self._tasks[task.id] = task
        self._user_tasks.setdefault(user_id, []).append(task.id)
        logger.info(f"Task {task.id} dibuat: url={url[:50]}… user={user_id} plat={platform}")
        return task

    def get_task(self, task_id: str) -> Optional[DownloadTask]:
        return self._tasks.get(task_id)

    def get_user_tasks(self, user_id: int) -> list[DownloadTask]:
        return [self._tasks[tid] for tid in self._user_tasks.get(user_id, [])
                if tid in self._tasks]

    def get_active_tasks(self) -> list[DownloadTask]:
        return [t for t in self._tasks.values()
                if t.status in (TaskStatus.DOWNLOADING, TaskStatus.PAUSED, TaskStatus.PENDING)]

    def get_all_tasks(self) -> list[DownloadTask]:
        return list(self._tasks.values())

    def user_active_count(self, user_id: int) -> int:
        return sum(1 for t in self.get_user_tasks(user_id)
                   if t.status in (TaskStatus.DOWNLOADING, TaskStatus.PENDING))

    def can_user_download(self, user_id: int) -> bool:
        """Cek apakah user masih boleh download (tidak melebihi max_per_user)"""
        return self.user_active_count(user_id) < self._max_per_user

    # ── Kontrol ──────────────────────────────────────────────────────

    def pause_task(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        if not task:
            return False
        if task.status in (TaskStatus.DOWNLOADING,):
            logger.info(f"Task {task_id} → PAUSE")
            task.status = TaskStatus.PAUSED
            task.request_pause()
            return True
        return False

    def resume_task(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        if not task:
            return False
        if task.status in (TaskStatus.PAUSED,):
            logger.info(f"Task {task_id} → RESUME")
            task.status = TaskStatus.DOWNLOADING
            task.request_resume()
            return True
        return False

    def stop_task(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        if not task:
            return False
        if task.status in (TaskStatus.DOWNLOADING, TaskStatus.PAUSED,
                           TaskStatus.PENDING, TaskStatus.RESUMING):
            logger.info(f"Task {task_id} → STOP")
            task.status = TaskStatus.STOPPED
            task.request_stop()
            return True
        return False

    # ── Semaphore wrapper ────────────────────────────────────────────

    async def run_with_semaphore(self, coro, task: DownloadTask):
        """Jalankan coroutine dengan semaphore global"""
        async with self._semaphore:
            self._active_count += 1
            try:
                return await coro
            finally:
                self._active_count -= 1

    # ── Cleanup ──────────────────────────────────────────────────────

    def cleanup_completed(self, user_id: Optional[int] = None):
        """Hapus task yang sudah complete/failed/stopped dari memory"""
        if user_id:
            ids = list(self._user_tasks.get(user_id, []))
        else:
            ids = list(self._tasks.keys())

        done_statuses = {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.STOPPED}
        for tid in ids:
            task = self._tasks.get(tid)
            if task and task.status in done_statuses:
                del self._tasks[tid]
                if user_id and tid in self._user_tasks.get(user_id, []):
                    self._user_tasks[user_id].remove(tid)

    def cleanup_all_completed(self):
        for uid in list(self._user_tasks.keys()):
            self.cleanup_completed(uid)


# ── Global singleton ─────────────────────────────────────────────────
queue: DownloadQueue = DownloadQueue(max_concurrent_global=3)

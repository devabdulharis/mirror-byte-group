"""
Auto Cleanup — hapus file lama secara periodik.

Fitur:
- Hapus file download yang sudah lebih dari N jam
- Hapus file .part (partial download yang ditinggalkan)
- Hapus direktori kosong
- Log rotation sederhana
- Bersihkan task queue yang sudah selesai
"""

import os
import time
import shutil
import logging
import asyncio
from config import Config
from utils.queue import queue

logger = logging.getLogger(__name__)

# File dianggap "lama" jika lebih dari 6 jam tidak diakses
MAX_FILE_AGE_HOURS = 6
# File .part dianggap abandoned jika lebih dari 2 jam
MAX_PART_AGE_HOURS = 2
# Interval pengecekan (dalam detik)
CHECK_INTERVAL = 3600  # 1 jam


def clean_download_dir(download_path: str = None) -> dict:
    """
    Hapus file-file lama dari direktori download.
    Returns dict dengan statistik.
    """
    path = download_path or Config.DOWNLOAD_PATH
    if not os.path.exists(path):
        return {"deleted": 0, "freed_bytes": 0, "errors": 0}

    now = time.time()
    max_file_age = MAX_FILE_AGE_HOURS * 3600
    max_part_age = MAX_PART_AGE_HOURS * 3600

    deleted = 0
    freed = 0
    errors = 0

    for root, dirs, files in os.walk(path, topdown=False):
        # Hapus file lama
        for fname in files:
            fpath = os.path.join(root, fname)
            try:
                stat = os.stat(fpath)
                age = now - stat.st_mtime

                # File .part: lebih agresif
                if fname.endswith('.part'):
                    if age > max_part_age:
                        freed += stat.st_size
                        os.remove(fpath)
                        deleted += 1
                        logger.info(f"Cleanup: hapus partial file {fpath} (age={age/3600:.1f}h)")
                # File biasa: hapus jika > max age
                elif age > max_file_age:
                    freed += stat.st_size
                    os.remove(fpath)
                    deleted += 1
                    logger.info(f"Cleanup: hapus file lama {fpath} (age={age/3600:.1f}h)")
            except OSError as e:
                errors += 1
                logger.warning(f"Cleanup error: {fpath}: {e}")

        # Hapus direktori kosong (kecuali root)
        if root != path:
            try:
                if not os.listdir(root):
                    os.rmdir(root)
                    logger.info(f"Cleanup: hapus dir kosong {root}")
            except OSError:
                pass

    return {"deleted": deleted, "freed_bytes": freed, "errors": errors}


def clean_queue_tasks():
    """Bersihkan task queue yang sudah selesai/expired"""
    before = len(queue.get_all_tasks())
    queue.cleanup_all_completed()
    after = len(queue.get_all_tasks())
    if before != after:
        logger.info(f"Cleanup queue: {before - after} task dibersihkan")


async def periodic_cleanup():
    """
    Background task yang jalan setiap CHECK_INTERVAL.
    Panggil via asyncio.create_task() di main().
    """
    logger.info(f"Periodic cleanup started (interval={CHECK_INTERVAL}s)")
    while True:
        try:
            await asyncio.sleep(CHECK_INTERVAL)
            logger.info("Running periodic cleanup...")

            # 1. Hapus file lama
            stats = clean_download_dir()
            if stats["deleted"] > 0:
                from utils.helpers import format_size
                logger.info(
                    f"Cleanup files: {stats['deleted']} file dihapus "
                    f"({format_size(stats['freed_bytes'])})"
                )

            # 2. Bersihkan queue
            clean_queue_tasks()

        except asyncio.CancelledError:
            logger.info("Periodic cleanup cancelled")
            break
        except Exception as e:
            logger.error(f"Periodic cleanup error: {e}")

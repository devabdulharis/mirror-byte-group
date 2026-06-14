"""
Mirror Progress Tracker — progress bar untuk upload/mirror ke berbagai platform.
Mirip dengan ProgressTracker untuk download tapi untuk upload.
"""

import time
import logging
from telegram import Message

logger = logging.getLogger(__name__)


class MirrorProgressTracker:
    """
    Melacak progress upload/mirror dan update pesan Telegram.
    """

    def __init__(self, message: Message, platform: str = "Upload"):
        self.message = message
        self.platform = platform
        self.start_time = time.time()
        self.last_update = -999
        self.last_bytes = 0
        self._spinner_idx = 0
        self._last_speed_ts = 0
        self._last_speed_bytes = 0

    def _get_spinner(self) -> str:
        frames = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
        frame = frames[self._spinner_idx % len(frames)]
        self._spinner_idx += 1
        return frame

    def _progress_bar(self, current: int, total: int, width: int = 12) -> str:
        if total == 0:
            return f"{self._get_spinner()} [░░░░░░░░░░░░]"

        percent = current / total
        filled = int(width * percent)
        bar = '█' * filled + '▒' * (width - filled)

        if percent >= 1.0:
            return f"✅ [{bar}] 100%"

        return f"{self._get_spinner()} [{bar}] {percent*100:.0f}%"

    async def update(self, current: int, total: int, filename: str = ""):
        """Update progress — throttle 1 detik"""
        now = time.time()

        if self.last_update > 0 and now - self.last_update < 1.0:
            return

        if self._last_speed_ts > 0:
            interval = now - self._last_speed_ts
            speed = (current - self._last_speed_bytes) / max(interval, 0.1)
        else:
            speed = 0

        self._last_speed_ts = now
        self._last_speed_bytes = current
        self.last_update = now

        elapsed = now - self.start_time

        # ETA
        eta_str = ""
        if speed > 0 and total > 0 and current < total:
            eta = (total - current) / speed
            if eta > 60:
                eta_str = f" ETA: {int(eta//60)}m {int(eta%60)}s"
            else:
                eta_str = f" ETA: {int(eta)}s"

        from utils.helpers import format_size
        bar = self._progress_bar(current, total)

        text = (
            f"📤 **Upload ke {self.platform}**\n\n"
            f"{bar}\n\n"
            f"📦 {format_size(current)} / {format_size(total)}"
            f"{eta_str}\n"
            f"⚡ {format_size(int(speed))}/s\n"
            f"⏱ {int(elapsed)}s"
        )

        if filename:
            text += f"\n📁 `{filename[:40]}`"

        try:
            await self.message.edit_text(text)
        except Exception:
            pass

    async def complete(self, filename: str = "", extra_info: str = ""):
        """Tampilkan pesan sukses"""
        from utils.helpers import format_size
        elapsed = time.time() - self.start_time

        text = (
            f"✅ **Upload ke {self.platform} Selesai**\n\n"
            f"📁 `{filename}`\n"
            f"⏱ {int(elapsed)}s"
        )
        if extra_info:
            text += f"\n{extra_info}"

        try:
            await self.message.edit_text(text)
        except Exception:
            pass

    async def error(self, err_msg: str, filename: str = ""):
        """Tampilkan pesan error"""
        text = f"❌ **Upload ke {self.platform} Gagal**\n\n"
        if filename:
            text += f"📁 `{filename}`\n"
        text += f"Error: `{err_msg}`"

        try:
            await self.message.edit_text(text)
        except Exception:
            pass

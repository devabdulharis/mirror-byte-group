import time
from telegram import Message
import asyncio

class ProgressTracker:
    def __init__(self, message: Message, action: str = "Downloading"):
        self.message = message
        self.action = action
        self.start_time = time.time()
        self.last_update = -999  # Biar update PERTAMA selalu keproses
        self.last_bytes = 0
        self._spinner_idx = 0
        self._wave_offset = 0
        self._last_speed_ts = 0
        self._last_speed_bytes = 0

    def _get_spinner(self) -> str:
        frames = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
        frame = frames[self._spinner_idx % len(frames)]
        self._spinner_idx += 1
        return frame

    def create_progress_bar(self, current: int, total: int, width: int = 14) -> str:
        if total == 0:
            # Wave animation ketika ukuran total belum diketahui
            self._wave_offset = (self._wave_offset + 1) % (width * 2)
            wave_pos = self._wave_offset if self._wave_offset < width else (width * 2 - self._wave_offset)
            bar_list = ['░'] * width
            bar_list[wave_pos] = '▒'
            if wave_pos > 0:
                bar_list[wave_pos - 1] = '▓'
            if wave_pos < width - 1:
                bar_list[wave_pos + 1] = '▓'
            bar = ''.join(bar_list)
            return f"{self._get_spinner()} [{bar}]"

        percent = current / total
        filled = width * percent
        full_blocks = int(filled)

        bar_list = ['░'] * width

        for i in range(full_blocks):
            bar_list[i] = '█'

        if full_blocks < width:
            remainder = filled - full_blocks
            if remainder > 0:
                grad = ['▏', '▎', '▍', '▌', '▋', '▊', '▉']
                idx = min(int(remainder * len(grad)), len(grad) - 1)
                bar_list[full_blocks] = grad[idx]

        bar = ''.join(bar_list)

        if percent >= 1.0:
            return f"[✓] [{bar}] 100%"

        return f"{self._get_spinner()} [{bar}] {percent*100:.0f}%"

    async def update(self, current: int, total: int, extra_info: str = ""):
        """Update progress — throttle 0.8 detik biar animasi responsif"""
        now = time.time()

        # Update pertama: jangan throttle
        # Update selanjutnya: throttle 0.8 detik
        if self.last_update > 0 and now - self.last_update < 0.8:
            return

        # Hitung kecepatan berdasarkan interval update sebelumnya (bukan dari start)
        if self._last_speed_ts > 0:
            interval = now - self._last_speed_ts
            speed = (current - self._last_speed_bytes) / max(interval, 0.1)
        else:
            speed = 0

        self._last_speed_ts = now
        self._last_speed_bytes = current
        self.last_update = now
        self.last_bytes = current
        elapsed = now - self.start_time

        # ETA
        if speed > 0 and total > 0 and current < total:
            eta = (total - current) / speed
            if eta > 3600:
                eta_str = f"{int(eta//3600)}j {int((eta%3600)//60)}m"
            elif eta > 60:
                eta_str = f"{int(eta//60)}m {int(eta%60)}s"
            else:
                eta_str = f"{int(eta)}s"
        else:
            eta_str = "..."

        from utils.helpers import format_size

        bar_line = self.create_progress_bar(current, total)

        if total > 0:
            text = (
                f"⬇ {self.action}\n\n"
                f"{bar_line}\n\n"
                f"Size: {format_size(current)} / {format_size(total)}\n"
                f"Speed: {format_size(int(speed))}/s  ETA: {eta_str}  Elapsed: {int(elapsed)}s"
            )
        else:
            text = (
                f"⬇ {self.action}\n\n"
                f"{bar_line}\n\n"
                f"Downloaded: {format_size(current)}\n"
                f"Elapsed: {int(elapsed)}s"
            )

        if extra_info:
            text += f"\n\n{extra_info}"

        try:
            await self.message.edit_text(text)
        except Exception:
            pass


class DownloadProgress:
    """Hook untuk yt-dlp progress (dipanggil dari thread, schedule ke event loop)"""
    def __init__(self, tracker: ProgressTracker):
        self.tracker = tracker
        # Loop WAJIB di-capture di sini (dari main thread),
        # karena __call__ nanti jalan di thread yt-dlp
        self.loop = asyncio.get_event_loop()

    def __call__(self, d: dict):
        if d['status'] == 'downloading':
            current = d.get('downloaded_bytes', 0)
            total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
            filename = d.get('filename', '').split('/')[-1] or d.get('info', {}).get('title', '')

            asyncio.run_coroutine_threadsafe(
                self.tracker.update(current, total, f"File: {filename[:50]}"),
                self.loop
            )

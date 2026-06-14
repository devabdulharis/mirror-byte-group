import os
import re
import aiohttp
import aiofiles
import asyncio
import yt_dlp
from urllib.parse import urlparse, unquote
from config import Config
from utils.helpers import sanitize_filename, ensure_download_dir
from utils.progress import ProgressTracker, DownloadProgress
from utils.queue import DownloadTask, TaskStoppedError


class GeneralDownloader:
    def __init__(self):
        ensure_download_dir()

    async def get_file_info(self, url: str) -> dict:
        """Get info dari URL umum"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.head(url, allow_redirects=True,
                                         timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    filename = self._extract_filename(url, resp.headers)
                    content_type = resp.headers.get('content-type', 'unknown')
                    size = int(resp.headers.get('content-length', 0))

                    return {
                        'filename': filename,
                        'content_type': content_type,
                        'size': size,
                        'url': str(resp.url),
                        'supports_resume': 'bytes' in resp.headers.get('accept-ranges', '')
                    }
        except Exception:
            return {
                'filename': sanitize_filename(url.split('/')[-1]) or 'download',
                'content_type': 'unknown',
                'size': 0,
                'url': url,
                'supports_resume': False
            }

    async def download(self, url: str, filename: str = None,
                        progress_tracker: ProgressTracker = None,
                        task: DownloadTask = None) -> dict:
        """
        Download file dari URL langsung.

        Args:
            url: URL sumber
            filename: Nama file output (opsional)
            progress_tracker: Tracker untuk progress bar
            task: DownloadTask untuk kontrol pause/resume/stop
        """

        # Coba dulu dengan yt-dlp untuk platform yang didukung
        try:
            result = await self._try_ytdlp(url, progress_tracker, task)
            if result:
                return result
        except TaskStoppedError:
            raise
        except Exception:
            pass

        # Direct download dengan support pause/resume/stop
        info = await self.get_file_info(url)
        safe_filename = filename or sanitize_filename(info['filename'])
        file_path = os.path.join(Config.DOWNLOAD_PATH, safe_filename)
        part_path = file_path + ".part"

        # Cek partial download untuk resume
        resume_from = 0
        if os.path.exists(part_path) and info.get('supports_resume', False):
            resume_from = os.path.getsize(part_path)
            mode = 'ab'  # append mode
        elif os.path.exists(part_path):
            # Server tidak support resume, mulai ulang
            os.remove(part_path)
            mode = 'wb'
        else:
            mode = 'wb'

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        }
        if resume_from > 0:
            headers['Range'] = f'bytes={resume_from}-'

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers,
                                    allow_redirects=True,
                                    timeout=aiohttp.ClientTimeout(total=7200)) as resp:
                # Kalau server gak support range, resp 200 = full content
                if resp.status == 200:
                    resume_from = 0
                    mode = 'wb'

                total = int(resp.headers.get('content-length', 0))
                if resume_from > 0 and total > 0:
                    # Content-length setelah range adalah sisa bytes
                    total = resume_from + total

                downloaded = resume_from

                async with aiofiles.open(part_path, mode) as f:
                    async for chunk in resp.content.iter_chunked(65536):
                        # Cek pause/stop setiap chunk
                        if task:
                            await task.checkpoint()

                        await f.write(chunk)
                        downloaded += len(chunk)

                        if task:
                            task.downloaded_bytes = downloaded
                            task.total_bytes = total
                            if total > 0:
                                task.progress_pct = (downloaded / total) * 100

                        if progress_tracker:
                            await progress_tracker.update(downloaded, total)

        # Selesai: rename part → file asli
        if os.path.exists(part_path):
            os.rename(part_path, file_path)

        file_size = os.path.getsize(file_path)

        return {
            'files': [file_path],
            'total_size': file_size,
            'count': 1
        }

    async def _try_ytdlp(self, url: str, progress_tracker: ProgressTracker = None,
                          task: DownloadTask = None) -> dict:
        """Coba download dengan yt-dlp (mendukung 1000+ platform)"""
        output_template = os.path.join(Config.DOWNLOAD_PATH, '%(title)s.%(ext)s')

        hooks = []
        if progress_tracker:
            hooks.append(DownloadProgress(progress_tracker))

        # Hook untuk stop signal
        if task:
            def stop_hook(d):
                if task.should_stop:
                    raise yt_dlp.utils.DownloadError("STOPPED_BY_USER")
            hooks.append(stop_hook)

        ydl_opts = {
            'format': 'bestvideo+bestaudio/best',
            'outtmpl': output_template,
            'merge_output_format': 'mp4',
            'progress_hooks': hooks,
            'quiet': True,
            'no_warnings': True,
        }

        return await asyncio.to_thread(self._sync_ytdlp, url, ydl_opts, task)

    def _sync_ytdlp(self, url: str, ydl_opts: dict, task: DownloadTask = None) -> dict:
        """Sync yt-dlp download (dijalankan di thread)"""
        downloaded_files = []

        def my_hook(d):
            if d['status'] == 'finished':
                downloaded_files.append(d['filename'])

        ydl_opts['progress_hooks'] = ydl_opts.get('progress_hooks', []) + [my_hook]

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
        except yt_dlp.utils.DownloadError as e:
            if "STOPPED_BY_USER" in str(e):
                raise TaskStoppedError("Download dihentikan oleh user")
            raise

        if downloaded_files:
            total_size = sum(os.path.getsize(f) for f in downloaded_files if os.path.exists(f))
            return {
                'files': downloaded_files,
                'total_size': total_size,
                'count': len(downloaded_files)
            }

        return None

    def _extract_filename(self, url: str, headers: dict) -> str:
        """Extract filename dari URL atau headers"""
        # Dari Content-Disposition header
        cd = headers.get('content-disposition', '')
        if cd:
            match = re.search(r'filename[^;=\n]*=(([\'"]).*?\2|[^;\n]*)', cd)
            if match:
                return sanitize_filename(unquote(match.group(1).strip('"').strip("'")))

        # Dari URL
        path = urlparse(url).path
        filename = os.path.basename(unquote(path))
        if filename and '.' in filename:
            return sanitize_filename(filename)

        return 'download'

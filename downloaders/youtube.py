import os
import yt_dlp
import asyncio
from config import Config
from utils.helpers import sanitize_filename, ensure_download_dir
from utils.progress import DownloadProgress, ProgressTracker
from utils.queue import DownloadTask, TaskStoppedError

class YouTubeDownloader:
    def __init__(self):
        ensure_download_dir()

    def get_video_info(self, url: str) -> dict:
        """Get video information without downloading"""
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

            # Handle playlist
            if info.get('_type') == 'playlist':
                entries = info.get('entries', [])
                return {
                    'type': 'playlist',
                    'title': info.get('title', 'Unknown Playlist'),
                    'count': len(entries),
                    'entries': entries[:5],  # Preview 5 items
                    'uploader': info.get('uploader', 'Unknown')
                }

            formats = []
            for f in info.get('formats', []):
                if f.get('vcodec') != 'none' and f.get('acodec') != 'none':
                    formats.append({
                        'format_id': f.get('format_id'),
                        'ext': f.get('ext'),
                        'resolution': f.get('resolution', 'audio only'),
                        'filesize': f.get('filesize') or f.get('filesize_approx', 0),
                        'fps': f.get('fps', 0),
                        'vcodec': f.get('vcodec', 'none'),
                    })

            return {
                'type': 'video',
                'title': info.get('title', 'Unknown'),
                'duration': info.get('duration', 0),
                'uploader': info.get('uploader', 'Unknown'),
                'view_count': info.get('view_count', 0),
                'like_count': info.get('like_count', 0),
                'thumbnail': info.get('thumbnail', ''),
                'description': info.get('description', '')[:500],
                'formats': formats[-5:],  # Top 5 formats
                'upload_date': info.get('upload_date', ''),
            }

    async def download_audio(self, url: str, progress_tracker: ProgressTracker = None,
                              task: DownloadTask = None) -> dict:
        """Download sebagai MP3"""
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
            'format': 'bestaudio/best',
            'outtmpl': output_template,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '320',
            }],
            'progress_hooks': hooks,
            'quiet': True,
        }

        return await asyncio.to_thread(self._download, url, ydl_opts)

    async def download_video(self, url: str, quality: str = "best",
                              progress_tracker: ProgressTracker = None,
                              task: DownloadTask = None) -> dict:
        """Download video dengan kualitas tertentu"""
        output_template = os.path.join(Config.DOWNLOAD_PATH, '%(title)s.%(ext)s')

        quality_map = {
            "best": "bestvideo+bestaudio/best",
            "1080p": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
            "720p": "bestvideo[height<=720]+bestaudio/best[height<=720]",
            "480p": "bestvideo[height<=480]+bestaudio/best[height<=480]",
            "360p": "bestvideo[height<=360]+bestaudio/best[height<=360]",
            "audio": "bestaudio/best"
        }

        hooks = []
        if progress_tracker:
            hooks.append(DownloadProgress(progress_tracker))

        if task:
            def stop_hook(d):
                if task.should_stop:
                    raise yt_dlp.utils.DownloadError("STOPPED_BY_USER")
            hooks.append(stop_hook)

        ydl_opts = {
            'format': quality_map.get(quality, "bestvideo+bestaudio/best"),
            'outtmpl': output_template,
            'merge_output_format': 'mp4',
            'progress_hooks': hooks,
            'quiet': True,
            'postprocessors': [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4',
            }],
        }

        return await asyncio.to_thread(self._download, url, ydl_opts)

    async def download_playlist(self, url: str, audio_only: bool = False,
                                 progress_tracker: ProgressTracker = None,
                                 task: DownloadTask = None) -> dict:
        """Download playlist YouTube"""
        output_template = os.path.join(Config.DOWNLOAD_PATH, '%(playlist)s/%(playlist_index)s - %(title)s.%(ext)s')

        hooks = []
        if progress_tracker:
            hooks.append(DownloadProgress(progress_tracker))

        if task:
            def stop_hook(d):
                if task.should_stop:
                    raise yt_dlp.utils.DownloadError("STOPPED_BY_USER")
            hooks.append(stop_hook)

        base_opts = {
            'outtmpl': output_template,
            'progress_hooks': hooks,
            'quiet': True,
        }

        if audio_only:
            base_opts.update({
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }]
            })
        else:
            base_opts.update({
                'format': 'bestvideo+bestaudio/best',
                'merge_output_format': 'mp4',
            })

        return await asyncio.to_thread(self._download, url, base_opts)

    def _download(self, url: str, opts: dict) -> dict:
        """Internal download function (sync)"""
        downloaded_files = []

        def my_hook(d):
            if d['status'] == 'finished':
                downloaded_files.append(d['filename'])

        opts['progress_hooks'] = opts.get('progress_hooks', []) + [my_hook]

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
        except yt_dlp.utils.DownloadError as e:
            if "STOPPED_BY_USER" in str(e):
                raise TaskStoppedError("Download dihentikan oleh user")
            raise

        # Get actual files (after postprocessing, extension might change)
        result_files = []
        for f in downloaded_files:
            # Check for converted files
            base = os.path.splitext(f)[0]
            for ext in ['.mp3', '.mp4', '.mkv', '.webm', f]:
                candidate = base + ext if not ext.startswith('/') else ext
                if os.path.exists(candidate):
                    result_files.append(candidate)
                    break

        if not result_files:
            # Fallback: cari file terbaru di download dir
            import glob
            files = glob.glob(os.path.join(Config.DOWNLOAD_PATH, '*'))
            if files:
                result_files = [max(files, key=os.path.getctime)]

        total_size = sum(os.path.getsize(f) for f in result_files if os.path.exists(f))

        return {
            'files': result_files,
            'total_size': total_size,
            'count': len(result_files)
        }

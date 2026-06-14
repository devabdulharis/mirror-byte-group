import os
import re
import json
import hashlib
import asyncio
import aiohttp
import aiofiles
from config import Config
from utils.helpers import ensure_download_dir, sanitize_filename
from utils.progress import ProgressTracker
from utils.queue import DownloadTask, TaskStoppedError


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
TERABOX_UA = "terabox;1.40.0.132;PC;PC-Windows;10.0.26100;WindowsTeraBox"
BASE = "https://dm.terabox.com"

COMMON_QS = {
    "app_id": "250528",
    "web": "1",
    "channel": "dubox",
    "clienttype": "0",
}


def _build_headers(extra: dict | None = None) -> dict:
    h = {
        "User-Agent": TERABOX_UA,
        "Cookie": Config.TERABOX_COOKIE or "",
    }
    if extra:
        h.update(extra)
    return h


class TeraboxDownloader:
    """
    Downloader untuk Terabox share link.
    Prioritas informasi:
      1. Third-party API (terabox.hnn.workers.dev)
      2. Third-party API (ytdl.freemediabot.xyz)
      3. Official resolve (GET /api/share/list)
    """

    def __init__(self):
        ensure_download_dir()

    # ==================================================================
    # Get file info
    # ==================================================================
    async def get_file_info(self, url: str) -> dict:
        share_code = self._extract_share_code(url)

        try:
            return await self._get_info_primary(share_code)
        except Exception:
            pass
        try:
            return await self._get_info_fallback(url)
        except Exception:
            pass
        try:
            return await self._get_info_official(share_code)
        except Exception:
            pass

        raise Exception("Tidak dapat mengambil informasi file dari Terabox")

    async def _get_info_primary(self, share_code: str) -> dict:
        api_url = f"https://terabox.hnn.workers.dev/api/get-info?shorturl={share_code}"
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    raise Exception(f"HTTP {resp.status}")
                data = await resp.json()
                if not data.get("ok"):
                    raise Exception(f"API not ok: {data}")
                return {
                    "source": "thirdparty_v1",
                    "files": data.get("list", []),
                    "count": len(data.get("list", [])),
                    "title": data.get("title", "Unknown"),
                    "share_code": share_code,
                }

    async def _get_info_fallback(self, url: str) -> dict:
        api_url = f"https://ytdl.freemediabot.xyz/terabox?url={url}"
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    raise Exception(f"HTTP {resp.status}")
                data = await resp.json()
                return {
                    "source": "thirdparty_v2",
                    "files": [{
                        "name": data.get("title", "unknown"),
                        "size": data.get("size", 0),
                        "download_url": data.get("url", ""),
                    }],
                    "count": 1,
                    "title": data.get("title", "Unknown"),
                }

    async def _get_info_official(self, share_code: str) -> dict:
        """Official resolve via GET /api/shorturlinfo."""
        js_token = Config.TERABOX_JS_TOKEN or ""
        params = {
            **COMMON_QS,
            "shorturl": share_code,
            "root": "1",
            "jsToken": js_token,
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{BASE}/api/shorturlinfo",
                params=params,
                headers=_build_headers(),
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status != 200:
                    raise Exception(f"Official resolve: HTTP {resp.status}")
                data = await resp.json()
                if data.get("errno", -1) != 0:
                    raise Exception(f"Official resolve gagal: errno={data.get('errno')}")
                file_list = data.get("list", [])
                files = []
                for f in file_list:
                    files.append({
                        "name": f.get("server_filename", "unknown"),
                        "size": f.get("size", 0),
                        "fs_id": f.get("fs_id", 0),
                        "isdir": f.get("isdir", 0),
                        "path": f.get("path", ""),
                    })
                return {
                    "source": "official_resolve",
                    "files": files,
                    "count": len(files),
                    "title": data.get("title", "Unknown"),
                    "share_code": share_code,
                    "shareid": data.get("shareid", 0),
                    "uk": data.get("uk", 0),
                }

    # ==================================================================
    # Download
    # ==================================================================
    async def download(self, url: str, progress_tracker: ProgressTracker | None = None,
                        task: DownloadTask | None = None) -> dict:
        info = await self.get_file_info(url)
        source = info.get("source", "")

        if source in ("thirdparty_v1", "thirdparty_v2"):
            return await self._download_via_dlink(info, progress_tracker, task)

        if source == "official_resolve":
            try:
                return await self._download_via_official(info, progress_tracker, task)
            except Exception:
                # Fallback ke dlink via download API
                return await self._download_via_official_dlink(info, progress_tracker, task)

        raise Exception(f"Unknown info source: {source}")

    async def _download_via_dlink(self, info: dict, progress_tracker=None, task=None) -> dict:
        downloaded_files = []
        for file_info in info.get("files", []):
            dl_url = file_info.get("download_url") or file_info.get("dlink", "")
            filename = file_info.get("name", "terabox_download")
            if not dl_url:
                continue
            file_path = await self._download_file(dl_url, filename, progress_tracker, task)
            if file_path:
                downloaded_files.append(file_path)
        total_size = sum(os.path.getsize(f) for f in downloaded_files if os.path.exists(f))
        return {"files": downloaded_files, "total_size": total_size, "count": len(downloaded_files)}

    async def _download_via_official(self, info: dict, progress_tracker=None, task=None) -> dict:
        """
        Official transfer + download.
        1) POST /api/download → dapatkan dlink
        2) Download dari dlink
        """
        js_token = Config.TERABOX_JS_TOKEN or ""
        if not js_token:
            raise Exception("jsToken diperlukan")

        files = info.get("files", [])
        fs_ids = [f["fs_id"] for f in files if not f.get("isdir")]

        if not fs_ids:
            raise Exception("Tidak ada file untuk didownload")

        # Dapatkan dlink via /api/download
        dl_params = {**COMMON_QS, "jsToken": js_token}
        dl_data = {
            "fidlist": json.dumps(fs_ids),
            "type": "dlink",
            "vip": "2",
            "need_speed": "1",
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{BASE}/api/download",
                params=dl_params,
                data=dl_data,
                headers=_build_headers({"Content-Type": "application/x-www-form-urlencoded"}),
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                r = await resp.json()
                if r.get("errno", -1) != 0:
                    raise Exception(f"Download API gagal: errno={r.get('errno')}")
                dlink_list = r.get("dlink", [])

            # Download setiap file
            downloaded_files = []
            for i, f_info in enumerate(files):
                if f_info.get("isdir"):
                    continue
                filename = f_info.get("name", "unknown")
                dlink = dlink_list[i] if i < len(dlink_list) else None
                if not dlink:
                    continue
                file_path = await self._download_file(dlink, filename, progress_tracker, task)
                if file_path:
                    downloaded_files.append(file_path)

        total_size = sum(os.path.getsize(f) for f in downloaded_files if os.path.exists(f))
        return {"files": downloaded_files, "total_size": total_size, "count": len(downloaded_files)}

    async def _download_via_official_dlink(self, info: dict, progress_tracker=None, task=None) -> dict:
        """Fallback: download via path-based /rest/2.0/pcs/file"""
        js_token = Config.TERABOX_JS_TOKEN or ""
        downloaded_files = []

        async with aiohttp.ClientSession() as session:
            for f_info in info.get("files", []):
                if f_info.get("isdir"):
                    continue
                filename = f_info.get("name", "unknown")
                remote_path = f_info.get("path", f"/{filename}")
                file_path = await self._download_by_path(remote_path, filename, progress_tracker, session, task)
                if file_path:
                    downloaded_files.append(file_path)

        total_size = sum(os.path.getsize(f) for f in downloaded_files if os.path.exists(f))
        return {"files": downloaded_files, "total_size": total_size, "count": len(downloaded_files)}

    async def _download_by_path(self, remote_path: str, filename: str,
                                 progress_tracker=None, session: aiohttp.ClientSession | None = None,
                                 task=None) -> str:
        js_token = Config.TERABOX_JS_TOKEN or ""
        safe_filename = sanitize_filename(filename)
        file_path = os.path.join(Config.DOWNLOAD_PATH, safe_filename)
        close_session = session is None
        if session is None:
            session = aiohttp.ClientSession()

        try:
            dl_params = {
                "method": "download",
                "app_id": COMMON_QS["app_id"],
                "path": remote_path,
                "jsToken": js_token,
            }
            async with session.get(
                f"{BASE}/rest/2.0/pcs/file",
                params=dl_params,
                headers=_build_headers(),
                allow_redirects=False,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status not in (302, 301, 303, 307, 308):
                    raise Exception(f"Download link gagal: HTTP {resp.status}")
                dlink = resp.headers.get("Location", "")
                if not dlink:
                    raise Exception("Tidak ada Location header")

            async with session.get(
                dlink,
                headers=_build_headers(),
                allow_redirects=True,
                timeout=aiohttp.ClientTimeout(total=7200),
            ) as dl_resp:
                if dl_resp.status not in (200, 206):
                    raise Exception(f"Download gagal: HTTP {dl_resp.status}")
                total = int(dl_resp.headers.get("content-length", 0))
                downloaded = 0
                async with aiofiles.open(file_path, "wb") as f:
                    async for chunk in dl_resp.content.iter_chunked(65536):
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
        finally:
            if close_session:
                await session.close()

        return file_path

    async def _download_file(self, url: str, filename: str, progress_tracker=None,
                              task: DownloadTask | None = None) -> str:
        safe_filename = sanitize_filename(filename)
        file_path = os.path.join(Config.DOWNLOAD_PATH, safe_filename)
        part_path = file_path + ".part"

        headers = _build_headers()
        resume_from = 0

        # Cek partial download untuk resume
        if os.path.exists(part_path):
            resume_from = os.path.getsize(part_path)
            if resume_from > 0:
                headers['Range'] = f'bytes={resume_from}-'

        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                headers=headers,
                allow_redirects=True,
                timeout=aiohttp.ClientTimeout(total=3600),
            ) as resp:
                # Tentukan mode setelah lihat response status
                if resp.status == 200:
                    # Server tidak support range → mulai dari awal
                    resume_from = 0
                    mode = 'wb'
                elif resp.status == 206:
                    # Partial content
                    mode = 'ab'
                else:
                    mode = 'wb'

                total = int(resp.headers.get("content-length", 0))
                if resp.status == 206 and resume_from > 0:
                    total = resume_from + total

                downloaded = resume_from
                async with aiofiles.open(part_path, mode) as f:
                    async for chunk in resp.content.iter_chunked(65536):
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

        # Rename part → file asli
        if os.path.exists(part_path):
            os.rename(part_path, file_path)

        return file_path

    # ==================================================================
    # Utility
    # ==================================================================
    def _extract_share_code(self, url: str) -> str:
        patterns = [
            r"surl=([^&]+)",
            r"/s/([^/?]+)",
            r"freeterabox\.com/s/([^/?]+)",
            r"1024terabox\.com/s/([^/?]+)",
            r"terabox\.com/s/([^/?]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return url.split("/")[-1]

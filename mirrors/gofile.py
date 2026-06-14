import os
import aiohttp
import aiofiles
from config import Config
from utils.mirror_progress import MirrorProgressTracker

class GoFileMirror:
    """GoFile.io - Free file hosting"""

    BASE_URL = "https://api.gofile.io"

    async def get_best_server(self) -> str:
        """Get best upload server"""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.BASE_URL}/servers") as resp:
                data = await resp.json()
                if data.get('status') == 'ok':
                    servers = data['data']['servers']
                    # Pilih server dengan zona terdekat
                    return servers[0]['name']
        return "store1"

    async def upload(self, file_path: str, progress_tracker: MirrorProgressTracker = None) -> dict:
        """Upload file ke GoFile"""
        filename = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)

        try:
            server = await self.get_best_server()
            upload_url = f"https://{server}.gofile.io/uploadFile"

            headers = {}
            if Config.GOFILE_TOKEN:
                headers['Authorization'] = f"Bearer {Config.GOFILE_TOKEN}"

            async with aiohttp.ClientSession() as session:
                if progress_tracker:
                    # Upload dengan progress tracking via file wrapper
                    class ProgressFile:
                        def __init__(self, path, tracker, total):
                            self.path = path
                            self.tracker = tracker
                            self.total = total
                            self.read_so_far = 0
                            self.f = open(path, 'rb')

                        def __aiter__(self):
                            return self

                        async def __anext__(self):
                            chunk = self.f.read(65536)
                            if not chunk:
                                self.f.close()
                                raise StopAsyncIteration
                            self.read_so_far += len(chunk)
                            await self.tracker.update(self.read_so_far, self.total, filename)
                            return chunk

                    form = aiohttp.FormData()
                    form.add_field('file', ProgressFile(file_path, progress_tracker, file_size),
                                   filename=filename)
                else:
                    with open(file_path, 'rb') as f:
                        form = aiohttp.FormData()
                        form.add_field('file', f, filename=filename)

                async with session.post(upload_url, data=form,
                                         headers=headers,
                                         timeout=aiohttp.ClientTimeout(total=3600)) as resp:
                    data = await resp.json()

                    if data.get('status') == 'ok':
                        file_data = data['data']
                        if progress_tracker:
                            await progress_tracker.complete(filename)
                        return {
                            'success': True,
                            'platform': 'gofile',
                            'link': file_data.get('downloadPage', ''),
                            'direct_link': f"https://{server}.gofile.io/download/{file_data.get('code', '')}/{filename}",
                            'file_id': file_data.get('fileId', ''),
                            'code': file_data.get('code', '')
                        }

            if progress_tracker:
                await progress_tracker.error("Upload gagal", filename)
            return {
                'success': False,
                'error': 'Upload gagal',
                'platform': 'gofile'
            }

        except Exception as e:
            if progress_tracker:
                await progress_tracker.error(str(e), filename)
            return {
                'success': False,
                'error': str(e),
                'platform': 'gofile'
            }

import os
import git
import asyncio
import zipfile
import shutil
from config import Config
from utils.helpers import sanitize_filename, ensure_download_dir
from utils.queue import DownloadTask, TaskStoppedError

class GitHubDownloader:
    def __init__(self):
        ensure_download_dir()

    def parse_github_url(self, url: str) -> dict:
        """Parse GitHub URL untuk mendapatkan info repo"""
        import re

        # Pattern untuk berbagai format GitHub URL
        patterns = [
            r'github\.com/([^/]+)/([^/]+)(?:/tree/([^/]+))?',
            r'github\.com/([^/]+)/([^/]+)\.git',
        ]

        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                owner = match.group(1)
                repo = match.group(2).replace('.git', '')
                branch = match.group(3) if len(match.groups()) > 2 and match.group(3) else 'main'

                return {
                    'owner': owner,
                    'repo': repo,
                    'branch': branch,
                    'clone_url': f'https://github.com/{owner}/{repo}.git',
                    'zip_url': f'https://github.com/{owner}/{repo}/archive/refs/heads/{branch}.zip',
                    'api_url': f'https://api.github.com/repos/{owner}/{repo}'
                }

        return None

    async def get_repo_info(self, url: str) -> dict:
        """Get repository information via GitHub API"""
        import aiohttp

        info = self.parse_github_url(url)
        if not info:
            return None

        async with aiohttp.ClientSession() as session:
            async with session.get(info['api_url']) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return {
                        'name': data.get('name'),
                        'full_name': data.get('full_name'),
                        'description': data.get('description', 'No description'),
                        'stars': data.get('stargazers_count', 0),
                        'forks': data.get('forks_count', 0),
                        'language': data.get('language', 'Unknown'),
                        'size': data.get('size', 0) * 1024,  # KB to bytes
                        'default_branch': data.get('default_branch', 'main'),
                        'clone_url': info['clone_url'],
                        'topics': data.get('topics', []),
                        'license': data.get('license', {}).get('name', 'No License') if data.get('license') else 'No License',
                        'updated_at': data.get('updated_at', ''),
                    }
        return info

    async def clone_repo(self, url: str, depth: int = None,
                          progress_callback=None, task: DownloadTask = None) -> dict:
        """Clone GitHub repository"""
        info = self.parse_github_url(url)
        if not info:
            raise ValueError("Invalid GitHub URL")

        repo_dir = os.path.join(Config.DOWNLOAD_PATH, f"{info['owner']}_{info['repo']}")

        # Hapus jika sudah ada
        if os.path.exists(repo_dir):
            shutil.rmtree(repo_dir)

        def do_clone():
            clone_opts = {
                'progress': git.remote.RemoteProgress() if progress_callback else None
            }
            if depth:
                clone_opts['depth'] = depth

            repo = git.Repo.clone_from(
                info['clone_url'],
                repo_dir,
                **{k: v for k, v in clone_opts.items() if v is not None}
            )
            return repo

        await asyncio.to_thread(do_clone)

        # Zip the repo
        zip_path = repo_dir + '.zip'
        await asyncio.to_thread(self._zip_directory, repo_dir, zip_path)

        zip_size = os.path.getsize(zip_path)

        return {
            'files': [zip_path],
            'repo_dir': repo_dir,
            'total_size': zip_size,
            'repo_name': f"{info['owner']}/{info['repo']}",
            'count': 1
        }

    async def download_zip(self, url: str, task: DownloadTask = None) -> dict:
        """Download repo sebagai ZIP langsung"""
        import aiohttp
        import aiofiles

        info = self.parse_github_url(url)
        if not info:
            raise ValueError("Invalid GitHub URL")

        zip_filename = f"{info['owner']}_{info['repo']}_{info['branch']}.zip"
        zip_path = os.path.join(Config.DOWNLOAD_PATH, zip_filename)

        async with aiohttp.ClientSession() as session:
            async with session.get(info['zip_url']) as resp:
                if resp.status == 200:
                    async with aiofiles.open(zip_path, 'wb') as f:
                        async for chunk in resp.content.iter_chunked(8192):
                            if task:
                                await task.checkpoint()
                            await f.write(chunk)

        zip_size = os.path.getsize(zip_path)

        return {
            'files': [zip_path],
            'total_size': zip_size,
            'repo_name': f"{info['owner']}/{info['repo']}",
            'count': 1
        }

    def _zip_directory(self, directory: str, output_path: str):
        """Zip a directory"""
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(directory):
                # Skip .git directory
                dirs[:] = [d for d in dirs if d != '.git']
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, os.path.dirname(directory))
                    zipf.write(file_path, arcname)

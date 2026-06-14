import os
import re
import humanize
import psutil
from config import Config

def detect_platform(url: str) -> str:
    """Detect platform from URL"""
    url_lower = url.lower()

    for pattern in Config.YOUTUBE_PATTERNS:
        if pattern in url_lower:
            return "youtube"

    for pattern in Config.GITHUB_PATTERNS:
        if pattern in url_lower:
            return "github"

    for pattern in Config.TERABOX_PATTERNS:
        if pattern in url_lower:
            return "terabox"

    # Check if it's a direct file URL
    if any(ext in url_lower for ext in ['.mp4', '.mkv', '.zip', '.rar', '.pdf', '.mp3', '.png', '.jpg']):
        return "direct"

    return "unknown"

def format_size(size_bytes: int) -> str:
    """Format bytes to human readable"""
    return humanize.naturalsize(size_bytes, binary=True)

def format_duration(seconds: int) -> str:
    """Format seconds to human readable duration"""
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        return f"{seconds//60}m {seconds%60}s"
    else:
        return f"{seconds//3600}h {(seconds%3600)//60}m"

def sanitize_filename(filename: str) -> str:
    """Remove invalid characters from filename"""
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    filename = filename.strip('. ')
    return filename[:200] if len(filename) > 200 else filename

def get_system_stats() -> dict:
    """Get system resource usage"""
    disk = psutil.disk_usage(Config.DOWNLOAD_PATH if os.path.exists(Config.DOWNLOAD_PATH) else '/')
    return {
        "cpu": psutil.cpu_percent(interval=1),
        "ram": psutil.virtual_memory().percent,
        "disk_free": format_size(disk.free),
        "disk_used": format_size(disk.used),
        "disk_total": format_size(disk.total)
    }

def is_authorized(user_id: int) -> bool:
    """Check if user is authorized"""
    if not Config.AUTHORIZED_USERS:
        return True  # Semua user diizinkan jika list kosong
    return user_id in Config.AUTHORIZED_USERS or user_id == Config.OWNER_ID

def ensure_download_dir():
    """Pastikan direktori download ada"""
    os.makedirs(Config.DOWNLOAD_PATH, exist_ok=True)

import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Telegram
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    API_ID = int(os.getenv("API_ID", 0))
    API_HASH = os.getenv("API_HASH")
    OWNER_ID = int(os.getenv("OWNER_ID", 0))

    # AI
    AI_API_KEY = os.getenv("AI_API_KEY", "")
    AI_BASE_URL = os.getenv("AI_BASE_URL", "http://panel.hdev.biz.id:20128/v1")
    AI_MODEL = os.getenv("AI_MODEL", "claude-sonnet-4-6-20250514")

    # Google Drive
    GDRIVE_CREDENTIALS_JSON = os.getenv("GDRIVE_CREDENTIALS_JSON", "credentials.json")
    GDRIVE_FOLDER_ID = os.getenv("GDRIVE_FOLDER_ID", "")

    # Terabox
    TERABOX_COOKIE = os.getenv("TERABOX_COOKIE", "")
    TERABOX_BDS_TOKEN = os.getenv("TERABOX_BDS_TOKEN", "")
    TERABOX_JS_TOKEN = os.getenv("TERABOX_JS_TOKEN", "")
    TERABOX_DEVID = os.getenv("TERABOX_DEVID", "")

    # GoFile
    GOFILE_TOKEN = os.getenv("GOFILE_TOKEN", "")

    # Settings
    MAX_FILE_SIZE_TG = int(os.getenv("MAX_FILE_SIZE_TG", 2000)) * 1024 * 1024  # Convert to bytes
    DOWNLOAD_PATH = os.getenv("DOWNLOAD_PATH", "./downloads")
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///bot.db")

    # Authorized users
    _auth_users = os.getenv("AUTHORIZED_USERS", "")
    AUTHORIZED_USERS = [int(x) for x in _auth_users.split(",") if x.strip()] if _auth_users else []

    # Platform detection patterns
    YOUTUBE_PATTERNS = [
        "youtube.com/watch",
        "youtu.be/",
        "youtube.com/shorts",
        "youtube.com/playlist",
        "music.youtube.com"
    ]

    GITHUB_PATTERNS = [
        "github.com/",
    ]

    TERABOX_PATTERNS = [
        "terabox.com",
        "1024terabox.com",
        "teraboxapp.com",
        "mirrobox.com",
        "nephobox.com",
        "freeterabox.com",
        "4funbox.co",
        "momerybox.com",
        "tibibox.com"
    ]

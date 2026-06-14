import os
import json
import time
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from config import Config
from utils.helpers import detect_platform, format_size, format_duration, is_authorized
from utils.progress import ProgressTracker
from utils.database import get_session, DownloadTask, UserSession
from utils.queue import queue, TaskStatus, TaskStoppedError
from downloaders.youtube import YouTubeDownloader
from downloaders.github import GitHubDownloader
from downloaders.terabox import TeraboxDownloader
from downloaders.general import GeneralDownloader
from handlers.ai import AIHandler

yt_downloader = YouTubeDownloader()
gh_downloader = GitHubDownloader()
tb_downloader = TeraboxDownloader()
gen_downloader = GeneralDownloader()
ai_handler = AIHandler()

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle URL yang dikirim user"""
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("⛔ Kamu tidak memiliki akses ke bot ini.")
        return

    url = update.message.text.strip()
    user_id = update.effective_user.id
    platform = detect_platform(url)

    # Simpan URL di context
    context.user_data['current_url'] = url
    context.user_data['platform'] = platform

    # Tampilkan menu berdasarkan platform
    if platform == "youtube":
        await handle_youtube_url(update, context, url)
    elif platform == "github":
        await handle_github_url(update, context, url)
    elif platform == "terabox":
        await handle_terabox_url(update, context, url)
    elif platform in ["direct", "unknown"]:
        await handle_general_url(update, context, url)
    else:
        await update.message.reply_text(
            "❓ Platform tidak dikenali. Sedang menganalisis...",
            parse_mode=ParseMode.MARKDOWN
        )
        # Gunakan AI untuk analisis
        analysis = await ai_handler.analyze_url(url)
        keyboard = [
            [InlineKeyboardButton("⬇️ Download Langsung", callback_data="dl_direct")],
            [InlineKeyboardButton("🤖 Tanya AI Lebih Lanjut", callback_data="ask_ai")],
            [InlineKeyboardButton("❌ Batal", callback_data="cancel")]
        ]
        await update.message.reply_text(
            f"🤖 **Analisis AI:**\n\n{analysis}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )

async def handle_youtube_url(update: Update, context: ContextTypes.DEFAULT_TYPE, url: str):
    """Handle YouTube URL"""
    msg = await update.message.reply_text("🔍 Mengambil informasi video...")

    try:
        info = await asyncio.to_thread(yt_downloader.get_video_info, url)

        if info['type'] == 'playlist':
            text = (
                f"📋 **YouTube Playlist Terdeteksi**\n\n"
                f"📝 **{info['title']}**\n"
                f"👤 Channel: `{info['uploader']}`\n"
                f"🎬 Total: `{info['count']} video`\n\n"
                f"**Preview (5 pertama):**\n"
            )
            for i, entry in enumerate(info.get('entries', [])[:5], 1):
                text += f"{i}. {entry.get('title', 'Unknown')}\n"

            keyboard = [
                [InlineKeyboardButton("🎵 Download Semua (MP3)", callback_data="yt_playlist_audio"),
                 InlineKeyboardButton("🎬 Download Semua (Video)", callback_data="yt_playlist_video")],
                [InlineKeyboardButton("❌ Batal", callback_data="cancel")]
            ]
        else:
            duration_str = format_duration(info.get('duration', 0))
            views = f"{info.get('view_count', 0):,}"

            text = (
                f"🎬 **YouTube Video**\n\n"
                f"📝 **{info['title']}**\n"
                f"👤 Channel: `{info['uploader']}`\n"
                f"⏱️ Durasi: `{duration_str}`\n"
                f"👁️ Views: `{views}`\n\n"
                f"🎯 **Pilih Format Download:**"
            )

            keyboard = [
                [
                    InlineKeyboardButton("🎵 MP3 (Audio)", callback_data="yt_mp3"),
                    InlineKeyboardButton("🎬 MP4 Best", callback_data="yt_video_best")
                ],
                [
                    InlineKeyboardButton("📺 1080p", callback_data="yt_video_1080p"),
                    InlineKeyboardButton("📺 720p", callback_data="yt_video_720p")
                ],
                [
                    InlineKeyboardButton("📺 480p", callback_data="yt_video_480p"),
                    InlineKeyboardButton("📺 360p", callback_data="yt_video_360p")
                ],
                [InlineKeyboardButton("🤖 Tanya AI", callback_data="ask_ai"),
                 InlineKeyboardButton("❌ Batal", callback_data="cancel")]
            ]

        await msg.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard),
                             parse_mode=ParseMode.MARKDOWN)

    except Exception as e:
        await msg.edit_text(f"❌ Error mengambil info video:\n`{str(e)}`\n\nCoba gunakan /download langsung.",
                             parse_mode=ParseMode.MARKDOWN)

async def handle_github_url(update: Update, context: ContextTypes.DEFAULT_TYPE, url: str):
    """Handle GitHub URL"""
    msg = await update.message.reply_text("🔍 Mengambil informasi repository...")

    try:
        info = await gh_downloader.get_repo_info(url)

        if info:
            size_str = format_size(info.get('size', 0)) if info.get('size') else 'Unknown'

            text = (
                f"📁 **GitHub Repository**\n\n"
                f"🔗 **{info.get('full_name', info.get('name', 'Unknown'))}**\n"
                f"📝 {info.get('description', 'No description')}\n\n"
                f"⭐ Stars: `{info.get('stars', 0):,}`\n"
                f"🍴 Forks: `{info.get('forks', 0):,}`\n"
                f"💻 Language: `{info.get('language', 'Unknown')}`\n"
                f"📦 Size: `{size_str}`\n"
                f"📜 License: `{info.get('license', 'Unknown')}`\n"
            )

            if info.get('topics'):
                text += f"🏷️ Topics: {', '.join(info['topics'][:5])}\n"

            text += f"\n🎯 **Pilih Metode Download:**"
        else:
            text = "📁 **GitHub Repository**\n\n🎯 **Pilih Metode Download:**"

        keyboard = [
            [InlineKeyboardButton("📥 Clone (Git)", callback_data="gh_clone"),
             InlineKeyboardButton("📦 Download ZIP", callback_data="gh_zip")],
            [InlineKeyboardButton("🌿 Shallow Clone (cepat)", callback_data="gh_shallow")],
            [InlineKeyboardButton("🤖 Tanya AI", callback_data="ask_ai"),
             InlineKeyboardButton("❌ Batal", callback_data="cancel")]
        ]

        await msg.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard),
                             parse_mode=ParseMode.MARKDOWN)

    except Exception as e:
        await msg.edit_text(f"❌ Error: `{str(e)}`", parse_mode=ParseMode.MARKDOWN)

async def handle_terabox_url(update: Update, context: ContextTypes.DEFAULT_TYPE, url: str):
    """Handle Terabox URL"""
    msg = await update.message.reply_text("🔍 Mengambil informasi file dari Terabox...")

    try:
        info = await tb_downloader.get_file_info(url)

        files = info.get('files', [])
        total_size = sum(f.get('size', 0) for f in files)

        text = (
            f"📦 **Terabox**\n\n"
            f"📝 **{info.get('title', 'Unknown')}**\n"
            f"📁 Jumlah file: `{len(files)}`\n"
            f"💾 Total size: `{format_size(total_size)}`\n\n"
        )

        if files:
            text += "**File list:**\n"
            for f in files[:5]:
                text += f"• `{f.get('name', 'Unknown')}` - {format_size(f.get('size', 0))}\n"
            if len(files) > 5:
                text += f"• ... dan {len(files)-5} file lainnya\n"

        text += "\n🎯 **Pilih aksi:**"

        keyboard = [
            [InlineKeyboardButton("⬇️ Download Semua", callback_data="tb_download_all")],
            [InlineKeyboardButton("🤖 Tanya AI", callback_data="ask_ai"),
             InlineKeyboardButton("❌ Batal", callback_data="cancel")]
        ]

        await msg.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard),
                             parse_mode=ParseMode.MARKDOWN)

    except Exception as e:
        await msg.edit_text(f"❌ Error Terabox: `{str(e)}`\n\nCoba /download untuk download langsung.",
                             parse_mode=ParseMode.MARKDOWN)

async def handle_general_url(update: Update, context: ContextTypes.DEFAULT_TYPE, url: str):
    """Handle URL umum"""
    msg = await update.message.reply_text("🔍 Menganalisis URL...")

    try:
        info = await gen_downloader.get_file_info(url)

        text = (
            f"🌐 **Direct Download**\n\n"
            f"📁 **{info['filename']}**\n"
            f"📝 Type: `{info['content_type']}`\n"
            f"💾 Size: `{format_size(info['size'])}`\n"
            f"🔄 Resume: {'✅' if info['supports_resume'] else '❌'}\n\n"
            f"🎯 **Pilih aksi:**"
        )

        keyboard = [
            [InlineKeyboardButton("⬇️ Download File", callback_data="dl_direct")],
            [InlineKeyboardButton("🤖 Tanya AI", callback_data="ask_ai"),
             InlineKeyboardButton("❌ Batal", callback_data="cancel")]
        ]

        await msg.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard),
                             parse_mode=ParseMode.MARKDOWN)

    except Exception as e:
        await msg.edit_text(f"❌ Error: `{str(e)}`", parse_mode=ParseMode.MARKDOWN)

async def process_download(update: Update, context: ContextTypes.DEFAULT_TYPE,
                            download_type: str):
    """Process download sesuai tipe (dengan queue system)"""
    query = update.callback_query
    user_id = query.from_user.id
    url = context.user_data.get('current_url', '')
    platform = context.user_data.get('platform', 'unknown')

    if not url:
        await query.message.edit_text("❌ URL tidak ditemukan. Kirim ulang URL.")
        return

    # Cek limit user
    if not queue.can_user_download(user_id):
        active = queue.user_active_count(user_id)
        await query.message.edit_text(
            f"⚠️ **Kamu sudah punya {active} download aktif.**\n\n"
            f"Tunggu selesai atau stop task dengan:\n"
            f"`/queue` — lihat task\n"
            f"`/pause <id>` — pause\n"
            f"`/stop <id>` — stop\n\n"
            f"Maks {queue._max_per_user} download per user.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    msg = query.message

    # Buat task di queue
    qtask = queue.create_task(
        user_id=user_id,
        chat_id=query.message.chat_id,
        url=url,
        platform=platform,
        filename_hint=url.split('/')[-1][:50]
    )

    # Simpan task ke database
    session = get_session()
    db_task = DownloadTask(
        user_id=user_id,
        chat_id=query.message.chat_id,
        url=url,
        platform=platform,
        status='downloading'
    )
    session.add(db_task)
    session.commit()

    await msg.edit_text(
        f"⬇️ **Download dimulai** (ID: `{qtask.id}`)\n"
        f"🔗 `{url[:50]}...`\n\n"
        f"Gunakan `/stop {qtask.id}` untuk membatalkan.",
        parse_mode=ParseMode.MARKDOWN
    )

    tracker = ProgressTracker(msg, "Downloading")
    result = None

    try:
        qtask.status = TaskStatus.DOWNLOADING
        qtask.started_at = time.time()

        # Eksekusi download via semaphore queue
        async def _do_download():
            if download_type == "yt_mp3":
                return await yt_downloader.download_audio(url, tracker, qtask)
            elif download_type.startswith("yt_video_"):
                quality = download_type.replace("yt_video_", "")
                return await yt_downloader.download_video(url, quality, tracker, qtask)
            elif download_type == "yt_playlist_audio":
                return await yt_downloader.download_playlist(url, audio_only=True, progress_tracker=tracker, task=qtask)
            elif download_type == "yt_playlist_video":
                return await yt_downloader.download_playlist(url, audio_only=False, progress_tracker=tracker, task=qtask)
            elif download_type == "gh_clone":
                return await gh_downloader.clone_repo(url, task=qtask)
            elif download_type == "gh_shallow":
                return await gh_downloader.clone_repo(url, depth=1, task=qtask)
            elif download_type == "gh_zip":
                return await gh_downloader.download_zip(url, qtask)
            elif download_type == "tb_download_all":
                return await tb_downloader.download(url, tracker, qtask)
            elif download_type == "dl_direct":
                return await gen_downloader.download(url, progress_tracker=tracker, task=qtask)
            return None

        result = await queue.run_with_semaphore(_do_download(), qtask)

        if result and result.get('files'):
            qtask.status = TaskStatus.COMPLETED
            qtask.completed_at = time.time()
            qtask.file_paths = result['files']
            qtask.progress_pct = 100.0

            # Update database
            db_task.status = 'completed'
            db_task.file_path = json.dumps(result['files'])
            db_task.file_size = result['total_size']
            db_task.completed_at = datetime.utcnow()
            session.commit()

            # Update user stats
            user_stat = session.query(UserSession).filter_by(user_id=user_id).first()
            if user_stat:
                user_stat.total_downloads += 1
                user_stat.total_size += result['total_size']
                session.commit()

            # Tampilkan menu mirror
            await show_mirror_menu(msg, context, result)
        else:
            raise Exception("Download tidak menghasilkan file")

    except TaskStoppedError:
        qtask.status = TaskStatus.STOPPED
        db_task.status = 'failed'
        db_task.error_msg = 'Stopped by user'
        session.commit()

        await msg.edit_text(
            f"🛑 **Download dihentikan** (ID: `{qtask.id}`)",
            parse_mode=ParseMode.MARKDOWN
        )

    except Exception as e:
        qtask.status = TaskStatus.FAILED
        qtask.error = str(e)
        db_task.status = 'failed'
        db_task.error_msg = str(e)
        session.commit()

        # Cek apakah task sudah di-stop (jika error dari thread yt-dlp)
        if qtask.should_stop:
            await msg.edit_text(
                f"🛑 **Download dihentikan** (ID: `{qtask.id}`)",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await msg.edit_text(
                f"❌ **Download Gagal**\n\n"
                f"Error: `{str(e)}`\n\n"
                f"💡 Coba `/retry` untuk mengulang.\n"
                f"💡 Atau tanya AI: /ai {str(e)[:100]}",
                parse_mode=ParseMode.MARKDOWN
            )
    finally:
        session.close()

async def show_mirror_menu(message, context: ContextTypes.DEFAULT_TYPE, result: dict):
    """Tampilkan menu mirror setelah download"""
    from utils.helpers import format_size

    files = result.get('files', [])
    total_size = result.get('total_size', 0)
    file_list_text = "\n".join([f"• `{os.path.basename(f)}`" for f in files[:5]])

    context.user_data['downloaded_files'] = files
    context.user_data['download_result'] = result

    text = (
        f"✅ **Download Selesai!**\n\n"
        f"📦 {len(files)} file ({format_size(total_size)})\n\n"
        f"{file_list_text}\n\n"
        f"🎯 **Pilih Mirror/Upload Tujuan:**"
    )

    keyboard = [
        [InlineKeyboardButton("📤 Upload ke Telegram", callback_data="mirror_telegram")],
        [InlineKeyboardButton("☁️ Google Drive", callback_data="mirror_gdrive"),
         InlineKeyboardButton("📁 GoFile.io", callback_data="mirror_gofile")],
        [InlineKeyboardButton("📦 Terabox", callback_data="mirror_terabox")],
        [InlineKeyboardButton("🔄 Semua Platform", callback_data="mirror_all")],
        [InlineKeyboardButton("🗑️ Hapus File Lokal", callback_data="delete_local"),
         InlineKeyboardButton("✅ Selesai", callback_data="done")]
    ]

    await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard),
                             parse_mode=ParseMode.MARKDOWN)

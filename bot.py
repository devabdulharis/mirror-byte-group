import os
import logging
import logging.handlers
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)
from telegram.constants import ParseMode

from config import Config
from utils.database import init_db, get_session, UserSession
from utils.helpers import detect_platform, is_authorized, format_size
from handlers.start import start_command, help_command, status_command, stats_command
from handlers.download import handle_url, process_download, show_mirror_menu
from handlers.mirror import process_mirror
from handlers.ai import AIHandler
from handlers.commands import (
    mirror_command, gdrive_command, gofile_command,
    queue_command, pause_command, resume_command, stop_command,
    retry_command, cleanup_command,
    history_command,
    broadcast_command, ban_command, unban_command,
    settings_menu, cleanup_now_callback, queue_cleanup_callback, view_queue_callback,
)

# Setup logging
os.makedirs('logs', exist_ok=True)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.handlers.RotatingFileHandler(
            'logs/bot.log', maxBytes=10*1024*1024, backupCount=5
        ),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

ai_handler = AIHandler()

# ===== CALLBACK QUERY HANDLER =====
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle semua callback query dari inline buttons"""
    query = update.callback_query
    await query.answer()

    data = query.data
    user_id = query.from_user.id

    logger.info(f"Button pressed: {data} by user {user_id}")

    # === DOWNLOAD ACTIONS ===
    if data in ["yt_mp3", "yt_video_best", "yt_video_1080p", "yt_video_720p",
                "yt_video_480p", "yt_video_360p", "yt_playlist_audio",
                "yt_playlist_video", "gh_clone", "gh_shallow", "gh_zip",
                "tb_download_all", "dl_direct"]:
        await process_download(update, context, data)

    # === MIRROR ACTIONS ===
    elif data == "mirror_telegram":
        await process_mirror(update, context, "telegram")
    elif data == "mirror_gdrive":
        await process_mirror(update, context, "gdrive")
    elif data == "mirror_gofile":
        await process_mirror(update, context, "gofile")
    elif data == "mirror_terabox":
        await process_mirror(update, context, "terabox")
    elif data == "mirror_all":
        await process_mirror(update, context, "all")

    # === MENU ACTIONS ===
    elif data == "menu_download":
        await query.message.edit_text(
            "📥 **Download Manager**\n\n"
            "Kirim URL yang ingin kamu download!\n\n"
            "**Platform yang didukung:**\n"
            "• 🎬 YouTube (video/audio/playlist)\n"
            "• 📁 GitHub (repo/zip)\n"
            "• 📦 Terabox\n"
            "• 🌐 URL langsung\n"
            "• 🎵 1000+ platform (Instagram, TikTok, dll)\n\n"
            "**Atau gunakan command:**\n"
            "`/yt <url>` `/ytmp3 <url>` `/gh <url>`\n"
            "`/tb <url>` `/dl <url>`",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu")
            ]])
        )

    elif data == "menu_ai":
        await query.message.edit_text(
            "🤖 **AI Assistant**\n\n"
            "Saya menggunakan AI untuk membantu kamu!\n\n"
            "**Cara pakai:**\n"
            "• `/ai <pertanyaan>` - Tanya sesuatu\n"
            "• `/analyze <url>` - Analisis URL\n"
            "• `/clear` - Reset percakapan\n\n"
            "**Atau langsung kirim pesan setelah menekan tombol Chat AI!**\n\n"
            "💬 Kirim pesan sekarang...",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu")
            ]])
        )
        context.user_data['mode'] = 'ai_chat'

    elif data == "menu_status":
        await status_command(query, context)

    elif data == "menu_help":
        await help_command(query, context)

    elif data == "menu_mirror":
        files = context.user_data.get('downloaded_files', [])
        if not files:
            await query.message.edit_text(
                "☁️ **Mirror Manager**\n\n"
                "❌ Tidak ada file yang sudah didownload.\n\n"
                "Download file terlebih dahulu, kemudian pilih opsi mirror.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu")
                ]])
            )
        else:
            result = context.user_data.get('download_result', {'files': files, 'total_size': 0})
            await show_mirror_menu(query.message, context, result)

    elif data == "menu_settings":
        await settings_menu(update, context)

    # === QUEUE / CONTROL CALLBACKS ===
    elif data == "view_queue":
        await view_queue_callback(update, context)
    elif data == "queue_cleanup":
        await queue_cleanup_callback(update, context)
    elif data == "cleanup_now":
        await cleanup_now_callback(update, context)

    # === OTHER ACTIONS ===
    elif data == "ask_ai":
        url = context.user_data.get('current_url', '')
        context.user_data['mode'] = 'ai_chat'

        if url:
            thinking_msg = await query.message.edit_text(
                "🤖 AI sedang menganalisis...",
                parse_mode=ParseMode.MARKDOWN
            )
            analysis = await ai_handler.analyze_url(url)
            await thinking_msg.edit_text(
                f"🤖 **Analisis AI untuk URL ini:**\n\n{analysis}\n\n"
                f"💬 Kirim pertanyaan lanjutan atau URL baru.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu")
                ]])
            )
        else:
            await query.message.edit_text(
                "🤖 **Mode AI Chat Aktif**\n\n"
                "Kirim pesan atau pertanyaan kamu!",
                parse_mode=ParseMode.MARKDOWN
            )

    elif data == "delete_local":
        files = context.user_data.get('downloaded_files', [])
        deleted = 0
        for f in files:
            if os.path.exists(f):
                os.remove(f)
                deleted += 1

        context.user_data['downloaded_files'] = []

        await query.message.edit_text(
            f"🗑️ **File Dihapus**\n\n"
            f"✅ {deleted} file lokal berhasil dihapus.\n"
            f"File di platform mirror tetap tersedia.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu")
            ]])
        )

    elif data == "cancel":
        await query.message.edit_text(
            "❌ **Dibatalkan**\n\nKirim URL baru atau gunakan /start",
            parse_mode=ParseMode.MARKDOWN
        )

    elif data == "done":
        await query.message.edit_text(
            "✅ **Selesai!**\n\nKirim URL baru untuk download lagi.\nGunakan /start untuk menu utama.",
            parse_mode=ParseMode.MARKDOWN
        )

    elif data == "main_menu":
        keyboard = [
            [InlineKeyboardButton("📥 Download", callback_data="menu_download"),
             InlineKeyboardButton("☁️ Mirror", callback_data="menu_mirror")],
            [InlineKeyboardButton("🤖 Chat AI", callback_data="menu_ai"),
             InlineKeyboardButton("📊 Status", callback_data="menu_status")],
            [InlineKeyboardButton("❓ Bantuan", callback_data="menu_help"),
             InlineKeyboardButton("⚙️ Settings", callback_data="menu_settings")]
        ]
        user_name = query.from_user.first_name
        await query.message.edit_text(
            f"🏠 **Menu Utama**\n\nHai {user_name}! Pilih aksi:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )

    elif data == "ask_ai_text":
        text = context.user_data.get('pending_text', '')
        if text:
            context.user_data['mode'] = 'ai_chat'
            thinking_msg = await query.message.edit_text("🤖 Berpikir...")
            response = await ai_handler.chat(user_id, text)
            await thinking_msg.edit_text(
                f"🤖 **AI:**\n\n{response}",
                parse_mode=ParseMode.MARKDOWN
            )

    else:
        logger.warning(f"Unknown callback data: {data}")
        await query.message.edit_text(
            f"⚠️ Aksi tidak dikenal: `{data}`",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu")
            ]])
        )


# ===== MESSAGE HANDLER =====
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle semua pesan text"""
    if not update.message or not update.message.text:
        return

    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("⛔ Akses ditolak.")
        return

    # Cek banned
    user_id = update.effective_user.id
    session = get_session()
    user_stat = session.query(UserSession).filter_by(user_id=user_id).first()
    if user_stat and user_stat.is_banned:
        session.close()
        await update.message.reply_text("⛔ Kamu telah di-ban dari bot ini.")
        return
    session.close()

    text = update.message.text.strip()
    mode = context.user_data.get('mode', 'normal')

    # Cek apakah itu URL
    if text.startswith('http://') or text.startswith('https://'):
        await handle_url(update, context)
    elif mode == 'ai_chat' or text.startswith('/'):
        # AI chat mode
        if not text.startswith('/'):
            thinking_msg = await update.message.reply_text("🤖 Berpikir...")
            response = await ai_handler.chat(update.effective_user.id, text)
            await thinking_msg.edit_text(
                f"🤖 **AI:**\n\n{response}",
                parse_mode=ParseMode.MARKDOWN
            )
    else:
        # Default - tanya AI apakah ini URL atau pertanyaan
        keyboard = [
            [InlineKeyboardButton("🤖 Tanya AI", callback_data="ask_ai_text"),
             InlineKeyboardButton("❌ Batal", callback_data="cancel")]
        ]
        context.user_data['pending_text'] = text

        await update.message.reply_text(
            f"💬 Kamu mengirim:\n`{text}`\n\n"
            f"Apakah kamu ingin menanyakan ini ke AI?",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )


# ===== COMMAND HANDLERS =====
async def ai_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /ai <pesan>"""
    if not context.args:
        context.user_data['mode'] = 'ai_chat'
        await update.message.reply_text(
            "🤖 **Mode AI Chat Aktif**\n\n"
            "Kirim pesan apapun, saya siap membantu!\n"
            "Gunakan /clear untuk reset percakapan.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    message = ' '.join(context.args)
    thinking_msg = await update.message.reply_text("🤖 Berpikir...")

    response = await ai_handler.chat(update.effective_user.id, message)

    await thinking_msg.edit_text(
        f"🤖 **AI:**\n\n{response}",
        parse_mode=ParseMode.MARKDOWN
    )

async def analyze_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /analyze <url>"""
    if not context.args:
        await update.message.reply_text("❌ Gunakan: `/analyze <url>`", parse_mode=ParseMode.MARKDOWN)
        return

    url = context.args[0]
    thinking_msg = await update.message.reply_text("🔍 Menganalisis URL...")

    analysis = await ai_handler.analyze_url(url)

    await thinking_msg.edit_text(
        f"🔍 **Analisis URL:**\n`{url}`\n\n{analysis}",
        parse_mode=ParseMode.MARKDOWN
    )

async def clear_ai_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /clear - hapus riwayat AI"""
    ai_handler.clear_history(update.effective_user.id)
    context.user_data['mode'] = 'normal'
    await update.message.reply_text("🗑️ Riwayat percakapan AI dihapus!")

async def yt_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /yt <url>"""
    if not context.args:
        await update.message.reply_text("❌ Gunakan: `/yt <youtube_url>`", parse_mode=ParseMode.MARKDOWN)
        return

    url = context.args[0]
    context.user_data['current_url'] = url
    context.user_data['platform'] = 'youtube'

    fake_update = type('obj', (object,), {
        'message': update.message,
        'effective_user': update.effective_user
    })()

    from handlers.download import handle_youtube_url
    await handle_youtube_url(fake_update, context, url)

async def ytmp3_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /ytmp3 <url> - langsung download MP3"""
    if not context.args:
        await update.message.reply_text("❌ Gunakan: `/ytmp3 <youtube_url>`", parse_mode=ParseMode.MARKDOWN)
        return

    url = context.args[0]
    context.user_data['current_url'] = url
    context.user_data['platform'] = 'youtube'

    msg = await update.message.reply_text("⬇️ Memulai download MP3...")

    from utils.progress import ProgressTracker
    from downloaders.youtube import YouTubeDownloader
    from utils.queue import queue, TaskStatus

    yt = YouTubeDownloader()
    tracker = ProgressTracker(msg, "Downloading MP3")

    qtask = queue.create_task(
        user_id=update.effective_user.id,
        chat_id=update.effective_chat.id,
        url=url,
        platform='youtube',
        filename_hint='youtube_mp3'
    )
    qtask.status = TaskStatus.DOWNLOADING

    try:
        result = await yt.download_audio(url, tracker, qtask)
        qtask.status = TaskStatus.COMPLETED
        context.user_data['downloaded_files'] = result['files']
        context.user_data['download_result'] = result
        await show_mirror_menu(msg, context, result)
    except Exception as e:
        from utils.queue import TaskStoppedError
        if isinstance(e, TaskStoppedError):
            await msg.edit_text(f"🛑 Download dihentikan.")
        else:
            await msg.edit_text(f"❌ Error: `{str(e)}`", parse_mode=ParseMode.MARKDOWN)

async def github_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /gh <url>"""
    if not context.args:
        await update.message.reply_text("❌ Gunakan: `/gh <github_url>`", parse_mode=ParseMode.MARKDOWN)
        return

    url = context.args[0]
    context.user_data['current_url'] = url
    context.user_data['platform'] = 'github'

    fake_update = type('obj', (object,), {
        'message': update.message,
        'effective_user': update.effective_user
    })()

    from handlers.download import handle_github_url
    await handle_github_url(fake_update, context, url)

async def terabox_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /tb <url>"""
    if not context.args:
        await update.message.reply_text("❌ Gunakan: `/tb <terabox_url>`", parse_mode=ParseMode.MARKDOWN)
        return

    url = context.args[0]
    context.user_data['current_url'] = url
    context.user_data['platform'] = 'terabox'

    fake_update = type('obj', (object,), {
        'message': update.message,
        'effective_user': update.effective_user
    })()

    from handlers.download import handle_terabox_url
    await handle_terabox_url(fake_update, context, url)

async def dl_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /dl <url> - download langsung"""
    if not context.args:
        await update.message.reply_text("❌ Gunakan: `/dl <url>`", parse_mode=ParseMode.MARKDOWN)
        return

    url = context.args[0]
    context.user_data['current_url'] = url
    context.user_data['platform'] = 'direct'

    msg = await update.message.reply_text("⬇️ Memulai download...")

    from utils.progress import ProgressTracker
    from downloaders.general import GeneralDownloader
    from utils.queue import queue, TaskStatus

    gen = GeneralDownloader()
    tracker = ProgressTracker(msg, "Downloading")

    qtask = queue.create_task(
        user_id=update.effective_user.id,
        chat_id=update.effective_chat.id,
        url=url,
        platform='direct',
        filename_hint=url.split('/')[-1][:50]
    )
    qtask.status = TaskStatus.DOWNLOADING

    try:
        result = await gen.download(url, progress_tracker=tracker, task=qtask)
        qtask.status = TaskStatus.COMPLETED
        context.user_data['downloaded_files'] = result['files']
        context.user_data['download_result'] = result
        await show_mirror_menu(msg, context, result)
    except Exception as e:
        from utils.queue import TaskStoppedError
        if isinstance(e, TaskStoppedError):
            await msg.edit_text(f"🛑 Download dihentikan.")
        else:
            await msg.edit_text(f"❌ Error: `{str(e)}`", parse_mode=ParseMode.MARKDOWN)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors"""
    logger.error(f"Error: {context.error}", exc_info=context.error)

    if update and hasattr(update, 'effective_message') and update.effective_message:
        await update.effective_message.reply_text(
            f"⚠️ **Terjadi Error**\n\n"
            f"`{str(context.error)[:200]}`\n\n"
            f"Coba lagi atau gunakan /start",
            parse_mode=ParseMode.MARKDOWN
        )

def main():
    """Main function"""
    # Init database
    init_db()
    logger.info("Database initialized")

    # Pastikan download dir ada
    from utils.helpers import ensure_download_dir
    ensure_download_dir()

    # Build application
    application = Application.builder().token(Config.BOT_TOKEN).build()

    # ── Command handlers ──────────────────────────────────────────────
    # Info & Help
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("history", history_command))

    # AI
    application.add_handler(CommandHandler("ai", ai_command))
    application.add_handler(CommandHandler("analyze", analyze_command))
    application.add_handler(CommandHandler("clear", clear_ai_command))

    # Download
    application.add_handler(CommandHandler("yt", yt_command))
    application.add_handler(CommandHandler("ytmp3", ytmp3_command))
    application.add_handler(CommandHandler("gh", github_command))
    application.add_handler(CommandHandler("tb", terabox_command))
    application.add_handler(CommandHandler("dl", dl_command))
    application.add_handler(CommandHandler("retry", retry_command))

    # Download Control (Queue)
    application.add_handler(CommandHandler("queue", queue_command))
    application.add_handler(CommandHandler("pause", pause_command))
    application.add_handler(CommandHandler("resume", resume_command))
    application.add_handler(CommandHandler("stop", stop_command))

    # Mirror
    application.add_handler(CommandHandler("mirror", mirror_command))
    application.add_handler(CommandHandler("gdrive", gdrive_command))
    application.add_handler(CommandHandler("gofile", gofile_command))

    # Owner Only
    application.add_handler(CommandHandler("broadcast", broadcast_command))
    application.add_handler(CommandHandler("ban", ban_command))
    application.add_handler(CommandHandler("unban", unban_command))

    # Utility
    application.add_handler(CommandHandler("cleanup", cleanup_command))

    # Callback query handler
    application.add_handler(CallbackQueryHandler(button_handler))

    # Message handler (URL dan teks biasa)
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        message_handler
    ))

    # Periodic cleanup background task
    loop = asyncio.get_event_loop()
    from utils.cleanup import periodic_cleanup
    loop.create_task(periodic_cleanup())
    logger.info("Periodic cleanup task scheduled")

    # Error handler
    application.add_error_handler(error_handler)

    logger.info("Bot started! Polling...")
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )

if __name__ == '__main__':
    main()

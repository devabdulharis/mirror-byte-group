from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from utils.helpers import get_system_stats, is_authorized
from utils.database import get_session, UserSession
from datetime import datetime

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /start"""
    user = update.effective_user

    # Register user ke database
    session = get_session()
    user_stat = session.query(UserSession).filter_by(user_id=user.id).first()
    if not user_stat:
        user_stat = UserSession(
            user_id=user.id,
            username=user.username or user.first_name
        )
        session.add(user_stat)
        session.commit()
    else:
        user_stat.last_active = datetime.utcnow()
        session.commit()
    session.close()

    text = (
        f"👋 **Halo, {user.first_name}!**\n\n"
        f"🤖 Selamat datang di **Download Manager Bot**\n\n"
        f"**Apa yang bisa saya lakukan?**\n\n"
        f"📥 **Download dari:**\n"
        f"  • 🎬 YouTube (MP3/Video/Playlist)\n"
        f"  • 📁 GitHub (Clone/ZIP)\n"
        f"  • 📦 Terabox\n"
        f"  • 🌐 URL langsung (semua format)\n"
        f"  • 🎵 1000+ platform via yt-dlp\n\n"
        f"☁️ **Mirror ke:**\n"
        f"  • 📱 Telegram Storage\n"
        f"  • ☁️ Google Drive\n"
        f"  • 📂 GoFile.io\n"
        f"  • 📦 Terabox\n\n"
        f"🤖 **AI Assistant** terintegrasi!\n\n"
        f"**Cara pakai:** Langsung kirim URL atau gunakan perintah di bawah!"
    )

    keyboard = [
        [InlineKeyboardButton("📥 Download", callback_data="menu_download"),
         InlineKeyboardButton("☁️ Mirror", callback_data="menu_mirror")],
        [InlineKeyboardButton("🤖 Chat AI", callback_data="menu_ai"),
         InlineKeyboardButton("📊 Status", callback_data="menu_status")],
        [InlineKeyboardButton("❓ Bantuan", callback_data="menu_help"),
         InlineKeyboardButton("⚙️ Settings", callback_data="menu_settings")]
    ]

    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /help"""
    text = (
        "📖 **Panduan Lengkap DLBot**\n\n"

        "**📥 Download Commands:**\n"
        "`/yt <url>` - Download YouTube\n"
        "`/ytmp3 <url>` - YouTube ke MP3\n"
        "`/gh <url>` - Clone GitHub repo\n"
        "`/tb <url>` - Download Terabox\n"
        "`/dl <url>` - Download langsung\n"
        "`/retry` - Ulang download terakhir yang gagal\n\n"

        "**🎮 Download Control:**\n"
        "`/queue` - Lihat antrean download\n"
        "`/pause <id>` - Pause download\n"
        "`/resume <id>` - Resume download\n"
        "`/stop <id>` - Stop download\n\n"

        "**☁️ Mirror Commands:**\n"
        "`/mirror` - Mirror file terakhir\n"
        "`/gdrive` - Upload ke Google Drive\n"
        "`/gofile` - Upload ke GoFile\n\n"

        "**🤖 AI Commands:**\n"
        "`/ai <pesan>` - Chat dengan AI\n"
        "`/analyze <url>` - Analisis URL dengan AI\n"
        "`/clear` - Hapus riwayat chat AI\n\n"

        "**📊 Info Commands:**\n"
        "`/status` - Status bot & sistem\n"
        "`/history` - Riwayat download\n"
        "`/stats` - Statistik kamu\n\n"

        "**🧹 Utility:**\n"
        "`/cleanup` - Hapus semua file lokal\n\n"

        "**💡 Tips:**\n"
        "• Kirim URL langsung tanpa perintah!\n"
        "• Bot mendukung 1000+ platform via yt-dlp\n"
        "• File bisa di-mirror ke banyak platform sekaligus\n"
        "• Tanya AI jika ada masalah download\n"
        "• `/queue` untuk lihat status download aktif"
    )

    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /status"""
    stats = get_system_stats()

    text = (
        f"📊 **Status Bot**\n\n"
        f"**💻 Sistem:**\n"
        f"  🖥️ CPU: `{stats['cpu']}%`\n"
        f"  🧠 RAM: `{stats['ram']}%`\n"
        f"  💾 Disk Free: `{stats['disk_free']}`\n"
        f"  💾 Disk Used: `{stats['disk_used']}`\n\n"
        f"**🤖 Bot Status:** ✅ Online\n"
        f"**🌐 AI Status:** ✅ Ready\n"
    )

    # Cek konfigurasi mirror
    from config import Config
    from mirrors.gdrive import GoogleDriveMirror
    from mirrors.terabox_mirror import TeraboxMirror

    gdrive = GoogleDriveMirror()
    terabox = TeraboxMirror()

    text += "\n**☁️ Mirror Status:**\n"
    text += f"  📱 Telegram: ✅\n"
    text += f"  ☁️ Google Drive: {'✅' if gdrive.is_available() else '❌ (perlu setup)'}\n"
    text += f"  📂 GoFile.io: ✅\n"
    text += f"  📦 Terabox: {'✅' if terabox.is_available() else '❌ (perlu cookie)'}\n"

    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /stats - statistik user"""
    user_id = update.effective_user.id
    session = get_session()

    user_stat = session.query(UserSession).filter_by(user_id=user_id).first()
    tasks = session.query(DownloadTask).filter_by(user_id=user_id).order_by(
        DownloadTask.created_at.desc()
    ).limit(5).all()
    session.close()

    if not user_stat:
        await update.message.reply_text("❌ Data tidak ditemukan.")
        return

    from utils.helpers import format_size

    text = (
        f"📈 **Statistik Kamu**\n\n"
        f"👤 Username: `@{user_stat.username or 'Unknown'}`\n"
        f"📥 Total Download: `{user_stat.total_downloads}`\n"
        f"💾 Total Size: `{format_size(user_stat.total_size)}`\n"
        f"📅 Bergabung: `{user_stat.created_at.strftime('%d %b %Y')}`\n\n"
        f"**5 Download Terakhir:**\n"
    )

    for task in tasks:
        status_icon = "✅" if task.status == "completed" else "❌" if task.status == "failed" else "⏳"
        text += f"{status_icon} `{task.url[:40]}...` ({task.platform})\n"

    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

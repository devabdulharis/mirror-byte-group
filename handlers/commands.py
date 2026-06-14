"""
Command handlers tambahan:
- /mirror, /gdrive, /gofile → mirror
- /history, /queue → informasi
- /pause, /resume, /stop → kontrol download
- /retry → ulang download
- /broadcast, /ban, /unban → owner only
- /cleanup → hapus file lokal
"""

import os
import asyncio
import logging
import shutil
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from config import Config
from utils.database import get_session, DownloadTask, UserSession, MirrorTask
from utils.helpers import format_size, is_authorized
from utils.queue import queue, TaskStatus
from handlers.mirror import process_mirror
from handlers.download import show_mirror_menu

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
#  MIRROR COMMANDS
# ═══════════════════════════════════════════════════════════════════════

async def mirror_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /mirror — mirror file terakhir yang sudah didownload"""
    files = context.user_data.get('downloaded_files', [])
    if not files:
        await update.message.reply_text(
            "❌ **Tidak ada file untuk di-mirror.**\n\n"
            "Download file terlebih dahulu, lalu gunakan /mirror lagi.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    result = context.user_data.get('download_result', {'files': files, 'total_size': 0})
    msg = await update.message.reply_text("☁️ Menyiapkan menu mirror...")
    await show_mirror_menu(msg, context, result)


async def gdrive_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /gdrive — upload file terakhir ke Google Drive langsung"""
    files = context.user_data.get('downloaded_files', [])
    if not files:
        await update.message.reply_text(
            "❌ **Tidak ada file untuk diupload.**\n\n"
            "Download file terlebih dahulu.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    from mirrors.gdrive import GoogleDriveMirror
    gdrive = GoogleDriveMirror()

    if not gdrive.is_available():
        await update.message.reply_text(
            "❌ **Google Drive tidak dikonfigurasi.**\n\n"
            "Set `GDRIVE_CREDENTIALS_JSON` di file `.env`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    msg = await update.message.reply_text("☁️ **Upload ke Google Drive...**", parse_mode=ParseMode.MARKDOWN)

    for file_path in files:
        if not os.path.exists(file_path):
            await msg.edit_text(f"❌ File tidak ditemukan: `{os.path.basename(file_path)}`")
            continue

        await msg.edit_text(
            f"☁️ **Upload ke GDrive...**\n📁 `{os.path.basename(file_path)}`",
            parse_mode=ParseMode.MARKDOWN
        )
        result = await gdrive.upload(file_path)

        if result.get('success'):
            link = result.get('link', '')
            text = f"✅ **Upload selesai!**\n📁 `{os.path.basename(file_path)}`\n"
            if link:
                text += f"🔗 [Buka di GDrive]({link})"
            await msg.edit_text(text, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)
        else:
            await msg.edit_text(
                f"❌ Gagal upload: `{result.get('error', 'Unknown error')}`",
                parse_mode=ParseMode.MARKDOWN
            )


async def gofile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /gofile — upload file terakhir ke GoFile langsung"""
    files = context.user_data.get('downloaded_files', [])
    if not files:
        await update.message.reply_text(
            "❌ **Tidak ada file untuk diupload.**\n\n"
            "Download file terlebih dahulu.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    from mirrors.gofile import GoFileMirror
    gofile = GoFileMirror()

    msg = await update.message.reply_text("📂 **Upload ke GoFile.io...**", parse_mode=ParseMode.MARKDOWN)

    for file_path in files:
        if not os.path.exists(file_path):
            continue

        await msg.edit_text(
            f"📂 **Upload ke GoFile...**\n📁 `{os.path.basename(file_path)}`",
            parse_mode=ParseMode.MARKDOWN
        )
        result = await gofile.upload(file_path)

        if result.get('success'):
            link = result.get('link', '')
            text = f"✅ **Upload selesai!**\n📁 `{os.path.basename(file_path)}`\n"
            if link:
                text += f"🔗 [Download di GoFile]({link})"
            await msg.edit_text(text, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)
        else:
            await msg.edit_text(
                f"❌ Gagal upload: `{result.get('error', 'Unknown error')}`",
                parse_mode=ParseMode.MARKDOWN
            )


# ═══════════════════════════════════════════════════════════════════════
#  DOWNLOAD CONTROL COMMANDS
# ═══════════════════════════════════════════════════════════════════════

async def queue_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /queue — lihat status antrean download"""
    user_id = update.effective_user.id
    tasks = queue.get_user_tasks(user_id)

    if not tasks:
        await update.message.reply_text(
            "📋 **Antrean Download**\n\n"
            "Kosong. Tidak ada task download aktif.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    text = "📋 **Antrean Download Kamu**\n\n"
    for i, t in enumerate(tasks, 1):
        status_emoji = t.status.emoji()
        progress = f"{t.progress_pct:.1f}%" if t.status == TaskStatus.DOWNLOADING else ""
        filename = t.filename_hint or t.url[:40]
        text += f"{i}. {status_emoji} `{filename}`\n"
        text += f"   ID: `{t.id}` | Status: **{t.status.value}** {progress}\n\n"

    # Tombol cleanup
    keyboard = [
        [InlineKeyboardButton("🗑️ Bersihkan Selesai", callback_data="queue_cleanup")],
        [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu")]
    ]

    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )


async def pause_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /pause <task_id> — pause download"""
    if not context.args:
        task_id = _get_latest_active_task(update.effective_user.id)
        if not task_id:
            await update.message.reply_text(
                "❌ Gunakan: `/pause <task_id>`\n\n"
                "Cek task ID dengan /queue",
                parse_mode=ParseMode.MARKDOWN
            )
            return
    else:
        task_id = context.args[0]

    if queue.pause_task(task_id):
        await update.message.reply_text(
            f"⏸️ **Download Dipause**\n\nTask: `{task_id}`\n\n"
            f"Gunakan `/resume {task_id}` untuk melanjutkan.",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await update.message.reply_text(
            f"❌ Gagal pause task `{task_id}`.\n"
            f"Pastikan task sedang **downloading**.",
            parse_mode=ParseMode.MARKDOWN
        )


async def resume_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /resume <task_id> — resume download"""
    if not context.args:
        task_id = _get_latest_paused_task(update.effective_user.id)
        if not task_id:
            await update.message.reply_text(
                "❌ Gunakan: `/resume <task_id>`\n\n"
                "Cek task ID dengan /queue",
                parse_mode=ParseMode.MARKDOWN
            )
            return
    else:
        task_id = context.args[0]

    if queue.resume_task(task_id):
        await update.message.reply_text(
            f"▶️ **Download Dilanjutkan**\n\nTask: `{task_id}`",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await update.message.reply_text(
            f"❌ Gagal resume task `{task_id}`.\n"
            f"Pastikan task sedang **paused**.",
            parse_mode=ParseMode.MARKDOWN
        )


async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /stop <task_id> — stop/ cancel download"""
    if not context.args:
        task_id = _get_latest_active_task(update.effective_user.id)
        if not task_id:
            await update.message.reply_text(
                "❌ Gunakan: `/stop <task_id>`\n\n"
                "Cek task ID dengan /queue",
                parse_mode=ParseMode.MARKDOWN
            )
            return
    else:
        task_id = context.args[0]

    if queue.stop_task(task_id):
        task = queue.get_task(task_id)
        filename_hint = task.filename_hint if task else ""

        # Hapus file partial
        if task and task.file_paths:
            for fp in task.file_paths:
                if os.path.exists(fp):
                    os.remove(fp)
                part_fp = fp + ".part"
                if os.path.exists(part_fp):
                    os.remove(part_fp)

        await update.message.reply_text(
            f"🛑 **Download Dihentikan**\n\n"
            f"Task: `{task_id}`\n"
            f"File: `{filename_hint}`\n"
            f"Partial files telah dibersihkan.",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await update.message.reply_text(
            f"❌ Gagal stop task `{task_id}`.\n"
            f"Task mungkin sudah selesai atau tidak ditemukan.",
            parse_mode=ParseMode.MARKDOWN
        )


async def retry_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /retry — ulang download terakhir yang gagal"""
    user_id = update.effective_user.id
    session = get_session()

    # Cari task gagal terakhir dari database
    failed_task = session.query(DownloadTask).filter_by(
        user_id=user_id, status='failed'
    ).order_by(DownloadTask.created_at.desc()).first()
    session.close()

    if not failed_task:
        await update.message.reply_text(
            "❌ **Tidak ada download yang gagal** untuk diulang.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Set URL di context dan trigger download ulang
    context.user_data['current_url'] = failed_task.url
    context.user_data['platform'] = failed_task.platform

    from handlers.download import handle_url
    await handle_url(update, context)


async def cleanup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /cleanup — hapus semua file download lokal yang sudah di-mirror"""
    download_path = Config.DOWNLOAD_PATH
    deleted = 0
    size_freed = 0

    for f in os.listdir(download_path):
        file_path = os.path.join(download_path, f)
        if os.path.isfile(file_path):
            size_freed += os.path.getsize(file_path)
            os.remove(file_path)
            deleted += 1

    # Hapus file partial (.part)
    for f in os.listdir(download_path):
        if f.endswith('.part'):
            file_path = os.path.join(download_path, f)
            os.remove(file_path)

    # Hapus subdirektori hasil playlist
    for f in os.listdir(download_path):
        dir_path = os.path.join(download_path, f)
        if os.path.isdir(dir_path):
            shutil.rmtree(dir_path, ignore_errors=True)

    await update.message.reply_text(
        f"🧹 **Cleanup Selesai!**\n\n"
        f"🗑️ {deleted} file dihapus\n"
        f"💾 {format_size(size_freed)} ruang dibebaskan\n"
        f"📁 Direktori: `{download_path}`",
        parse_mode=ParseMode.MARKDOWN
    )


# ═══════════════════════════════════════════════════════════════════════
#  HISTORY
# ═══════════════════════════════════════════════════════════════════════

async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /history — riwayat download user"""
    user_id = update.effective_user.id
    session = get_session()

    # Ambil 10 download terakhir
    tasks = session.query(DownloadTask).filter_by(
        user_id=user_id
    ).order_by(DownloadTask.created_at.desc()).limit(10).all()
    session.close()

    if not tasks:
        await update.message.reply_text(
            "📜 **Riwayat Download**\n\n"
            "Belum ada riwayat download.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    text = "📜 **Riwayat Download (10 terakhir)**\n\n"
    for i, task in enumerate(tasks, 1):
        status_icon = "✅" if task.status == "completed" else "❌" if task.status == "failed" else "⏳"
        url_short = task.url[:40] + "…" if len(task.url) > 40 else task.url
        created = task.created_at.strftime("%d/%m %H:%M")
        text += f"{i}. {status_icon} `{url_short}`\n"
        text += f"   📅 {created} | 📁 {task.platform}"
        if task.file_size:
            text += f" | 💾 {format_size(task.file_size)}"
        text += "\n\n"

    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


# ═══════════════════════════════════════════════════════════════════════
#  OWNER ONLY COMMANDS
# ═══════════════════════════════════════════════════════════════════════

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /broadcast <pesan> — kirim pesan ke semua user (owner only)"""
    if update.effective_user.id != Config.OWNER_ID:
        await update.message.reply_text("⛔ **Hanya owner** yang bisa menggunakan command ini.", parse_mode=ParseMode.MARKDOWN)
        return

    if not context.args:
        await update.message.reply_text("❌ Gunakan: `/broadcast <pesan>`", parse_mode=ParseMode.MARKDOWN)
        return

    message = ' '.join(context.args)
    session = get_session()
    users = session.query(UserSession).all()
    session.close()

    sent = 0
    failed = 0
    for user in users:
        try:
            await context.bot.send_message(
                chat_id=user.user_id,
                text=f"📢 **Broadcast dari Owner**\n\n{message}",
                parse_mode=ParseMode.MARKDOWN
            )
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)  # Rate limit

    await update.message.reply_text(
        f"📢 **Broadcast selesai**\n\n"
        f"✅ Terkirim: {sent}\n"
        f"❌ Gagal: {failed}",
        parse_mode=ParseMode.MARKDOWN
    )


async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /ban <user_id> — ban user (owner only)"""
    if update.effective_user.id != Config.OWNER_ID:
        await update.message.reply_text("⛔ Hanya owner yang bisa menggunakan command ini.")
        return

    if not context.args:
        await update.message.reply_text("❌ Gunakan: `/ban <user_id>`", parse_mode=ParseMode.MARKDOWN)
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ User ID harus berupa angka.")
        return

    session = get_session()
    user = session.query(UserSession).filter_by(user_id=target_id).first()
    if user:
        user.is_banned = True
        session.commit()
        session.close()
        await update.message.reply_text(f"✅ User `{target_id}` telah di-ban.", parse_mode=ParseMode.MARKDOWN)
    else:
        session.close()
        await update.message.reply_text(f"❌ User `{target_id}` tidak ditemukan di database.", parse_mode=ParseMode.MARKDOWN)


async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /unban <user_id> — unban user (owner only)"""
    if update.effective_user.id != Config.OWNER_ID:
        await update.message.reply_text("⛔ Hanya owner yang bisa menggunakan command ini.")
        return

    if not context.args:
        await update.message.reply_text("❌ Gunakan: `/unban <user_id>`", parse_mode=ParseMode.MARKDOWN)
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ User ID harus berupa angka.")
        return

    session = get_session()
    user = session.query(UserSession).filter_by(user_id=target_id).first()
    if user:
        user.is_banned = False
        session.commit()
        session.close()
        await update.message.reply_text(f"✅ User `{target_id}` telah di-unban.", parse_mode=ParseMode.MARKDOWN)
    else:
        session.close()
        await update.message.reply_text(f"❌ User `{target_id}` tidak ditemukan.", parse_mode=ParseMode.MARKDOWN)


# ═══════════════════════════════════════════════════════════════════════
#  SETTINGS MENU
# ═══════════════════════════════════════════════════════════════════════

async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk menu settings (callback)"""
    query = update.callback_query
    await query.answer()

    text = (
        "⚙️ **Settings**\n\n"
        f"📥 Maks file Telegram: `{Config.MAX_FILE_SIZE_TG // (1024*1024)} MB`\n"
        f"📂 Download path: `{Config.DOWNLOAD_PATH}`\n"
        f"🔄 Max concurrent downloads: `{queue._max_global}`\n"
        f"👤 Max per user: `{queue._max_per_user}`\n\n"
        f"**Commands:**\n"
        f"• `/cleanup` — Hapus semua file lokal\n"
        f"• `/queue` — Lihat antrean download\n"
    )

    keyboard = [
        [InlineKeyboardButton("🗑️ Cleanup File", callback_data="cleanup_now")],
        [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu")]
    ]

    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )


async def cleanup_now_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback untuk cleanup dari settings menu"""
    query = update.callback_query
    await query.answer()

    download_path = Config.DOWNLOAD_PATH
    deleted = 0
    size_freed = 0

    for f in os.listdir(download_path):
        file_path = os.path.join(download_path, f)
        if os.path.isfile(file_path):
            size_freed += os.path.getsize(file_path)
            os.remove(file_path)
            deleted += 1

    for f in os.listdir(download_path):
        dir_path = os.path.join(download_path, f)
        if os.path.isdir(dir_path):
            shutil.rmtree(dir_path, ignore_errors=True)

    await query.message.edit_text(
        f"🧹 **Cleanup Selesai!**\n\n"
        f"🗑️ {deleted} file dihapus\n"
        f"💾 {format_size(size_freed)} ruang dibebaskan",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu")
        ]])
    )


async def queue_cleanup_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback untuk bersihkan task selesai dari queue"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    queue.cleanup_completed(user_id)

    await query.message.edit_text(
        "🗑️ **Task selesai dibersihkan!**\n\n"
        "Gunakan /queue untuk melihat antrean terkini.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("📋 Lihat Queue", callback_data="view_queue"),
            InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu")
        ]])
    )


async def view_queue_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback untuk lihat queue dari menu"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    tasks = queue.get_user_tasks(user_id)
    if not tasks:
        await query.message.edit_text(
            "📋 **Antrean Download**\n\nKosong.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu")
            ]])
        )
        return

    text = "📋 **Antrean Download Kamu**\n\n"
    for t in tasks:
        text += f"{t.status.emoji()} `{t.id}` — **{t.status.value}**\n"
        text += f"   📁 {t.filename_hint or t.url[:40]}\n"
        if t.progress_pct > 0:
            text += f"   📊 {t.progress_pct:.1f}%\n"

    keyboard = [
        [InlineKeyboardButton("🗑️ Bersihkan", callback_data="queue_cleanup")],
        [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu")]
    ]
    await query.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))


# ═══════════════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════════════

def _get_latest_active_task(user_id: int) -> str | None:
    """Cari task aktif terakhir milik user"""
    tasks = queue.get_user_tasks(user_id)
    active = [t for t in tasks if t.status in (TaskStatus.DOWNLOADING, TaskStatus.PAUSED)]
    if active:
        return active[-1].id
    return None


def _get_latest_paused_task(user_id: int) -> str | None:
    """Cari task paused terakhir milik user"""
    tasks = queue.get_user_tasks(user_id)
    paused = [t for t in tasks if t.status == TaskStatus.PAUSED]
    if paused:
        return paused[-1].id
    return None

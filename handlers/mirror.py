import os
import json
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from mirrors.telegram_mirror import TelegramMirror
from mirrors.gdrive import GoogleDriveMirror
from mirrors.gofile import GoFileMirror
from mirrors.terabox_mirror import TeraboxMirror
from utils.helpers import format_size
from utils.mirror_progress import MirrorProgressTracker

gdrive_mirror = GoogleDriveMirror()
gofile_mirror = GoFileMirror()
terabox_mirror = TeraboxMirror()


async def process_mirror(update: Update, context: ContextTypes.DEFAULT_TYPE, platform: str):
    """Process mirroring ke platform tertentu dengan progress tracking"""
    query = update.callback_query
    files = context.user_data.get('downloaded_files', [])

    if not files:
        await query.message.edit_text("❌ Tidak ada file untuk di-mirror.")
        return

    tg_mirror = TelegramMirror(query.get_bot())

    msg = query.message
    results = []

    if platform == "all":
        platforms = ["telegram", "gdrive", "gofile", "terabox"]
    else:
        platforms = [platform]

    total_ops = len(files) * len(platforms)
    current_op = 0

    for file_path in files:
        if not os.path.exists(file_path):
            continue

        file_results = {'file': os.path.basename(file_path), 'mirrors': {}}

        for plat in platforms:
            current_op += 1
            filename = os.path.basename(file_path)

            # Buat progress tracker spesifik per platform
            plat_emoji = {"telegram": "📱", "gdrive": "☁️", "gofile": "📂", "terabox": "📦"}
            plat_name = {"telegram": "Telegram", "gdrive": "Google Drive", "gofile": "GoFile.io", "terabox": "Terabox"}
            tracker = MirrorProgressTracker(msg, plat_name.get(plat, plat))

            await msg.edit_text(
                f"{plat_emoji.get(plat, '📤')} **Upload ke {plat_name.get(plat, plat)}**\n\n"
                f"📁 File: `{filename}`\n"
                f"📊 Progress: `{current_op}/{total_ops}`\n\n"
                f"⏳ Menyiapkan...",
                parse_mode=ParseMode.MARKDOWN
            )

            result = None

            if plat == "telegram":
                caption = f"📥 Downloaded by @{(await query.get_bot().get_me()).username}"
                result = await tg_mirror.upload(file_path, query.message.chat_id, caption, msg)

            elif plat == "gdrive":
                if gdrive_mirror.is_available():
                    result = await gdrive_mirror.upload(file_path, progress_tracker=tracker)
                else:
                    result = {'success': False, 'error': 'Google Drive tidak dikonfigurasi', 'platform': 'gdrive'}

            elif plat == "gofile":
                result = await gofile_mirror.upload(file_path, progress_tracker=tracker)

            elif plat == "terabox":
                if terabox_mirror.is_available():
                    result = await terabox_mirror.upload(file_path, progress_tracker=tracker)
                else:
                    result = {'success': False, 'error': 'Terabox tidak dikonfigurasi', 'platform': 'terabox'}

            if result:
                file_results['mirrors'][plat] = result

        results.append(file_results)

    # Tampilkan hasil
    await show_mirror_results(msg, context, results)


async def show_mirror_results(message, context: ContextTypes.DEFAULT_TYPE, results: list):
    """Tampilkan hasil mirroring — kirim pesan BARU dengan link klikable"""
    bot = context.bot
    chat_id = message.chat_id
    from html import escape

    text = "✅ <b>Mirror Selesai!</b>\n\n"

    for file_result in results:
        safe_file = escape(file_result['file'])
        text += f"📁 <b>{safe_file}</b>\n"

        for platform, result in file_result['mirrors'].items():
            if result.get('success'):
                icon = {'telegram': '📱', 'gdrive': '☁️', 'gofile': '📂', 'terabox': '📦'}.get(platform, '🔗')
                link = result.get('link', '')

                if platform == 'telegram':
                    if link:
                        safe_link = escape(link)
                        text += f'{icon} Telegram: <a href="{safe_link}">📱 Buka di Telegram</a>\n'
                    else:
                        text += f"{icon} Telegram: ✅ (private chat — link tidak tersedia)\n"

                elif platform == 'gdrive':
                    if link:
                        safe_link = escape(link)
                        text += f'{icon} GDrive: <a href="{safe_link}">☁️ Buka di Google Drive</a>\n'
                    else:
                        text += f"{icon} GDrive: ✅\n"

                elif platform == 'gofile':
                    if link:
                        safe_link = escape(link)
                        text += f'{icon} GoFile: <a href="{safe_link}">📂 Download dari GoFile</a>\n'
                    else:
                        text += f"{icon} GoFile: ✅\n"

                elif platform == 'terabox':
                    if link:
                        safe_link = escape(link)
                        text += f'{icon} Terabox: <a href="{safe_link}">📦 Buka di Terabox</a>\n'
                    else:
                        text += f"{icon} Terabox: ✅ {escape(str(result.get('path', '')))}\n"
            else:
                text += f"❌ {platform}: {escape(str(result.get('error', 'Unknown error')))}\n"

        text += "\n"

    keyboard = [
        [InlineKeyboardButton("🗑️ Hapus File Lokal", callback_data="delete_local")],
        [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu")]
    ]

    # Simpan mirror results ke context
    context.user_data['mirror_results'] = results

    # Kirim pesan BARU dengan hasil — jangan edit pesan progress
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )
    except Exception as e:
        # Fallback: edit pesan lama kalau send_message gagal
        await message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )

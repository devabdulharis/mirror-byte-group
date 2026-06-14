import os
from telegram import Bot, Message
from telegram.error import TelegramError
from config import Config
from utils.helpers import format_size

class TelegramMirror:
    def __init__(self, bot: Bot):
        self.bot = bot

    async def upload(self, file_path: str, chat_id: int,
                     caption: str = "", message: Message = None) -> dict:
        """Upload file ke Telegram sebagai storage"""
        file_size = os.path.getsize(file_path)

        if file_size > Config.MAX_FILE_SIZE_TG:
            return {
                'success': False,
                'error': f'File terlalu besar ({format_size(file_size)}). Max Telegram: {format_size(Config.MAX_FILE_SIZE_TG)}',
                'platform': 'telegram'
            }

        filename = os.path.basename(file_path)
        ext = os.path.splitext(filename)[1].lower()

        # Pilih metode upload berdasarkan tipe file
        try:
            if message:
                await message.edit_text(f"📤 Uploading ke Telegram...\n📁 `{filename}`\n💾 {format_size(file_size)}",
                                         parse_mode="Markdown")

            with open(file_path, 'rb') as f:
                if ext in ['.mp4', '.mkv', '.avi', '.mov']:
                    sent = await self.bot.send_video(
                        chat_id=chat_id,
                        video=f,
                        caption=caption or f"🎬 {filename}",
                        supports_streaming=True,
                        filename=filename
                    )
                    file_id = sent.video.file_id

                elif ext in ['.mp3', '.ogg', '.flac', '.wav', '.m4a']:
                    sent = await self.bot.send_audio(
                        chat_id=chat_id,
                        audio=f,
                        caption=caption or f"🎵 {filename}",
                        filename=filename
                    )
                    file_id = sent.audio.file_id

                elif ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
                    sent = await self.bot.send_photo(
                        chat_id=chat_id,
                        photo=f,
                        caption=caption or f"🖼️ {filename}"
                    )
                    file_id = sent.photo[-1].file_id

                else:
                    sent = await self.bot.send_document(
                        chat_id=chat_id,
                        document=f,
                        caption=caption or f"📄 {filename}",
                        filename=filename
                    )
                    file_id = sent.document.file_id

            return {
                'success': True,
                'platform': 'telegram',
                'file_id': file_id,
                'message_id': sent.message_id,
                'link': f"https://t.me/c/{str(chat_id)[4:]}/{sent.message_id}" if str(chat_id).startswith('-100') else None
            }

        except TelegramError as e:
            return {
                'success': False,
                'error': str(e),
                'platform': 'telegram'
            }

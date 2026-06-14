import json
from openai import OpenAI
from config import Config

client = OpenAI(
    api_key=Config.AI_API_KEY,
    base_url=Config.AI_BASE_URL,
)

SYSTEM_PROMPT = """Kamu adalah AI assistant untuk Telegram Download Manager Bot bernama "DLBot".
Kamu membantu pengguna dengan:
1. Menjelaskan cara menggunakan bot
2. Menganalisis URL dan menentukan platform yang tepat
3. Memberikan rekomendasi kualitas download
4. Troubleshooting masalah download
5. Menjawab pertanyaan umum tentang format file

Jawab dalam Bahasa Indonesia, singkat, jelas, dan helpful.
Gunakan emoji yang relevan untuk membuat percakapan lebih menarik.
Jika ada URL, analisis dan berikan informasi yang berguna."""

class AIHandler:
    def __init__(self):
        self.conversations = {}  # user_id -> conversation history
        self.max_history = 10

    def get_history(self, user_id: int) -> list:
        return self.conversations.get(user_id, [])

    def add_to_history(self, user_id: int, role: str, content: str):
        if user_id not in self.conversations:
            self.conversations[user_id] = []

        self.conversations[user_id].append({
            "role": role,
            "content": content
        })

        # Keep only last N messages
        if len(self.conversations[user_id]) > self.max_history * 2:
            self.conversations[user_id] = self.conversations[user_id][-self.max_history * 2:]

    def clear_history(self, user_id: int):
        self.conversations[user_id] = []

    async def chat(self, user_id: int, message: str) -> str:
        """Chat dengan AI via OpenAI-compatible API"""
        import asyncio

        self.add_to_history(user_id, "user", message)
        history = self.get_history(user_id)

        def do_request():
            response = client.chat.completions.create(
                model=Config.AI_MODEL,
                max_tokens=1024,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    *history
                ]
            )
            return response.choices[0].message.content

        try:
            response = await asyncio.to_thread(do_request)
            # Handle empty response
            if not response:
                response = "Maaf, saya tidak bisa merespon saat ini. Coba lagi ya."
            self.add_to_history(user_id, "assistant", response)
            return response
        except Exception as e:
            return f"❌ AI Error: {str(e)}\n\nCoba lagi beberapa saat."

    async def analyze_url(self, url: str) -> str:
        """Analisis URL dengan AI"""
        import asyncio

        prompt = f"""Analisis URL berikut dan berikan informasi:
URL: {url}

Berikan:
1. Platform/sumber konten
2. Jenis konten yang mungkin didownload
3. Estimasi ukuran (jika bisa ditebak)
4. Tips download yang optimal
5. Potensi masalah yang mungkin muncul

Format jawaban singkat dan informatif."""

        def do_request():
            response = client.chat.completions.create(
                model=Config.AI_MODEL,
                max_tokens=512,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ]
            )
            return response.choices[0].message.content

        try:
            result = await asyncio.to_thread(do_request)
            return result or "Tidak dapat menganalisis URL tersebut."
        except Exception as e:
            return f"Tidak dapat menganalisis URL: {str(e)}"

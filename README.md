# 🤖 MBG (Mirror Byte Group)

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11%2B-blue?style=for-the-badge&logo=python" alt="Python">
  <img src="https://img.shields.io/badge/Telegram-Bot-blue?style=for-the-badge&logo=telegram" alt="Telegram">
  <img src="https://img.shields.io/badge/Docker-Ready-2496ED?style=for-the-badge&logo=docker" alt="Docker">
  <img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License">
</p>

<p align="center">
  <b>Download dari berbagai platform & upload ke berbagai cloud — langsung dari Telegram!</b><br>
  YouTube, GitHub, Terabox, URL langsung + 1000+ platform via yt-dlp<br>
  Mirror ke Telegram, Google Drive, GoFile, Terabox
</p>

---

## ✨ Fitur Unggulan

| Fitur | Status |
|-------|--------|
| 📥 **Download YouTube** (MP3 / MP4 / Playlist) | ✅ |
| 📁 **Clone GitHub Repo** (Git / ZIP / Shallow) | ✅ |
| 📦 **Download Terabox** (Multi file + subfolder) | ✅ |
| 🌐 **URL Langsung** (semua format file) | ✅ |
| 🎵 **1000+ Platform** (via yt-dlp: Instagram, TikTok, Twitter, dll) | ✅ |
| ☁️ **Mirror ke Telegram Storage** | ✅ |
| ☁️ **Mirror ke Google Drive** | ✅ |
| ☁️ **Mirror ke GoFile.io** | ✅ |
| ☁️ **Mirror ke Terabox** | ✅ |
| 🎮 **Queue System** (max concurrent, per-user limit) | ✅ |
| ⏸️ **Pause / Resume / Stop Download** | ✅ |
| 🔄 **Auto Resume** (partial download via Range header) | ✅ |
| 📊 **Progress Bar Real-time** (speed, ETA, animasi) | ✅ |
| 📤 **Progress Upload** (mirror dengan progress bar) | ✅ |
| 🤖 **AI Assistant** (analisis URL, troubleshooting) | ✅ |
| 🧹 **Auto Cleanup** (file lama otomatis dihapus) | ✅ |
| 📜 **Riwayat Download** (10 download terakhir) | ✅ |
| 🔄 **Retry** download yang gagal | ✅ |
| 👑 **Owner Controls** (broadcast, ban/unban user) | ✅ |
| 🐳 **Docker Support** | ✅ |
| ⚙️ **Systemd Service** | ✅ |

---

## 🚀 Cara Instalasi

### 🐳 Docker (Rekomendasi)

```bash
# Clone repo
git clone https://github.com/harisbit88/telegram-download-bot.git
cd telegram-download-bot

# Copy & edit konfigurasi
cp .env.example .env
nano .env   # Isi BOT_TOKEN, API_ID, API_HASH, dll

# Jalankan
docker compose up -d
```

### 🐍 Manual (Python)

```bash
# Clone repo
git clone https://github.com/harisbit88/telegram-download-bot.git
cd telegram-download-bot

# Buat virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy & edit konfigurasi
cp .env.example .env
nano .env   # Isi konfigurasi kamu

# Jalankan
python bot.py
```

### 📟 Systemd (Linux)

```bash
# Setup seperti manual di atas, lalu:
sudo cp telegram-download-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now telegram-download-bot
```

---

## 📖 Panduan Penggunaan

### 📥 Download

Kirim URL langsung ke chat, atau gunakan command:

```
/yt <url>         → Menu pilih format YouTube
/ytmp3 <url>      → Download MP3 langsung
/tb <url>         → Download dari Terabox
/gh <url>         → Clone GitHub repository
/dl <url>         → Download URL langsung
/retry            → Ulang download terakhir yang gagal
```

### 🎮 Kontrol Download

```
/queue            → Lihat antrean download
/pause <id>       → Pause download aktif
/resume <id>      → Resume download yang di-pause
/stop <id>        → Stop & batalkan download
```

### ☁️ Mirror

Setelah download selesai, pilih platform tujuan dari menu, atau gunakan:

```
/mirror           → Menu mirror untuk file terakhir
/gdrive           → Upload langsung ke Google Drive
/gofile           → Upload langsung ke GoFile.io
```

### 🤖 AI Assistant

```
/ai <pesan>       → Chat dengan AI assistant
/analyze <url>    → Analisis URL
/clear            → Reset riwayat chat AI
```

### 👑 Owner Only

```
/broadcast <msg>  → Kirim pesan ke semua user
/ban <user_id>    → Ban user
/unban <user_id>  → Unban user
```

### 🧹 Utility

```
/cleanup          → Hapus semua file download lokal
/stats            → Statistik penggunaan kamu
/history          → Riwayat download
/status           → Status bot & sistem
```

---

## ⚙️ Konfigurasi

Copy `.env.example` ke `.env` dan isi:

| Variable | Wajib | Deskripsi |
|----------|-------|-----------|
| `BOT_TOKEN` | ✅ | Token dari [@BotFather](https://t.me/botfather) |
| `API_ID` | ✅ | Dari [my.telegram.org](https://my.telegram.org) |
| `API_HASH` | ✅ | Dari [my.telegram.org](https://my.telegram.org) |
| `OWNER_ID` | ✅ | ID Telegram kamu (dari [@userinfobot](https://t.me/userinfobot)) |
| `AI_API_KEY` | ❌ | API key untuk AI assistant |
| `AI_BASE_URL` | ❌ | Base URL API (OpenAI-compatible) |
| `AI_MODEL` | ❌ | Nama model AI |
| `GDRIVE_CREDENTIALS_JSON` | ❌ | Path ke credentials.json Google Drive |
| `GDRIVE_FOLDER_ID` | ❌ | ID folder Google Drive tujuan |
| `TERABOX_COOKIE` | ❌ | Cookie browser untuk Terabox |
| `TERABOX_JS_TOKEN` | ❌ | jsToken dari Terabox |
| `GOFILE_TOKEN` | ❌ | Token dari [gofile.io](https://gofile.io) |
| `MAX_FILE_SIZE_TG` | ❌ | Maks upload ke Telegram (MB, default: 2000) |

---

## 🗂️ Struktur Project

```
telegram-download-bot/
├── bot.py                       # Entry point utama
├── config.py                    # Konfigurasi dari .env
├── requirements.txt             # Dependencies Python
├── Dockerfile                   # Container build
├── docker-compose.yml           # Container orchestration
├── telegram-download-bot.service # Systemd unit
├── deploy.sh                    # Script deploy
├── .env.example                 # Template konfigurasi
├── .gitignore                   # Ignore file sensitif
├── handlers/
│   ├── start.py                 # /start, /help, /status, /stats
│   ├── download.py              # Logic download & menu
│   ├── mirror.py                # Logic mirror & progress
│   ├── ai.py                    # AI chat handler
│   └── commands.py              # Semua command tambahan
├── downloaders/
│   ├── youtube.py               # YouTube via yt-dlp
│   ├── github.py                # GitHub clone/zip
│   ├── terabox.py               # Terabox (multi-source)
│   └── general.py               # URL langsung + yt-dlp fallback
├── mirrors/
│   ├── telegram_mirror.py       # Upload ke Telegram
│   ├── gdrive.py                # Upload ke Google Drive
│   ├── gofile.py                # Upload ke GoFile.io
│   └── terabox_mirror.py        # Upload ke Terabox
├── utils/
│   ├── database.py              # SQLAlchemy models
│   ├── helpers.py               # Utility functions
│   ├── progress.py              # Download progress bar
│   ├── mirror_progress.py       # Upload progress bar
│   ├── queue.py                 # Download queue system
│   └── cleanup.py               # Periodic auto cleanup
└── analysis-terabox.md          # Dokumentasi Terabox API
```

---

## 🔧 Technical Highlights

### Download Queue System
- **Max concurrent global**: 3 download simultan
- **Max per user**: 2 download per user
- **Task states**: pending → downloading → paused/resumed → completed/stopped/failed
- **Semaphore-based** concurrency control

### Pause / Resume
- **aiohttp downloads**: Partial file dengan `.part` extension, resume via `Range` header
- **yt-dlp downloads**: Stop via progress hook, pause via event flag
- **Terabox downloads**: Checkpoint per chunk, support resume

### Progress Tracking
- **Download**: Progress bar animasi, speed, ETA, file info per 0.8 detik
- **Upload/Mirror**: Progress bar real-time per 1 detik
  - GDrive: via `next_chunk()` progress
  - GoFile: via custom file wrapper iterator
  - Terabox: per-chunk tracking

### Auto Cleanup
- File download > 6 jam dihapus otomatis
- File `.part` > 2 jam dianggap abandoned
- Direktori kosong dibersihkan
- Queue task selesai dihapus dari memory
- Log rotation: 10MB per file, 5 backup

---

## 🔒 Keamanan

- ⚠️ **Jangan commit `.env`** — sudah di `.gitignore`
- 🔑 Gunakan `.env.example` sebagai template aman
- 🚫 Support **ban user** oleh owner
- 👥 Opsi **authorized users** — batasi akses hanya user tertentu
- 📝 **Credentials tidak hardcoded** — semua dari environment variables

---

## 📸 Screenshots

| Menu | Download | Mirror |
|------|----------|--------|
| 🏠 Menu utama dengan tombol interaktif | 📊 Progress bar real-time dengan speed & ETA | ☁️ Pilih platform mirror + progress upload |
| Queue management | AI Assistant | Status sistem |

*(Tambahkan screenshot dengan meng-upload gambar ke folder `screenshots/`)*

---

## 🤝 Kontribusi

Pull request, bug report, dan saran fitur sangat diterima!

1. Fork project ini
2. Buat branch fitur: `git checkout -b fitur-keren`
3. Commit perubahan: `git commit -m 'feat: tambah fitur keren'`
4. Push ke branch: `git push origin fitur-keren`
5. Buka Pull Request

---

## 📄 Lisensi

Distributed under the **MIT License**. See `LICENSE` for more information.

---

## 🙏 Credits

- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot)
- [yt-dlp](https://github.com/yt-dlp/yt-dlp)
- [Terabox API Research](analysis-terabox.md)

---

<p align="center">
  <b>Dibuat dengan ❤️ untuk memudahkan download & upload via Telegram</b><br>
  <a href="https://github.com/harisbit88/telegram-download-bot">⭐ Star di GitHub</a> •
  <a href="https://github.com/harisbit88/telegram-download-bot/issues">🐛 Laporkan Bug</a>
</p>

#!/bin/bash
# Deployment script untuk Telegram Download Bot
# Usage: bash deploy.sh [docker|systemd]

set -e

BOT_DIR="/home/haris_id/Repository/telegram-download-bot"

echo "🚀 Deploy Telegram Download Bot"
echo "================================"

case "${1:-docker}" in
  docker)
    echo "📦 Deploy dengan Docker..."
    cd "$BOT_DIR"

    # Buat direktori yang diperlukan
    mkdir -p data downloads logs

    # Build dan start container
    docker compose up -d --build

    echo "✅ Bot running! Cek dengan: docker compose logs -f"
    ;;

  systemd)
    echo "📦 Deploy dengan Systemd..."
    cd "$BOT_DIR"

    # Buat direktori log
    mkdir -p logs

    # Install service
    sudo cp telegram-download-bot.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable telegram-download-bot
    sudo systemctl start telegram-download-bot

    echo "✅ Bot running! Cek dengan:"
    echo "   sudo systemctl status telegram-download-bot"
    echo "   journalctl -u telegram-download-bot -f"
    ;;

  *)
    echo "Usage: bash deploy.sh [docker|systemd]"
    exit 1
    ;;
esac

FROM python:3.14-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Create download directory
RUN mkdir -p ./downloads

# Environment file (harus di-mount atau disediakan)
ENV BOT_TOKEN=""

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import sqlite3; sqlite3.connect('bot.db').execute('SELECT 1')" || exit 1

# Run bot
CMD ["python", "bot.py"]

#!/usr/bin/env python3
"""
Test script untuk Terabox Downloader
Cek koneksi API, ekstrak share code, dan informasi file.

Usage:
    python test_terabox.py <url_terabox>

    Atau tanpa argumen (memakai default test URL):
    python test_terabox.py
"""

import sys
import os
import asyncio
import json
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# CONFIG (ambil dari .env)
# ============================================================
COOKIE = os.getenv("TERABOX_COOKIE", "")
DOWNLOAD_PATH = os.getenv("DOWNLOAD_PATH", "./downloads")

# ============================================================
# HELPER: extract share code (copy dari downloaders/terabox.py)
# ============================================================
import re

def extract_share_code(url: str) -> str:
    """Extract share code dari URL"""
    patterns = [
        r'surl=([^&]+)',
        r'/s/([^/?]+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return url.split('/')[-1]


# ============================================================
# TEST 1: Cek konfigurasi
# ============================================================
def test_config():
    print("\n" + "="*60)
    print("📋 TEST 1: Cek Konfigurasi Terabox")
    print("="*60)
    print(f"  Cookie:      {'✅ Ada' if COOKIE else '❌ KOSONG'}")
    print(f"  Token:       {'✅ Ada' if TOKEN else '❌ KOSONG'}")
    print(f"  Download:    {DOWNLOAD_PATH}")

    # Pastikan folder download ada
    os.makedirs(DOWNLOAD_PATH, exist_ok=True)

    return bool(COOKIE)


# ============================================================
# TEST 2: Cek API get-info (primary)
# ============================================================
async def test_api_primary(share_code: str):
    print("\n" + "="*60)
    print("📡 TEST 2: Cek API Primary (terabox.hnn.workers.dev)")
    print("="*60)

    import aiohttp

    api_url = f"https://terabox.hnn.workers.dev/api/get-info?shorturl={share_code}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                print(f"  Status:  {resp.status}")
                if resp.status == 200:
                    data = await resp.json()
                    print(f"  OK:      {data.get('ok', False)}")
                    print(f"  Title:   {data.get('title', 'N/A')}")
                    file_list = data.get('list', [])
                    print(f"  Files:   {len(file_list)} file(s)")

                    for i, f in enumerate(file_list[:5], 1):
                        size = f.get('size', 0)
                        name = f.get('name', 'Unknown')
                        dlink = f.get('dlink', '')
                        print(f"\n  [{i}] {name}")
                        print(f"      Size: {size} bytes ({size/1024/1024:.1f} MB)" if size > 0 else "      Size: ?")
                        print(f"      Dlink: {'✅ Ada' if dlink else '❌ TIDAK ADA'}")

                    return data
                else:
                    body = await resp.text()
                    print(f"  Response: {body[:500]}")
                    return None
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return None


# ============================================================
# TEST 3: Cek API fallback
# ============================================================
async def test_api_fallback(url: str):
    print("\n" + "="*60)
    print("📡 TEST 3: Cek API Fallback (ytdl.freemediabot.xyz)")
    print("="*60)

    import aiohttp

    api_url = f"https://ytdl.freemediabot.xyz/terabox?url={url}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                print(f"  Status:  {resp.status}")
                if resp.status == 200:
                    data = await resp.json()
                    title = data.get('title', 'N/A')
                    size = data.get('size', 0)
                    dl_url = data.get('url', '')
                    print(f"  Title:   {title}")
                    print(f"  Size:    {size} bytes ({size/1024/1024:.1f} MB)" if size > 0 else "  Size: ?")
                    print(f"  DL URL:  {'✅ Ada' if dl_url else '❌ TIDAK ADA'}")
                    return data
                else:
                    body = await resp.text()
                    print(f"  Response: {body[:500]}")
                    return None
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return None


# ============================================================
# TEST 4: Coba download 1MB pertama (test koneksi download)
# ============================================================
async def test_download(url: str, filename: str):
    print("\n" + "="*60)
    print("⬇️  TEST 4: Test Download (1 MB pertama)")
    print("="*60)

    import aiohttp
    import aiofiles

    file_path = os.path.join(DOWNLOAD_PATH, filename)

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers,
                                    allow_redirects=True,
                                    timeout=aiohttp.ClientTimeout(total=60)) as resp:
                print(f"  Status:  {resp.status}")
                print(f"  Type:    {resp.headers.get('content-type', '?')}")

                total = int(resp.headers.get('content-length', 0))
                print(f"  Size:    {total} bytes ({total/1024/1024:.1f} MB)" if total > 0 else "  Size: ?")

                # Download max 1MB untuk test
                max_test = 1024 * 1024  # 1 MB
                downloaded = 0

                async with aiofiles.open(file_path, 'wb') as f:
                    async for chunk in resp.content.iter_chunked(65536):
                        await f.write(chunk)
                        downloaded += len(chunk)
                        if downloaded >= max_test:
                            print(f"  ✅ Downloaded {downloaded/1024/1024:.1f} MB (test OK)")
                            break

                # Hapus file test
                os.remove(file_path)
                print(f"  🧹 File test dihapus")

                if total > 0:
                    print(f"\n  ✅ Koneksi download berfungsi!")
                else:
                    print(f"\n  ⚠️ Download OK, tapi Content-Length tidak diketahui")

                return True

    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False


# ============================================================
# MAIN
# ============================================================
async def main():
    print("="*60)
    print("🔍 TERABOX DOWNLOADER TEST")
    print("="*60)

    url = sys.argv[1] if len(sys.argv) > 1 else None

    if not url:
        print("\n⚠️  Tidak ada URL diberikan sebagai argumen.")
        print("   Gunakan: python test_terabox.py <url_terabox>")
        print("\n   Contoh URL test (kalau ada):")
        print("   https://www.terabox.com/s/xxx")
        print("\n❌ TEST GAGAL - tidak ada URL")
        sys.exit(1)

    print(f"\n🔗 URL: {url}")
    share_code = extract_share_code(url)
    print(f"🔑 Share Code: {share_code}")

    # Test 1: Config
    config_ok = test_config()
    if not config_ok:
        print("\n⚠️  Cookie Terabox kosong - beberapa fitur mungkin tidak berfungsi")

    # Test 2: API Primary
    data = await test_api_primary(share_code)

    # Test 3: API Fallback (kalau primary gagal)
    fallback_data = None
    if not data or not data.get('ok'):
        fallback_data = await test_api_fallback(url)

    # Test 4: Download test (kalau ada dlink)
    dl_url = None
    if data and data.get('ok'):
        files = data.get('list', [])
        if files:
            dl_url = files[0].get('dlink', '') or files[0].get('download_url', '')
    elif fallback_data:
        dl_url = fallback_data.get('url', '')

    if dl_url:
        print(f"\n🔗 Download URL tersedia, mencoba test download...")
        filename = data.get('title', 'terabox_test') if data else 'terabox_test'
        await test_download(dl_url, filename)
    else:
        print("\n" + "="*60)
        print("⚠️  TEST 4: Dilewati (tidak ada download URL)")
        print("="*60)
        print("  API mungkin tidak mengembalikan link download langsung.")
        print("  Coba cek apakah cookie masih valid atau share link masih aktif.")

    # ===== SUMMARY =====
    print("\n" + "="*60)
    print("📊 HASIL TEST")
    print("="*60)

    if data and data.get('ok'):
        print("  ✅ API Primary:   BERHASIL")
    else:
        print("  ❌ API Primary:   GAGAL")

    if fallback_data:
        print("  ✅ API Fallback:  BERHASIL")
    else:
        print("  ❌ API Fallback:  GAGAL")

    if config_ok:
        print("  ✅ Config:        OK")
    else:
        print("  ⚠️ Config:        Cookie kosong")

    print("="*60)
    print()


if __name__ == "__main__":
    asyncio.run(main())

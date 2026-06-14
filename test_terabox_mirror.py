#!/usr/bin/env python3
"""
Test script untuk Terabox Mirror (Upload ke Terabox)
Mengikuti dokumentasi resmi: https://herobenhero.github.io/1024TeraBox-REST-API/

Official flow:
  POST /rest/2.0/xpan/file?method=precreate   (Fase 1)
  POST {node}/rest/2.0/pcs/superfile2          (Fase 2 — skip jika rapid)
  POST /rest/2.0/xpan/file?method=create       (Fase 3)

Legacy flow (fallback):
  POST www.terabox.com/api/precreate
  POST c3.terabox.com/rest/2.0/pcs/superfile2
  POST www.terabox.com/api/create

Usage:
    python test_terabox_mirror.py
"""

import os, sys, json, hashlib, re, asyncio, aiohttp
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# CONFIG — dari .env
# ============================================================
COOKIE    = os.getenv("TERABOX_COOKIE", "")
BDS_TOKEN = os.getenv("TERABOX_BDS_TOKEN", "")
JS_TOKEN  = os.getenv("TERABOX_JS_TOKEN", "")
DEVID     = os.getenv("TERABOX_DEVID", "")

# Official API domain (real: dm.terabox.com)
API_BASE   = "https://dm.terabox.com"
PCS_DOMAIN = "https://szb-cdata.1024terabox.com"  # upload node

# Legacy domain (fallback)
LEGACY_BASE = "https://www.terabox.com/api"

# Common fixed params
COMMON_PARAMS = {
    "app_id": "250528",
    "web": "1",
    "channel": "dubox",
    "clienttype": "0",
}

COMMON_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36 Edg/148.0.0.0"
    ),
    "Referer": "https://dm.terabox.com/ai/index/indonesian",
    "Origin": "https://dm.terabox.com",
    "x-requested-with": "XMLHttpRequest",
}

CHUNK_SIZE = 4 * 1024 * 1024  # 4 MB

PASS = 0
FAIL = 0

def ok(msg):
    global PASS
    PASS += 1
    print(f"   ✅ {msg}")

def ng(msg, detail=""):
    global FAIL
    FAIL += 1
    print(f"   ❌ {msg}" + (f" — {detail}" if detail else ""))

def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def get_devuid() -> str:
    """Ambil devuid dari config, fallback ke browserid dari cookie."""
    if DEVID:
        return DEVID
    m = re.search(r"browserid=([^;]+)", COOKIE)
    return m.group(1) if m else ""


def build_headers(content_type: str | None = None) -> dict:
    h = dict(COMMON_HEADERS)
    h["Cookie"] = COOKIE
    if content_type:
        h["Content-Type"] = content_type
    return h


# ============================================================
# TEST 1: Cek konfigurasi
# ============================================================
def test_config():
    section("TEST 1: Konfigurasi Terabox")

    if not COOKIE:
        ng("TERABOX_COOKIE kosong!")
        return False

    has_ndus      = "ndus=" in COOKIE
    has_browserid = "browserid=" in COOKIE
    has_csrftoken = "csrfToken=" in COOKIE

    ok("ndus ditemukan" if has_ndus else "ndus tidak ada")
    ok("browserid ditemukan" if has_browserid else "browserid tidak ada")
    ok("csrfToken ditemukan" if has_csrftoken else "csrfToken tidak ada")

    # Official tokens
    if BDS_TOKEN:
        ok(f"TERABOX_BDS_TOKEN terisi ({BDS_TOKEN[:16]}...)")
    else:
        ng("TERABOX_BDS_TOKEN kosong — official API upload tidak bisa")

    if JS_TOKEN:
        ok(f"TERABOX_JS_TOKEN terisi ({JS_TOKEN[:16]}...)")
    else:
        ng("TERABOX_JS_TOKEN kosong — official API upload tidak bisa")

    return has_ndus and has_browserid


# ============================================================
# TEST 2: Cek session validity via official API
# ============================================================
async def test_session():
    section("TEST 2: Cek Session / Auth validity (official API)")

    # Real request: POST /api/user/getinfo (bukan GET!)
    params = {
        **COMMON_PARAMS,
        "jsToken": JS_TOKEN,
        "devuid": get_devuid(),
        "need_relation": "0",
        "need_secret_info": "1",
        "user_list": "[4401883070935]",
        "bdstoken": BDS_TOKEN,
    }
    url = f"{API_BASE}/api/user/getinfo"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, params=params, headers=build_headers("application/x-www-form-urlencoded"),
                timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    errno = data.get("errno", -1)
                    if errno == 0:
                        uname = data.get("records", [{}])[0].get("uname", "?")
                        uk = data.get("records", [{}])[0].get("uk", "?")
                        ok(f"Session valid! User: {uname} (ID: {uk})")
                        return True
                    else:
                        errmsg = data.get("errmsg", "?")
                        ng(f"Session invalid: errno={errno} msg={errmsg}")
                        if errno == -6:
                            print("     ⚠️  Cookie expired atau tidak valid — "
                                  "login ulang di browser, ambil cookie baru")
                        return False
                else:
                    ng(f"HTTP {resp.status}")
                    return False
    except asyncio.TimeoutError:
        ng("Timeout — server 1024terabox.com lambat")
        return False
    except Exception as e:
        ng(f"Exception: {e}")
        return False


# ============================================================
# TEST 3: Official API — upload file dummy
# ============================================================
async def test_upload_official():
    section("TEST 3: Official API — Upload file dummy (3 fase)")

    FILE_TAG = f"{asyncio.get_running_loop().time():.0f}"
    test_file = f"/tmp/terabox_official_test_{FILE_TAG}.txt"
    test_content = f"Terabox Official API Test — {FILE_TAG}\nBaris kedua\nBaris ketiga."
    with open(test_file, "w") as f:
        f.write(test_content)

    file_size = os.path.getsize(test_file)
    filename = os.path.basename(test_file)
    remote_path = "/bot_uploads/"
    full_remote = f"{remote_path}{filename}"

    print(f"  File:    {test_file}")
    print(f"  Size:    {file_size} bytes")
    print(f"  Remote:  {full_remote}")

    # Hitung MD5 per chunk
    md5_list = []
    chunk_list = []
    with open(test_file, "rb") as f:
        while True:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break
            md5_list.append(hashlib.md5(chunk).hexdigest())
            chunk_list.append(chunk)

    print(f"  Chunks:  {len(md5_list)} ({CHUNK_SIZE/1024/1024:.0f} MB each)")
    for i, m in enumerate(md5_list):
        print(f"    chunk[{i}] md5={m}")

    try:
        async with aiohttp.ClientSession() as session:

            # ===== FASE 1: PRECREATE =====
            print("\n  --- Fase 1: Precreate ---")
            pre_params = {
                **COMMON_PARAMS,
                "method": "precreate",
                "bdstoken": BDS_TOKEN,
                "jsToken": JS_TOKEN,
                "devuid": get_devuid(),
            }
            pre_data = {
                "path": full_remote,
                "size": str(file_size),
                "autoinit": "1",
                "block_list": json.dumps(md5_list),
                "rtype": "1",
            }

            async with session.post(
                f"{API_BASE}/rest/2.0/xpan/file",
                params=pre_params,
                data=pre_data,
                headers=build_headers("application/x-www-form-urlencoded"),
            ) as resp:
                result = await resp.json()
                errno = result.get("errno", -1)
                print(f"     Response: {json.dumps(result, indent=6)[:500]}")

                if errno != 0:
                    ng(f"Precreate gagal: errno={errno} msg={result.get('errmsg', '?')}")
                    if errno == -6:
                        print("     ⚠️  Cookie expired atau bdstoken salah")
                    elif errno == -8:
                        print("     ⚠️  File sudah ada, path duplikat")
                    return False

                upload_id = result.get("uploadid")
                needed = result.get("block_list")  # None / [] / [indices]
                ok(f"Precreate berhasil! uploadid={upload_id}")
                if needed is not None and len(needed) > 0:
                    print(f"     Chunks perlu diupload: {len(needed)} (indices: {needed})")
                else:
                    print(f"     🔥 Rapid upload! Semua blok sudah ada di server — skip Fase 2")

            # ===== FASE 2: UPLOAD CHUNKS (skip jika rapid upload) =====
            if needed is not None and len(needed) > 0:
                print("\n  --- Fase 2: Upload chunks ---")
                for idx_str in needed:
                    idx = int(idx_str)
                    chunk_data = chunk_list[idx]
                    chunk_md5 = md5_list[idx]

                    up_params = {
                        "method": "upload",
                        "app_id": COMMON_PARAMS["app_id"],
                        "uploadid": upload_id,
                        "path": full_remote,
                        "partseq": str(idx),
                        "uploadsign": "0",
                    }
                    form = aiohttp.FormData()
                    form.add_field("file", chunk_data, filename=f"part{idx}")

                    async with session.post(
                        f"{PCS_DOMAIN}/rest/2.0/pcs/superfile2",
                        params=up_params,
                        data=form,
                        headers=build_headers(),
                    ) as up_resp:
                        up_result_text = await up_resp.text()
                        try:
                            up_result = json.loads(up_result_text)
                        except json.JSONDecodeError:
                            print(f"     ❌ PCS return HTTP {up_resp.status} (non-JSON): {up_result_text[:200]}")
                            print(f"\n⚠️  PCS UPLOAD NODE MEMINTA POMS KEY")
                            print("   Ini adalah security token server-side yang tidak bisa")
                            print("   di-reverse-engineer tanpa akses ke JavaScript web client.")
                            print("   Upload resmi ke Terabox TIDAK BISA dilakukan.")
                            print("   Gunakan layanan mirror lain (Telegram/GDrive/GoFile).")
                            raise Exception("POMS key required — Terabox upload not available")

                        returned_md5 = up_result.get("md5", "")
                        status = "✅" if returned_md5 == chunk_md5 else "❌"
                        print(f"     Chunk {idx}: sent={chunk_md5[:12]} ret={returned_md5[:12]} {status}")

            # ===== FASE 3: CREATE =====
            print("\n  --- Fase 3: Create (finalize) ---")
            create_params = {
                **COMMON_PARAMS,
                "method": "create",
                "bdstoken": BDS_TOKEN,
                "jsToken": JS_TOKEN,
                "devuid": get_devuid(),
            }
            create_data = {
                "path": full_remote,
                "size": str(file_size),
                "uploadid": upload_id,
                "block_list": json.dumps(md5_list),  # SEMUA chunk, urut
                "isdir": "0",
                "rtype": "1",
            }

            async with session.post(
                f"{API_BASE}/rest/2.0/xpan/file",
                params=create_params,
                data=create_data,
                headers=build_headers("application/x-www-form-urlencoded"),
            ) as create_resp:
                create_result = await create_resp.json()
                print(f"     Response: {json.dumps(create_result, indent=6)[:500]}")
                errno = create_result.get("errno", -1)

                if errno == 0:
                    ok(f"Upload BERHASIL! Path: {full_remote}")
                    fs_id = create_result.get("fs_id", "")
                    print(f"     fs_id: {fs_id}")
                else:
                    ng(f"Create gagal: errno={errno} msg={create_result.get('errmsg', '?')}")
                    return False

    except Exception as e:
        ng(f"Exception: {e}")
        return False
    finally:
        if os.path.exists(test_file):
            os.remove(test_file)

    return True


# ============================================================
# TEST 4: Legacy API — upload file dummy
# ============================================================
async def test_upload_legacy():
    section("TEST 4: Legacy API — Upload file dummy (fallback)")

    FILE_TAG = f"{asyncio.get_running_loop().time():.0f}"
    test_file = f"/tmp/terabox_legacy_test_{FILE_TAG}.txt"
    test_content = f"Terabox Legacy API Test — {FILE_TAG}"
    with open(test_file, "w") as f:
        f.write(test_content)

    file_size = os.path.getsize(test_file)
    filename = os.path.basename(test_file)
    full_remote = f"/bot_uploads/{filename}"

    legacy_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Cookie": COOKIE or "",
    }

    print(f"  File:    {test_file}")
    print(f"  Size:    {file_size} bytes")
    print(f"  Remote:  {full_remote}")

    try:
        async with aiohttp.ClientSession() as session:

            # Fase 1: Legacy precreate
            print("\n  --- Fase 1: Precreate (legacy) ---")
            pre_data = {
                "path": full_remote,
                "size": file_size,
                "isdir": "0",
                "block_list": "[]",
            }
            async with session.post(
                f"{LEGACY_BASE}/precreate", data=pre_data, headers=legacy_headers
            ) as resp:
                result = await resp.json()
                errno = result.get("errno", -1)
                if errno != 0:
                    ng(f"Precreate legacy: errno={errno} msg={result.get('errmsg', '?')}")
                    return False
                upload_id = result.get("uploadid")
                ok(f"Precreate legacy berhasil! uploadid={upload_id}")

            # Fase 2: Upload chunk
            print("\n  --- Fase 2: Upload chunk ---")
            chunk = test_content.encode()
            chunk_md5 = hashlib.md5(chunk).hexdigest()

            up_params = {
                "method": "upload",
                "path": full_remote,
                "uploadid": upload_id,
                "partseq": 0,
            }
            form = aiohttp.FormData()
            form.add_field("file", chunk, filename="part0")

            async with session.post(
                "https://szb-cdata.1024terabox.com/rest/2.0/pcs/superfile2",
                params=up_params, data=form, headers=legacy_headers,
            ) as up_resp:
                up_result = await up_resp.json()
                print(f"     Response: {json.dumps(up_result)[:200]}")
                md5 = up_result.get("md5", chunk_md5)
                ok(f"Chunk uploaded, md5={md5}")

            # Fase 3: Create (legacy)
            print("\n  --- Fase 3: Create (legacy) ---")
            create_data = {
                "path": full_remote,
                "size": file_size,
                "isdir": "0",
                "uploadid": upload_id,
                "block_list": f'["{md5}"]',
            }
            async with session.post(
                f"{LEGACY_BASE}/create", data=create_data, headers=legacy_headers,
            ) as create_resp:
                create_result = await create_resp.json()
                print(f"     Response: {json.dumps(create_result)[:300]}")
                errno = create_result.get("errno", -1)
                if errno == 0:
                    ok(f"Legacy upload BERHASIL! Path: {full_remote}")
                else:
                    ng(f"Create legacy: errno={errno} msg={create_result.get('errmsg', '?')}")
                    return False

    except Exception as e:
        ng(f"Exception: {e}")
        return False
    finally:
        if os.path.exists(test_file):
            os.remove(test_file)

    return True


# ============================================================
# TEST 5: Verifikasi file di Terabox via official API
# ============================================================
async def test_verify():
    section("TEST 5: Verifikasi file di /bot_uploads/")

    params = {
        **COMMON_PARAMS,
        "dir": "/bot_uploads/",
        "num": "10",
        "order": "time",
        "desc": "1",
        "jsToken": JS_TOKEN,
    }
    url = f"{API_BASE}/api/list"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, params=params, headers=build_headers(),
                timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    files = data.get("list", [])
                    if files:
                        ok(f"Ditemukan {len(files)} file di /bot_uploads/:")
                        for f in files[:5]:
                            name = f.get("server_filename", "?")
                            size = f.get("size", 0)
                            ctime = f.get("server_ctime", "?")
                            print(f"     📄 {name} ({size/1024:.1f} KB)")
                        return True
                    else:
                        ng("Tidak ada file di /bot_uploads/")
                        return False
                else:
                    ng(f"HTTP {resp.status}")
                    return False
    except Exception as e:
        ng(f"Exception: {e}")
        return False


# ============================================================
# MAIN
# ============================================================
async def main():
    print("=" * 60)
    print("🔍 TERABOX MIRROR (UPLOAD) TEST")
    print("   Berdasarkan dokumentasi: 1024TeraBox-REST-API")
    print("=" * 60)

    # Test 1: Config
    config_ok = test_config()
    if not config_ok:
        print("\n⚠️  Konfigurasi tidak lengkap.")
        print("   Pastikan TERABOX_COOKIE di .env sudah diisi dengan benar.")
        print("   Cookie minimal harus mengandung ndus= dan browserid=.\n")
        sys.exit(1)

    # Test 2: Session (official)
    await test_session()

    # Test 3: Official upload (3 fase — rapid check included)
    upload_official_ok = await test_upload_official()

    # Test 4: Legacy upload (fallback)
    upload_legacy_ok = await test_upload_legacy()

    # Test 5: Verify
    if upload_official_ok or upload_legacy_ok:
        await test_verify()
    else:
        print("\n⏩  TEST 5: Dilewati (semua upload gagal)")

    # ===== RESULT =====
    print(f"\n{'=' * 60}")
    print(f"  📊 HASIL: ✅ {PASS} lulus  |  ❌ {FAIL} gagal")
    print(f"{'=' * 60}")

    if FAIL == 0:
        print("\n  🎉 Semua test BERHASIL!")
    elif upload_official_ok and upload_legacy_ok:
        print("\n  ✅ Official + Legacy API keduanya berfungsi!")
    elif upload_official_ok:
        print("\n  ✅ Official API berfungsi, Legacy API perlu dicek")
    elif upload_legacy_ok:
        print("\n  ✅ Legacy API berfungsi, Official API perlu dicek")
    else:
        print(f"\n  ⚠️  Ada {FAIL} test gagal. Cek detail di atas.")

    print()


if __name__ == "__main__":
    asyncio.run(main())

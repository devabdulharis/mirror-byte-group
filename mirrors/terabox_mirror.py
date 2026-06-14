import os
import json
import hashlib
import re
import aiohttp
from config import Config
from utils.mirror_progress import MirrorProgressTracker


# ---------------------------------------------------------------------------
# Constants — dari test_terabox_mirror.py (terverifikasi berhasil)
# ---------------------------------------------------------------------------
TERABOX_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36 Edg/148.0.0.0"
)
CHUNK_SIZE = 4 * 1024 * 1024  # 4 MB
LOG_PREFIX = "[TeraboxMirror]"

API_BASE    = "https://dm.terabox.com"
PCS_DOMAIN  = "https://szb-cdata.1024terabox.com"

COMMON_PARAMS = {
    "app_id": "250528",
    "web": "1",
    "channel": "dubox",
    "clienttype": "0",
}

COMMON_HEADERS = {
    "User-Agent": TERABOX_UA,
    "Referer": "https://dm.terabox.com/ai/index/indonesian",
    "Origin": "https://dm.terabox.com",
    "x-requested-with": "XMLHttpRequest",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _pick_js_token() -> str:
    return Config.TERABOX_JS_TOKEN or ""

def _pick_bdstoken() -> str:
    return Config.TERABOX_BDS_TOKEN or ""

def _get_devuid() -> str:
    """Ambil devuid dari config, fallback ke browserid dari cookie."""
    if Config.TERABOX_DEVID:
        return Config.TERABOX_DEVID
    cookie = Config.TERABOX_COOKIE or ""
    m = re.search(r"browserid=([^;]+)", cookie)
    return m.group(1) if m else ""

def _build_headers(content_type: str | None = None) -> dict:
    h = dict(COMMON_HEADERS)
    h["Cookie"] = Config.TERABOX_COOKIE or ""
    if content_type:
        h["Content-Type"] = content_type
    return h

def _has_tokens() -> bool:
    return bool(Config.TERABOX_COOKIE and Config.TERABOX_JS_TOKEN)

def _compute_chunk_md5s(file_path: str) -> tuple[list[str], list[bytes], int]:
    """Baca file dalam chunk 4MB. Returns (list_of_md5_hex, list_of_chunk_bytes, total_size)."""
    md5s: list[str] = []
    chunks: list[bytes] = []
    total = 0
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break
            md5s.append(hashlib.md5(chunk).hexdigest())
            chunks.append(chunk)
            total += len(chunk)
    return md5s, chunks, total


# ===========================================================================
# Official upload — endpoint persis seperti test_terabox_mirror.py
# ===========================================================================
async def _upload_official(file_path: str, remote_path: str,
                           progress_tracker: MirrorProgressTracker = None) -> dict:
    """
    Upload file via official Terabox REST API (3 fase).
    Endpoints dan parameter persis seperti test_terabox_mirror.py yang berhasil.
    """
    js_token  = _pick_js_token()
    bdstoken  = _pick_bdstoken()
    devuid    = _get_devuid()
    cookie    = Config.TERABOX_COOKIE or ""

    if not js_token:
        raise Exception("TERABOX_JS_TOKEN kosong")
    if not bdstoken:
        raise Exception("TERABOX_BDS_TOKEN kosong")
    if not devuid:
        raise Exception("devuid tidak ditemukan — butuh TERABOX_DEVID atau browserid di cookie")

    md5_list, chunk_list, file_size = _compute_chunk_md5s(file_path)
    filename = os.path.basename(file_path)
    full_remote = f"{remote_path}{filename}"

    import logging
    log = logging.getLogger(__name__)
    log.info(f"{LOG_PREFIX} Upload {filename} ({file_size} bytes) ke {full_remote}")

    try:
        async with aiohttp.ClientSession() as session:

            # ===== FASE 1: PRECREATE ====================================
            params_qs = {
                **COMMON_PARAMS,
                "method": "precreate",
                "bdstoken": bdstoken,
                "jsToken": js_token,
                "devuid": devuid,
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
                params=params_qs,
                data=pre_data,
                headers=_build_headers("application/x-www-form-urlencoded"),
            ) as resp:
                result = await resp.json()
                if result.get("errno", -1) != 0:
                    raise Exception(
                        f"Precreate gagal: errno={result.get('errno')} "
                        f"msg={result.get('errmsg', '?')}"
                    )

            upload_id = result.get("uploadid")
            needed = result.get("block_list")  # None = rapid upload (skip Fase 2)
            log.info(f"{LOG_PREFIX} Precreate OK, uploadid={upload_id}, "
                     f"rapid={needed is None or len(needed) == 0}")

            # ===== FASE 2: UPLOAD CHUNKS (skip jika rapid upload) =======
            uploaded_total = 0
            if needed is not None and len(needed) > 0:
                for idx_str in needed:
                    idx = int(idx_str)
                    chunk_data = chunk_list[idx]

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
                        headers=_build_headers(),
                    ) as up_resp:
                        up_text = await up_resp.text()
                        if up_resp.status != 200:
                            raise Exception(
                                f"Upload chunk {idx}: HTTP {up_resp.status} {up_text[:200]}"
                            )
                        try:
                            up_result = json.loads(up_text)
                        except json.JSONDecodeError:
                            raise Exception(
                                f"Upload chunk {idx}: server return non-JSON — {up_text[:200]}"
                            )

                        returned_md5 = up_result.get("md5", "")
                        if returned_md5 and returned_md5 != md5_list[idx]:
                            raise Exception(
                                f"MD5 mismatch chunk {idx}: "
                                f"expected {md5_list[idx]}, got {returned_md5}"
                            )

                    uploaded_total += len(chunk_data)
                    if progress_tracker:
                        await progress_tracker.update(uploaded_total, file_size, filename)

            # ===== FASE 3: CREATE =======================================
            create_qs = {
                **COMMON_PARAMS,
                "method": "create",
                "bdstoken": bdstoken,
                "jsToken": js_token,
                "devuid": devuid,
            }
            create_data = {
                "path": full_remote,
                "size": str(file_size),
                "uploadid": upload_id,
                "block_list": json.dumps(md5_list),
                "isdir": "0",
                "rtype": "1",
            }

            async with session.post(
                f"{API_BASE}/rest/2.0/xpan/file",
                params=create_qs,
                data=create_data,
                headers=_build_headers("application/x-www-form-urlencoded"),
            ) as create_resp:
                create_result = await create_resp.json()
                if create_result.get("errno", -1) != 0:
                    raise Exception(
                        f"Create gagal: errno={create_result.get('errno')} "
                        f"msg={create_result.get('errmsg', '?')}"
                    )

                fs_id = create_result.get("fs_id", "")
                log.info(f"{LOG_PREFIX} Upload BERHASIL! fs_id={fs_id}, path={full_remote}")

                return {
                    "success": True,
                    "platform": "terabox",
                    "path": full_remote,
                    "fs_id": str(fs_id),
                    "uploadid": upload_id,
                    "md5": create_result.get("md5", ""),
                    "method": "official",
                }

    except Exception as e:
        log.error(f"{LOG_PREFIX} Upload gagal: {e}")
        raise


# ===========================================================================
# Public class
# ===========================================================================
class TeraboxMirror:
    """Upload ke Terabox sebagai mirror."""

    def __init__(self):
        self.cookie = Config.TERABOX_COOKIE

    def is_available(self) -> bool:
        return bool(self.cookie)

    def is_official_available(self) -> bool:
        return _has_tokens()

    async def upload(self, file_path: str, remote_path: str = "/bot_uploads/",
                      progress_tracker: MirrorProgressTracker = None) -> dict:
        if not self.is_available():
            return {
                "success": False,
                "error": "Terabox cookie tidak dikonfigurasi",
                "platform": "terabox",
            }
        if not os.path.exists(file_path):
            return {
                "success": False,
                "error": f"File tidak ditemukan: {file_path}",
                "platform": "terabox",
            }

        if not _has_tokens():
            return {
                "success": False,
                "error": (
                    "Upload Terabox membutuhkan:\n"
                    "• TERABOX_COOKIE\n"
                    "• TERABOX_JS_TOKEN\n"
                    "• TERABOX_BDS_TOKEN\n"
                    "• TERABOX_DEVID (atau browserid di cookie)\n\n"
                    "Isi semua di file .env."
                ),
                "platform": "terabox",
            }

        try:
            return await _upload_official(file_path, remote_path, progress_tracker)
        except Exception as e:
            err_msg = str(e)
            if "errno=-6" in err_msg:
                return {
                    "success": False,
                    "error": (
                        "❌ Upload Terabox gagal: tidak terautentikasi.\n\n"
                        "Cookie atau token sudah expired.\n"
                        "Cara perbarui:\n"
                        "1. Login ke https://1024terabox.com\n"
                        "2. F12 → Network → reload\n"
                        "3. Cari request ke /rest/2.0/xpan/file\n"
                        "4. Ambil Cookie, jsToken, bdstoken, devuid baru\n"
                        "5. Update di .env"
                    ),
                    "platform": "terabox",
                }

            return {
                "success": False,
                "error": f"Upload Terabox gagal:\n{err_msg}",
                "platform": "terabox",
            }

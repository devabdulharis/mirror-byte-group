import os
import json
import hashlib
import re
import aiohttp
from config import Config
from utils.mirror_progress import MirrorProgressTracker


# ---------------------------------------------------------------------------
# Constants — berdasarkan source code npm library terabox-api v2.9.2
# ---------------------------------------------------------------------------
TERABOX_UA = "terabox;1.40.0.132;PC;PC-Windows;10.0.26100;WindowsTeraBox"
CHUNK_SIZE = 4 * 1024 * 1024  # 4 MB

COMMON_QS = {
    "app_id": "250528",
    "web": "1",
    "channel": "dubox",
    "clienttype": "0",
}


def _pick_base() -> str:
    """Gunakan dm.terabox.com sebagai base domain — cookie kita valid di sini."""
    return "https://dm.terabox.com"


def _pick_js_token() -> str:
    return Config.TERABOX_JS_TOKEN or ""


def _build_headers(cookie: str = "") -> dict:
    c = cookie or Config.TERABOX_COOKIE or ""
    return {
        "User-Agent": TERABOX_UA,
        "Cookie": c,
    }


def _has_tokens() -> bool:
    return bool(Config.TERABOX_COOKIE and Config.TERABOX_JS_TOKEN)


def _compute_chunk_md5s(file_path: str) -> tuple[list[str], list[bytes], int]:
    """
    Baca file dalam chunk 4MB.
    Returns (list_of_md5_hex, list_of_chunk_bytes, total_size).
    """
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


async def _locate_upload_host(session: aiohttp.ClientSession, base: str, cookie: str) -> str:
    """Dapatkan upload host PCS via locateupload."""
    url = f"{base}/rest/2.0/pcs/file?method=locateupload&app_id=250528"
    async with session.get(url, headers=_build_headers(cookie)) as resp:
        r = await resp.json()
        return f"https://{r['host']}"


async def _upload_official(file_path: str, remote_path: str, progress_tracker: MirrorProgressTracker = None) -> dict:
    """
    Upload file via API internal Terabox:
      1. locateupload → dapatkan upload host
      2. precreate → reserve upload id
      3. upload chunks (jika diperlukan)
      4. create → finalisasi
    """
    base = _pick_base()
    cookie = Config.TERABOX_COOKIE or ""
    js_token = _pick_js_token()

    md5_list, chunk_list, file_size = _compute_chunk_md5s(file_path)
    filename = os.path.basename(file_path)
    full_remote = f"{remote_path}{filename}"

    async with aiohttp.ClientSession() as session:
        # --- Dapatkan upload host ---
        uhost = await _locate_upload_host(session, base, cookie)

        # --- FASE 1: PRECREATE ---
        params_qs = {**COMMON_QS, "jsToken": js_token}
        pre_data = {
            "path": full_remote,
            "autoinit": "1",
            "size": str(file_size),
            "block_list": json.dumps(md5_list),
            "rtype": "2",
            "content-md5": md5_list[0] if md5_list else "",
            "slice-md5": md5_list[0] if md5_list else "",
            "content-crc32": "0",
        }
        headers = _build_headers(cookie)
        headers["Content-Type"] = "application/x-www-form-urlencoded"

        async with session.post(
            f"{base}/api/precreate", params=params_qs, data=pre_data, headers=headers
        ) as resp:
            result = await resp.json()
            if result.get("errno", -1) != 0:
                raise Exception(
                    f"Precreate gagal: errno={result.get('errno')} "
                    f"msg={result.get('errmsg', '?')}"
                )

        upload_id = result["uploadid"]
        needed_blocks = result.get("block_list")  # None / [] / [indices]

        uploaded_total = 0
        # --- FASE 2: UPLOAD CHUNKS ---
        if needed_blocks is not None and len(needed_blocks) > 0:
            for i, idx_str in enumerate(needed_blocks):
                idx = int(idx_str)
                chunk_data = chunk_list[idx]

                up_params = {
                    "method": "upload",
                    "app_id": COMMON_QS["app_id"],
                    "path": full_remote,
                    "uploadid": upload_id,
                    "partseq": str(idx),
                }
                form = aiohttp.FormData()
                form.add_field("file", chunk_data, filename="blob")

                pcs_headers = _build_headers(cookie)

                async with session.post(
                    f"{uhost}/rest/2.0/pcs/superfile2",
                    params=up_params,
                    data=form,
                    headers=pcs_headers,
                ) as up_resp:
                    body = await up_resp.text()
                    if up_resp.status != 200:
                        raise Exception(
                            f"Upload chunk {idx} gagal: HTTP {up_resp.status} {body[:200]}"
                        )
                    up_result = json.loads(body)
                    returned_md5 = up_result.get("md5", "")
                    if returned_md5 and returned_md5 != md5_list[idx]:
                        raise Exception(
                            f"MD5 mismatch chunk {idx}: "
                            f"expected {md5_list[idx]}, got {returned_md5}"
                        )

                # Update progress setelah setiap chunk
                uploaded_total += len(chunk_data)
                if progress_tracker:
                    await progress_tracker.update(
                        uploaded_total, file_size, filename
                    )

        # --- FASE 3: CREATE ---
        create_data = {
            "path": full_remote,
            "size": str(file_size),
            "isdir": "0",
            "uploadid": upload_id,
            "block_list": json.dumps(md5_list),
            "rtype": "2",
            "content-md5": md5_list[0] if md5_list else "",
            "slice-md5": md5_list[0] if md5_list else "",
            "content-crc32": "0",
        }
        async with session.post(
            f"{base}/api/create", params=params_qs, data=create_data, headers=headers
        ) as create_resp:
            create_result = await create_resp.json()
            if create_result.get("errno", -1) != 0:
                raise Exception(
                    f"Create gagal: errno={create_result.get('errno')} "
                    f"msg={create_result.get('errmsg', '?')}"
                )

            return {
                "success": True,
                "platform": "terabox",
                "path": full_remote,
                "fs_id": str(create_result.get("fs_id", "")),
                "uploadid": upload_id,
                "md5": create_result.get("md5", ""),
                "method": "official",
            }


# ===========================================================================
# Legacy fallback — via www.terabox.com/api (endpoint lawas)
# ===========================================================================
_LEGACY_BASE = "https://www.terabox.com/api"


async def _upload_legacy(file_path: str, remote_path: str) -> dict:
    """Fallback via endpoint lawas — kemungkinan perlu cookie domain berbeda."""
    filename = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)
    full_remote = f"{remote_path}{filename}"
    md5_list, chunk_list, _ = _compute_chunk_md5s(file_path)
    cookie = Config.TERABOX_COOKIE or ""

    legacy_headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/148.0.0.0",
        "Cookie": cookie,
    }

    async with aiohttp.ClientSession() as session:
        pre_data = {
            "path": full_remote,
            "size": file_size,
            "isdir": "0",
            "block_list": "[]",
        }
        async with session.post(
            f"{_LEGACY_BASE}/precreate", data=pre_data, headers=legacy_headers
        ) as resp:
            result = await resp.json()
            if result.get("errno", -1) != 0:
                raise Exception(
                    f"Precreate (legacy) gagal: errno={result.get('errno')} "
                    f"msg={result.get('errmsg', '?')}"
                )
            upload_id = result.get("uploadid")

        block_list = []
        with open(file_path, "rb") as f:
            part_num = 0
            while True:
                chunk = f.read(CHUNK_SIZE)
                if not chunk:
                    break
                chunk_md5 = hashlib.md5(chunk).hexdigest()

                params = {
                    "method": "upload",
                    "path": full_remote,
                    "uploadid": upload_id,
                    "partseq": part_num,
                }
                form = aiohttp.FormData()
                form.add_field("file", chunk, filename=f"part{part_num}")

                async with session.post(
                    "https://c3.terabox.com/rest/2.0/pcs/superfile2",
                    params=params, data=form, headers=legacy_headers,
                ) as upload_resp:
                    upload_result = await upload_resp.json()
                    block_list.append(upload_result.get("md5", chunk_md5))

                part_num += 1

        create_data = {
            "path": full_remote,
            "size": file_size,
            "isdir": "0",
            "uploadid": upload_id,
            "block_list": str(block_list),
        }
        async with session.post(
            f"{_LEGACY_BASE}/create", data=create_data, headers=legacy_headers,
        ) as create_resp:
            create_result = await create_resp.json()
            if create_result.get("errno", 0) == 0:
                return {
                    "success": True,
                    "platform": "terabox",
                    "path": full_remote,
                    "fs_id": str(create_result.get("fs_id", "")),
                    "method": "legacy",
                }

        return {"success": False, "error": "Upload gagal", "platform": "terabox"}


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

        # Official API via dm.terabox.com (butuh jsToken)
        if _has_tokens():
            try:
                return await _upload_official(file_path, remote_path, progress_tracker)
            except Exception as e:
                err_msg = str(e)
                if "errno=-6" in err_msg:
                    return {
                        "success": False,
                        "error": (
                            f"Official API gagal (auth): {err_msg}. "
                            "Cek TERABOX_COOKIE / TERABOX_JS_TOKEN di .env"
                        ),
                        "platform": "terabox",
                    }

        # Fallback legacy
        try:
            return await _upload_legacy(file_path, remote_path)
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "platform": "terabox",
            }

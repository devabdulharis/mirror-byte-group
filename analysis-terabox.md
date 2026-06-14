# Analisis API Terabox — Dokumentasi vs Implementasi Saat Ini

> **Sumber**: https://herobenhero.github.io/1024TeraBox-REST-API/index.html  
> **Tanggal**: 2026-06-14

---

## Daftar Isi

1. [Ringkasan API](#1-ringkasan-api)
2. [Autentikasi](#2-autentikasi)
3. [Base URL & Domain](#3-base-url--domain)
4. [Parameter Umum](#4-parameter-umum)
5. [Endpoint Lengkap](#5-endpoint-lengkap)
6. [Upload Flow (Detail)](#6-upload-flow-detail)
7. [Download Flow (Detail)](#7-download-flow-detail)
8. [Perbandingan: Dokumentasi vs Implementasi Saat Ini](#8-perbandingan-dokumentasi-vs-implementasi-saat-ini)
9. [Bugs di Implementasi Saat Ini](#9-bugs-di-implementasi-saat-ini)
10. [Rekomendasi Perbaikan](#10-rekomendasi-perbaikan)

---

## 1. Ringkasan API

Terabox (d/h Dubox, mirip Baidu Pan) menyediakan REST API untuk operasi file secara terprogram. Autentikasi berbasis cookie + token — **tidak ada API key tradisional**.

### Domain Utama

| Domain | Kegunaan |
|--------|----------|
| `https://1024terabox.com` | API utama (list, upload, download, share, dll) |
| `https://www.terabox.com` | Alternatif, kadang diperlukan untuk cookie |
| `https://dm.1024terabox.com` | Domain untuk PCS upload node |
| `https://{node}.1024terabox.com` | Upload node spesifik (misal `szb-cdata`, `dm-c-all`) |

---

## 2. Autentikasi

Tidak ada API key. Tiga komponen token wajib:

| Token | Cara Kirim | Fungsi | Masa Berlaku |
|-------|-----------|--------|-------------|
| **ndus** | Header `Cookie` | Primary session identifier | Beberapa hari / logout |
| **jsToken** | Query parameter | Read + Write operations | Stabil selama sesi |
| **bdstoken** | Query parameter | **Write** operations (upload, delete, rename, dll) | Stabil selama sesi |

### Cara Ekstraksi Token (dari Browser)

1. Buka `https://1024terabox.com`, login
2. F12 → Network → filter `getinfo`
3. Dari request `/api/user/getinfo`:
   - **`ndus`** → Request Headers → Cookie
   - **`jsToken`** → Query String Parameters
   - **`bdstoken`** → Query String Parameters (terlihat di request write)

### Headers Wajib

```http
User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36
Referer: https://1024terabox.com/main?category=all
Origin: https://1024terabox.com
Cookie: ndus=...; PANWEB=1
```

### Endpoint Test Auth

```
GET /api/user/getinfo?app_id=250528&web=1&channel=dubox&clienttype=0&jsToken=TOKEN
```
Sukses → `errno: 0`, data user di `records[0].uname`

---

## 3. Base URL & Domain

Dokumentasi menyebutkan **tiga domain** berbeda tergantung operasi:

| Operasi | Domain | Contoh Path |
|---------|--------|-------------|
| **Query/Read API** | `https://1024terabox.com` | `/api/list`, `/api/search`, `/api/user/getinfo` |
| **Write API** (file mgr) | `https://1024terabox.com` | `/rest/2.0/xpan/file?method=...` |
| **Upload chunks** (PCS) | `https://{node}.1024terabox.com` | `/rest/2.0/pcs/superfile2?method=upload` |
| **Download** | `https://1024terabox.com` | `/rest/2.0/pcs/file?method=download` |
| **Share** | `https://1024terabox.com` | `/share/pset`, `/share/list`, `/share/transfer` |
| **Trash** | `https://1024terabox.com` | `/api/recycle/list`, `/api/recycle/restore` |

> ⚠️ **Catatan**: Saat ini implementasi menggunakan `www.terabox.com` bukan `1024terabox.com`. Perlu dikonfirmasi apakah cookie lintas domain berfungsi.

---

## 4. Parameter Umum

Parameter yang **wajib** ada di **setiap request**:

| Parameter | Nilai | Keterangan |
|-----------|-------|-----------|
| `app_id` | `250528` | Fixed untuk web client |
| `web` | `1` | Platform identifier |
| `channel` | `dubox` | Channel identifier |
| `clienttype` | `0` | Client type |

---

## 5. Endpoint Lengkap

### 5.1 Akun

| Method | Endpoint | Kegunaan | Auth |
|--------|----------|----------|------|
| `GET` | `/api/user/getinfo` | Info profil user | `ndus`, `jsToken` |
| `GET` | `/api/quota` | Kapasitas penyimpanan | `ndus`, `jsToken` |

### 5.2 File Listing

| Method | Endpoint | Kegunaan | Auth |
|--------|----------|----------|------|
| `GET` | `/api/list` | List direktori (paginasi) | `ndus`, `jsToken` |

**Parameter list**:
- `dir` — path direktori (default `/`)
- `num` — items per page (default 100)
- `page` — halaman
- `order` — `time` / `name` / `size`
- `desc` — `1` (desc) / `0` (asc)

### 5.3 File Operations

Semua via endpoint: **`POST /rest/2.0/xpan/file`**

| method | opera | Kegunaan | Auth Tambahan |
|--------|-------|----------|---------------|
| `filemanager` | `rename` | Rename file/folder | `bdstoken` |
| `filemanager` | `move` | Pindah file | `bdstoken` |
| `filemanager` | `copy` | Copy file | `bdstoken` |
| `filemanager` | `delete` | Hapus ke trash | `bdstoken` |
| `create` | — | Buat folder (isdir=1) | `bdstoken` |

### 5.4 Upload

3 fase — lihat [section 6](#6-upload-flow-detail).

### 5.5 Download

2 langkah — lihat [section 7](#7-download-flow-detail).

### 5.6 Sharing

| Method | Endpoint | Kegunaan | Auth |
|--------|----------|----------|------|
| `POST` | `/share/pset` | Buat share link | `jsToken` |
| `GET` | `/share/teratransfer/sharelist` | Daftar share aktif | `ndus`, `jsToken` |
| `POST` | `/share/cancel` | Batalkan share | `bdstoken` |

### 5.7 Save / Transfer (dari share link orang lain)

| Langkah | Method | Endpoint | Kegunaan |
|---------|--------|----------|----------|
| 1 | `GET` | `/share/list` | Resolve link → dapat `shareid`, `uk` |
| 2 | `POST` | `/share/transfer` | Transfer file ke drive sendiri |

### 5.8 Search

| Method | Endpoint | Kegunaan | Auth |
|--------|----------|----------|------|
| `GET` | `/api/search` | Cari file rekursif | `ndus`, `jsToken` |

### 5.9 Trash

| Method | Endpoint | Kegunaan | Auth |
|--------|----------|----------|------|
| `GET` | `/api/recycle/list` | List trash | `ndus`, `jsToken` |
| `POST` | `/api/recycle/restore` | Restore file | `ndus`, `jsToken`, `bdstoken` |
| `POST` | `/api/recycle/clear` | Kosongkan trash | `ndus`, `jsToken`, `bdstoken` |

---

## 6. Upload Flow (Detail)

Upload file ke Terabox terdiri dari **3 fase**:

### Fase 1: Pre-create

```
POST /rest/2.0/xpan/file?method=precreate&bdstoken=TOKEN&jsToken=TOKEN

Body (form-urlencoded):
  path        = /remote_path.mp4
  size        = 10485760
  block_list  = ["md5_chunk_1", "md5_chunk_2"]   ← JSON array MD5 setiap chunk 4MB
  autoinit    = 1
  rtype       = 1
```

**Response sukses** (`errno: 0`):
```json
{
  "uploadid": "uuid-xxx",
  "block_list": ["md5_of_missing_chunk_1"]  ← chunk yang perlu diupload
}
```

Jika `block_list` kosong → **Rapid Upload** sukses, file sudah ada di server.  
Langsung ke Fase 3 (atau selesai).

### Fase 2: Upload Chunks

Hanya untuk chunk yang ada di `block_list` hasil Fase 1.

```
POST https://{node}.1024terabox.com/rest/2.0/pcs/superfile2?method=upload&app_id=250528&uploadid=ID&path=/remote_path.mp4&partseq=0&uploadsign=0

Body: multipart/form-data
  file = <binary chunk data>
```

**Response**:
```json
{"md5": "calculated_md5_of_chunk"}
```

### Fase 3: Create (Finalize)

```
POST /rest/2.0/xpan/file?method=create&bdstoken=TOKEN&jsToken=TOKEN

Body (form-urlencoded):
  path       = /remote_path.mp4
  size       = 10485760
  uploadid   = id_dari_fase_1
  block_list = ["md5_1", "md5_2"]   ← SEMUA chunk, berurutan
  isdir      = 0
  rtype      = 1
```

### Upload Flow Diagram

```
                    ┌─────────────┐
                    │  PRE-CREATE │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │ block_list  │
                    │ kosong?     │
                    └──┬──────┬───┘
                  YES  │      │  NO
                       │      │
                       │   ┌──▼──────────┐
                       │   │ UPLOAD CHUNK│
                       │   └──┬──────────┘
                       │      │ (loop per chunk)
                       │      │
                       │   ┌──▼──────────┐
                       │   │  CREATE     │
                       │   └──────┬──────┘
                       │          │
                    ┌──▼──────────▼──┐
                    │    SELESAI     │
                    └────────────────┘
```

---

## 7. Download Flow (Detail)

### Langkah 1: Dapatkan Download Link

```
GET /rest/2.0/pcs/file?method=download&app_id=250528&path=/MyVideo.mp4&jsToken=TOKEN

Headers: Cookie: ndus=...; User-Agent: Mozilla/5.0...
```

→ Response: **302 Redirect** ke `Location: https://d10.terabox.com/file/...`

### Langkah 2: Download File

```
GET <dlink_URL>
Headers:
  Cookie: ndus=...
  User-Agent: <SAMA PERSIS dengan langkah 1>
  Range: bytes=0-1048575   ← opsional
```

**⚠️ Kritis**: User-Agent harus **sama persis** antara langkah 1 dan 2,  
jika tidak → `403 Forbidden`.

---

## 8. Perbandingan: Dokumentasi vs Implementasi Saat Ini

### 8.1 Upload (`mirrors/terabox_mirror.py`)

| Aspek | Dokumentasi | Implementasi Saat Ini | Masalah |
|-------|------------|----------------------|---------|
| **Fase 1 Endpoint** | `POST /rest/2.0/xpan/file?method=precreate` | `POST https://www.terabox.com/api/precreate` | ❌ Berbeda endpoint |
| **Fase 3 Endpoint** | `POST /rest/2.0/xpan/file?method=create` | `POST https://www.terabox.com/api/create` | ❌ Berbeda endpoint |
| **Fase 2 Endpoint** | `POST https://{node}.1024terabox.com/rest/2.0/pcs/superfile2` | `POST https://c3.terabox.com/rest/2.0/pcs/superfile2` | ⚠️ Hardcode `c3.` |
| **`bdstoken`** | Wajib (query param) | ❌ **Tidak dikirim** | 🔴 KRITIS |
| **`jsToken`** | Wajib (query param) | ❌ **Tidak dikirim** | 🔴 KRITIS |
| **`autoinit`** | Harus `1` | ❌ **Tidak dikirim** | 🔴 KRITIS |
| **`rtype`** | Harus `1` | ❌ **Tidak dikirim** | 🔴 KRITIS |
| **`block_list` di Fase 1** | Array MD5 setiap chunk | `'[]'` (array kosong) | ❌ Tidak validasi rapid upload |
| **`block_list` di Fase 3** | Array MD5 SEMUA chunk | Hasil dari response upload | ⚠️ Mungkin OK |
| **`uploadsign`** | `0` | ❌ **Tidak dikirim** | ⚠️ |
| **Rapid Upload** | Didukung (skip Fase 2 jika blok sudah ada) | ❌ **Tidak diimplementasi** | Tidak efisien |
| **Resumable** | Didukung (per-chunk) | Parsial (chunk 4MB) | OK |
| **Domain** | `1024terabox.com` | `www.terabox.com` | ⚠️ Cookie mungkin beda |
| **Headers** | User-Agent, Referer, Origin | User-Agent saja | ❌ Kurang |

### 8.2 Download (`downloaders/terabox.py`)

| Aspek | Dokumentasi | Implementasi Saat Ini | Masalah |
|-------|------------|----------------------|---------|
| **Get dlink endpoint** | `GET /rest/2.0/pcs/file?method=download` | Tidak pakai API — langsung dari info response | ⚠️ Bergantung API pihak ke-3 |
| **ndus cookie** | Wajib di header | ❌ Tidak dikirim | ❌ Kalau pake direct download |
| **User-Agent konsisten** | Wajib sama | Mungkin beda | ⚠️ |
| **Path-based download** | Pakai path remote | Pakai dlink langsung | ⚠️ |

### 8.3 Autentikasi

| Aspek | Dokumentasi | Implementasi | Masalah |
|-------|------------|-------------|---------|
| `ndus` cookie | Ada di `.env` | Ada | ✅ |
| `bdstoken` | Wajib untuk write | ❌ **Tidak disimpan** | 🔴 |
| `jsToken` | Wajib untuk semua | ❌ **Tidak disimpan** | 🔴 |
| `PANWEB=1` cookie | Disarankan | ❌ Tidak ada | ⚠️ |
| Headers (Referer, Origin) | Wajib | ❌ Tidak ada | ⚠️ |

---

## 9. Bugs di Implementasi Saat Ini

### 🔴 Critical

#### 9.1 `bdstoken` dan `jsToken` tidak pernah dikirim

Dokumentasi dengan jelas menyebutkan `bdstoken` **wajib** untuk semua operasi write (upload, rename, delete, dll) dan `jsToken` untuk **semua operasi**.

Di `mirrors/terabox_mirror.py`:
```python
params = {
    'method': 'upload',
    'path': ...,
    'uploadid': ...,
    'partseq': ...,
}
```
Tidak ada `bdstoken`, tidak ada `jsToken`, tidak ada `app_id=250528`.

**Akibat**: Request bisa ditolak server, atau upload "berhasil" secara semu tapi file tidak benar-benar tersimpan.

#### 9.2 Endpoint precreate/create salah

Dokumentasi:  
- Precreate: `POST /rest/2.0/xpan/file?method=precreate`  
- Create: `POST /rest/2.0/xpan/file?method=create`

Implementasi:  
- Precreate: `POST https://www.terabox.com/api/precreate`  
- Create: `POST https://www.terabox.com/api/create`

**Akibat**: Endpoint `/api/precreate` dan `/api/create` mungkin adalah endpoint lawas atau internal yang berbeda. Bisa saja suatu saat berhenti bekerja.

#### 9.3 `autoinit` dan `rtype` tidak dikirim di Fase 1

Dokumentasi: `autoinit=1` dan `rtype=1` wajib di Fase 1 (precreate).  
Implementasi: tidak ada.

#### 9.4 Fase 1 pake `block_list='[]'` (kosong)

Dokumentasi: `block_list` harus berisi MD5 hash setiap chunk 4MB agar server bisa deteksi rapid upload.  
Implementasi: selalu array kosong.

**Akibat**: Setiap upload selalu upload penuh, tidak bisa memanfaatkan rapid upload.

### ⚠️ Warning

#### 9.5 Hardcode upload node `c3.terabox.com`

Implementasi hardcode `c3.terabox.com`. Dokumentasi mengatakan node bisa berbeda-beda (`szb-cdata.1024terabox.com`, `dm-c-all.terabox.com`, dll). Jika node `c3` mati atau berubah, upload akan gagal.

#### 9.6 Cookie domain mismatch

Cookie diset untuk `www.terabox.com` tapi endpoint dokumentasi menggunakan `1024terabox.com`. Perlu dikonfirmasi apakah cookie lintas domain berfungsi.

#### 9.7 User-Agent tidak konsisten

Dokumentasi menekankan User-Agent harus **sama persis** antara request auth dan download. Implementasi saat ini menggunakan User-Agent yang mungkin berbeda antar komponen.

#### 9.8 Tidak ada PANWEB=1 cookie

Dokumentasi menyebut `PANWEB=1` sebagai cookie tambahan. Implementasi tidak mengirimnya.

---

## 10. Rekomendasi Perbaikan

### Prioritas Tinggi (Harus Segera)

1. **Simpan `bdstoken` dan `jsToken` di `.env`**
   ```
   TERABOX_BDS_TOKEN=...
   TERABOX_JS_TOKEN=...
   ```

2. **Perbaiki endpoint precreate/create sesuai dokumentasi**
   - Precreate: `POST https://1024terabox.com/rest/2.0/xpan/file?method=precreate`
   - Create: `POST https://1024terabox.com/rest/2.0/xpan/file?method=create`

3. **Kirim `bdstoken`, `jsToken`, `autoinit=1`, `rtype=1`** di semua fase upload

4. **Hitung MD5 chunk 4MB** dan kirim di `block_list` Fase 1, bukan array kosong

5. **Implementasi rapid upload**: jika Fase 1 balikin `block_list` kosong, skip Fase 2

### Prioritas Sedang

6. **Gunakan `1024terabox.com`** sebagai base URL (bukan `www.terabox.com`)

7. **Tambahkan headers** `Referer` dan `Origin` sesuai dokumentasi

8. **Tambahkan cookie `PANWEB=1`** di session

9. **Jadikan upload node configurable** atau dapatkan dari API

### Prioritas Rendah

10. **Implementasi download via API resmi** (GET `/rest/2.0/pcs/file?method=download`)  
    Sebagai fallback jika dlink dari API pihak ke-3 gagal.

11. **Implementasi resume** untuk download terputus via `Range` header

12. **Buat fungsi periodik refresh token** — karena `ndus` bisa expired dalam beberapa hari

---

## 11. Kode Referensi (Dari Dokumentasi)

### Python — Upload Flow Lengkap

```python
import json
import hashlib

# ===== FASE 1: PRECREATE =====
block_list = []
with open(local_file, 'rb') as f:
    while True:
        chunk = f.read(4 * 1024 * 1024)  # 4MB
        if not chunk:
            break
        block_list.append(hashlib.md5(chunk).hexdigest())

precreate_data = {
    'path': remote_path,
    'size': str(total_size),
    'autoinit': '1',
    'block_list': json.dumps(block_list),
    'rtype': '1',
}

params = {
    'method': 'precreate',
    'bdstoken': BDS_TOKEN,
    'jsToken': JS_TOKEN,
}
resp = session.post(
    'https://1024terabox.com/rest/2.0/xpan/file',
    params=params,
    data=precreate_data
)
result = resp.json()

if result['errno'] != 0:
    raise Exception(f"Precreate gagal: {result.get('errmsg')}")

upload_id = result['uploadid']
needed_blocks = result.get('block_list', [])

# ===== FASE 2: UPLOAD CHUNKS (skip if rapid upload) =====
if needed_blocks:
    with open(local_file, 'rb') as f:
        for partseq in needed_blocks:
            chunk = f.read(4 * 1024 * 1024)
            # Cari posisi sebenarnya
            # ... (perlu map needed_blocks ke posisi)

            files = {'file': ('blob', chunk, 'application/octet-stream')}
            params = {
                'method': 'upload',
                'app_id': '250528',
                'uploadid': upload_id,
                'path': remote_path,
                'partseq': partseq,
                'uploadsign': '0',
            }
            session.post(
                'https://c3.1024terabox.com/rest/2.0/pcs/superfile2',
                params=params,
                files=files
            )

# ===== FASE 3: CREATE =====
create_data = {
    'path': remote_path,
    'size': str(total_size),
    'uploadid': upload_id,
    'block_list': json.dumps(block_list),  # Semua chunk
    'isdir': '0',
    'rtype': '1',
}

params = {
    'method': 'create',
    'bdstoken': BDS_TOKEN,
    'jsToken': JS_TOKEN,
}
resp = session.post(
    'https://1024terabox.com/rest/2.0/xpan/file',
    params=params,
    data=create_data
)
```

### Python — Download Flow Lengkap

```python
# Langkah 1: Dapatkan dlink
params = {
    'method': 'download',
    'app_id': '250528',
    'path': remote_path,
    'jsToken': JS_TOKEN,
}
resp = session.get(
    'https://1024terabox.com/rest/2.0/pcs/file',
    params=params,
    stream=True,
    allow_redirects=False
)

# Ikuti redirect untuk dapatkan dlink
dlink = resp.headers.get('Location') or resp.url

# Langkah 2: Download file
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ...',
    'Cookie': f'ndus={NDUS}',
}
with open(output_path, 'wb') as f:
    r = session.get(dlink, headers=headers, stream=True)
    for chunk in r.iter_content(chunk_size=8192):
        f.write(chunk)
```

---

## 12. Catatan Tambahan

- **Rate Limiting**: Dokumentasi tidak menyebutkan batas rate, tapi server Terabox bisa menolak request jika terlalu cepat.
- **Cookie Expired**: `ndus` expired dalam beberapa hari. Perlu mekanisme refresh.
- **Storage Quota**: Cek via `GET /api/quota` sebelum upload besar.
- **API Pihak Ketiga**: Downloader saat ini menggunakan `terabox.hnn.workers.dev` dan `ytdl.freemediabot.xyz` sebagai API pihak ke-3 yang tidak resmi. Ini rawan downtime/change.
- **Upload Folder**: Saat ini hanya support upload file. Untuk upload folder perlu implementasi Mkdir dulu.

---

## 13. Temuan dari Pengujian Langsung (2026-06-14)

### Domain

| Domain | Status | Kegunaan |
|--------|--------|----------|
| `dm.terabox.com` | ✅ **Berfungsi** | API utama (precreate, create, list, quota, getinfo, download) |
| `www.terabox.com` | ⚠️ Auth beda | Butuh ndus khusus domain `www` |
| `c-jp.terabox.com` | ✅ **PCS upload node** | Upload chunks (dari `locateupload`) |
| `dm1-cdata.terabox.com` | ✅ **PCS upload node alternatif** | Upload chunks |
| `szb-cdata.1024terabox.com` | ❌ POMS key | Cuma reachable kalau ada POMS key |
| `c3.terabox.com` | ❌ DNS tidak resolve | - |

### HTTP Method & Endpoint Real

| Endpoint | Method | Catatan |
|----------|--------|---------|
| `/api/user/getinfo` | **POST** | Browser pake POST, GET juga work |
| `/api/quota` | GET | ✅ |
| `/api/precreate` | **POST** | BUKAN `/rest/2.0/xpan/file` |
| `/api/create` | **POST** | BUKAN `/rest/2.0/xpan/file` |
| `/api/list` | **POST** / GET | Library pake POST |
| `/api/rapidupload` | POST | Endpoint khusus rapid |
| `/api/download` | POST | Dapatkan dlink dari fs_id |
| `/api/shorturlinfo` | GET | Resolve share link |
| `/rest/2.0/pcs/file?method=locateupload` | GET | Dapatkan upload host PCS |
| `/rest/2.0/pcs/superfile2` | POST | Upload chunk (ke PCS host) |

### User-Agent yang Benar

**BUKAN browser UA**, tapi UA khusus Terabox Client:
```
terabox;1.40.0.132;PC;PC-Windows;10.0.26100;WindowsTeraBox
```
Ini kunci utama — tanpa UA ini, precreate kadang login error.

### Upload Flow yang Berhasil (Confirmed ✅)

```
1. GET  /rest/2.0/pcs/file?method=locateupload
       → dapatkan upload host (c-jp.terabox.com / dm1-cdata.terabox.com)

2. POST /api/precreate?app_id=250528&jsToken=...
       Body: path, autoinit=1, size, block_list=[md5_chunks], rtype=2,
              content-md5, slice-md5, content-crc32
       → dapatkan upload_id + needed_blocks

3. POST {uhost}/rest/2.0/pcs/superfile2?method=upload&app_id=250528&...
       FormData: file=<chunk_data>
       → untuk setiap chunk di needed_blocks

4. POST /api/create?app_id=250528&jsToken=...
       Body: path, size, uploadid, block_list=[md5_chunks], isdir=0, rtype=2,
              content-md5, slice-md5, content-crc32
       → finalisasi
```

### Parameter Kunci

| Parameter | Dokumentasi | Realita |
|-----------|------------|---------|
| `rtype` | `1` | **`2`** |
| `block_list` | Array MD5 chunk | ✅ Sama |
| `content-md5` | Tidak disebut | **Wajib** — MD5 file lengkap |
| `slice-md5` | Tidak disebut | **Wajib** — MD5 slice pertama |
| `content-crc32` | Tidak disebut | Wajib (bisa `0`) |
| `autoinit` | `1` | ✅ `1` |
| `bdstoken` | Wajib | ❌ **Tidak diperlukan** untuk precreate/create |
| `jsToken` | Wajib | ✅ Wajib (dari `updateAppData` atau config) |
| `devuid` | Tidak disebut | ❌ Tidak diperlukan |

### POMS Key

**TIDAK DIPERLUKAN** kalau menggunakan:
- Upload host hasil `locateupload` (bukan hardcode `szb-cdata`)
- User-Agent Terabox client (bukan browser)
- Endpoint yang benar (`/api/precreate` + `/api/create`)

Error `"Invalid param poms key"` terjadi karena:
1. Upload host hardcode (`szb-cdata.1024terabox.com`) yang sudah deprecated
2. User-Agent browser yang tidak sesuai
3. Parameter `uploadsign=0` yang salah

### Source Code Referensi

Implementasi sukses berdasarkan **npm `terabox-api` v2.9.2**:
- https://www.npmjs.com/package/terabox-api
- Library: `seiya-npm/terabox-api`
- Endpoints dan parameter diambil dari `api.js` source

### Download Flow (Official)

```
1. POST /api/download
       Body: fidlist=[fs_ids], type=dlink, vip=2, need_speed=1
       → dapatkan array dlink

2. GET {dlink} dengan User-Agent sama
       → download file
```

Atau via path:
```
1. GET /rest/2.0/pcs/file?method=download&app_id=250528&path=/file&jsToken=...
       → 302 redirect ke dlink

2. GET {dlink} dengan User-Agent sama
       → download file
```

---

*Dokumen ini disusun berdasarkan dokumentasi resmi https://herobenhero.github.io/1024TeraBox-REST-API/index.html,
source code npm library `terabox-api` v2.9.2, dan pengujian langsung API real.*

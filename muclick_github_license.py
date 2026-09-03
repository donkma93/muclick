# -*- coding: utf-8 -*-
"""
Kích hoạt license online qua GitHub Contents API
Repo: donkma93/muclick → licenses/keys.json
(Lưu ý: repo public — ai cũng có thể đọc keys.json nếu không đổi sang private.)
"""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from datetime import date, datetime

from muclick_license import (
    clear_license,
    get_hwid,
    load_saved_license,
    normalize_key,
    save_license,
)
from muclick_paths import APP_VERSION

LICENSE_REPO_OWNER = "donkma93"
LICENSE_REPO_NAME = "muclick"
LICENSE_FILE_PATH = "licenses/keys.json"
API_BASE = "https://api.github.com"
USER_AGENT = "MuClick-License"
ADMIN_PASSWORD = "donpv93"


class LicenseOnlineError(Exception):
    """Lỗi mạng / API / nghiệp vụ license."""


def _load_token() -> str:
    tok = (os.environ.get("MUCLICK_GH_TOKEN") or "").strip()
    if tok:
        return tok
    try:
        from muclick_secrets import GITHUB_LICENSE_TOKEN as t  # type: ignore

        tok = (t or "").strip()
    except Exception:
        tok = ""
    return tok


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _request_json(method: str, url: str, token: str, body: dict | None = None):
    data = None
    headers = _headers(token)
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        try:
            detail = e.read().decode("utf-8", errors="replace")
        except Exception:
            detail = ""
        raise LicenseOnlineError(f"GitHub HTTP {e.code}: {detail or e.reason}") from e
    except Exception as e:
        raise LicenseOnlineError(f"Không kết nối GitHub: {e}") from e


def _contents_url() -> str:
    return (
        f"{API_BASE}/repos/{LICENSE_REPO_OWNER}/{LICENSE_REPO_NAME}"
        f"/contents/{LICENSE_FILE_PATH}"
    )


def _empty_doc() -> dict:
    return {"version": 1, "keys": []}


def fetch_keys_document(token: str | None = None) -> tuple[dict, str | None]:
    """
    Trả về (document, sha).
    sha=None nếu file chưa tồn tại trên repo (cần PUT tạo mới).
    """
    token = token or _load_token()
    if not token:
        raise LicenseOnlineError(
            "Chưa cấu hình GitHub token (MUCLICK_GH_TOKEN hoặc muclick_secrets.py)."
        )
    try:
        meta = _request_json("GET", _contents_url(), token)
    except LicenseOnlineError as e:
        if "HTTP 404" in str(e):
            return _empty_doc(), None
        raise
    content_b64 = meta.get("content") or ""
    sha = meta.get("sha") or ""
    if not sha:
        raise LicenseOnlineError("GitHub không trả sha cho keys.json.")
    try:
        raw = base64.b64decode(content_b64.replace("\n", ""))
        doc = json.loads(raw.decode("utf-8"))
    except Exception as e:
        raise LicenseOnlineError(f"keys.json không hợp lệ: {e}") from e
    if not isinstance(doc, dict):
        raise LicenseOnlineError("keys.json sai cấu trúc.")
    if "keys" not in doc or not isinstance(doc["keys"], list):
        doc["keys"] = []
    if "version" not in doc:
        doc["version"] = 1
    return doc, sha


def put_keys_document(
    doc: dict, sha: str | None, message: str, token: str | None = None
):
    token = token or _load_token()
    if not token:
        raise LicenseOnlineError("Chưa cấu hình GitHub token.")
    raw = json.dumps(doc, ensure_ascii=False, indent=2).encode("utf-8")
    body = {
        "message": message,
        "content": base64.b64encode(raw).decode("ascii"),
    }
    if sha:
        body["sha"] = sha
    return _request_json("PUT", _contents_url(), token, body)


def find_key_entry(doc: dict, key: str) -> dict | None:
    want = normalize_key(key)
    if not want:
        return None
    for item in doc.get("keys") or []:
        if not isinstance(item, dict):
            continue
        if normalize_key(item.get("key") or "") == want:
            return item
    return None


def _parse_exp(entry: dict) -> date:
    try:
        return date.fromisoformat(str(entry.get("exp") or "")[:10])
    except Exception as e:
        raise LicenseOnlineError("Key thiếu/sai ngày hết hạn (exp).") from e


def _validate_entry_common(entry: dict) -> date:
    if entry.get("enabled") is False:
        raise LicenseOnlineError("Key đã bị tắt (revoked).")
    exp = _parse_exp(entry)
    if exp < date.today():
        raise LicenseOnlineError(f"Key đã hết hạn ngày {exp.isoformat()}.")
    return exp


def _hwid_list(entry: dict) -> list[dict]:
    raw = entry.get("hwids") or []
    if not isinstance(raw, list):
        return []
    return [x for x in raw if isinstance(x, dict) and x.get("hwid")]


def _info_from_entry(entry: dict, key: str, hwid: str, exp: date) -> dict:
    return {
        "key": normalize_key(key),
        "key_id": str(entry.get("id") or ""),
        "exp": exp,
        "note": str(entry.get("note") or ""),
        "hwid": hwid,
        "days_left": (exp - date.today()).days,
        "activated_at": datetime.now().isoformat(timespec="seconds"),
        "last_online_check": datetime.now().isoformat(timespec="seconds"),
    }


def activate_or_revalidate(key: str | None = None, hwid: str | None = None) -> dict:
    """
    Kích hoạt / xác minh online.
    - key=None → dùng key trong license.json local
    Trả về info dict; raise LicenseOnlineError nếu fail.
    """
    hwid = hwid or get_hwid()
    saved = load_saved_license()
    key = normalize_key(key or ((saved or {}).get("key") or ""))
    if not key:
        raise LicenseOnlineError("Chưa có license key.")

    token = _load_token()
    last_err = None
    for attempt in range(3):
        try:
            doc, sha = fetch_keys_document(token)
            entry = find_key_entry(doc, key)
            if not entry:
                clear_license()
                raise LicenseOnlineError("Key không tồn tại trên server.")

            exp = _validate_entry_common(entry)
            max_devices = int(entry.get("max_devices") or 1)
            if max_devices < 1:
                max_devices = 1
            hwids = _hwid_list(entry)
            bound = [h.get("hwid") for h in hwids]

            if hwid in bound:
                info = _info_from_entry(entry, key, hwid, exp)
                save_license(info)
                return info

            if len(bound) >= max_devices:
                clear_license()
                raise LicenseOnlineError(
                    "Key đã được kích hoạt trên máy khác (giới hạn 1 máy/key)."
                )

            # Bind HWID mới
            hwids.append(
                {
                    "hwid": hwid,
                    "bound_at": datetime.now().isoformat(timespec="seconds"),
                    "app_version": APP_VERSION,
                }
            )
            entry["hwids"] = hwids
            # ghi lại entry trong doc (cùng object reference đã đủ)
            put_keys_document(
                doc,
                sha,
                message=f"chore: bind HWID for {entry.get('id') or 'key'}",
                token=token,
            )
            info = _info_from_entry(entry, key, hwid, exp)
            save_license(info)
            return info
        except LicenseOnlineError as e:
            msg = str(e)
            # conflict sha → retry
            if "409" in msg or "sha" in msg.lower() and attempt < 2:
                last_err = e
                continue
            raise
        except Exception as e:
            last_err = LicenseOnlineError(str(e))
            if attempt >= 2:
                raise last_err from e
    raise last_err or LicenseOnlineError("Kích hoạt thất bại.")


def revalidate_saved() -> dict:
    """Xác minh lại license đã lưu (bắt buộc online)."""
    saved = load_saved_license()
    if not saved:
        raise LicenseOnlineError("Chưa kích hoạt license.")
    # Nếu local HWID lệch máy hiện tại → fail sớm
    current = get_hwid()
    cached = saved.get("hwid") or ""
    if cached and cached != current:
        clear_license()
        raise LicenseOnlineError(
            "License không khớp máy này (HWID khác). Hãy kích hoạt lại."
        )
    return activate_or_revalidate(key=saved.get("key"), hwid=current)


def append_key_to_repo(
    key: str,
    exp: str,
    note: str = "",
    key_id: str | None = None,
    max_devices: int = 1,
    token: str | None = None,
) -> dict:
    """Admin: thêm key mới vào keys.json trên repo."""
    key = normalize_key(key) if key else ""
    if not key:
        raise LicenseOnlineError("Key trống.")
    # validate date
    date.fromisoformat(str(exp)[:10])

    token = token or _load_token()
    for attempt in range(3):
        doc, sha = fetch_keys_document(token)
        if find_key_entry(doc, key):
            raise LicenseOnlineError("Key đã tồn tại trên repo.")
        if not key_id:
            key_id = f"K{len(doc.get('keys') or []) + 1:03d}"
        entry = {
            "id": key_id,
            "key": key,
            "exp": str(exp)[:10],
            "note": note or "",
            "max_devices": int(max_devices) or 1,
            "enabled": True,
            "hwids": [],
        }
        doc.setdefault("keys", []).append(entry)
        try:
            put_keys_document(
                doc, sha, message=f"chore: add license {key_id}", token=token
            )
            return entry
        except LicenseOnlineError as e:
            if "409" in str(e) and attempt < 2:
                continue
            raise
    raise LicenseOnlineError("Không ghi được keys.json.")


def create_and_push_license(
    *,
    days: int | None = None,
    exp: str | None = None,
    note: str = "",
    key_id: str | None = None,
    max_devices: int = 1,
) -> dict:
    """
    Admin: sinh key mới + đẩy lên GitHub.
    Trả về entry (có field key, id, exp, ...).
    """
    from datetime import timedelta

    from muclick_license import generate_key

    if days is not None:
        if days < 0:
            raise LicenseOnlineError("Số ngày phải >= 0.")
        exp_s = (date.today() + timedelta(days=int(days))).isoformat()
    elif exp:
        exp_s = str(exp)[:10]
        date.fromisoformat(exp_s)
    else:
        raise LicenseOnlineError("Cần số ngày hoặc ngày hết hạn.")

    key = generate_key()
    return append_key_to_repo(
        key=key,
        exp=exp_s,
        note=note,
        key_id=key_id,
        max_devices=max_devices,
    )

def is_admin_password(text: str) -> bool:
    return (text or "").strip() == ADMIN_PASSWORD


def list_keys_summary(token: str | None = None) -> list[dict]:
    """Tóm tắt keys trên repo cho Admin UI."""
    doc, _sha = fetch_keys_document(token)
    out = []
    for item in doc.get("keys") or []:
        if not isinstance(item, dict):
            continue
        hwids = item.get("hwids") or []
        out.append(
            {
                "id": item.get("id"),
                "key": item.get("key"),
                "exp": item.get("exp"),
                "note": item.get("note") or "",
                "enabled": item.get("enabled", True),
                "bound": len(hwids) if isinstance(hwids, list) else 0,
                "max_devices": item.get("max_devices", 1),
            }
        )
    return out

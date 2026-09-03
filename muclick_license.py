# -*- coding: utf-8 -*-
"""
License MuClick — local cache + HWID.
Nguồn tin cậy kích hoạt: GitHub private repo (xem muclick_github_license).
"""

from __future__ import annotations

import ctypes
import hashlib
import os
import secrets
import winreg
from datetime import date, datetime

from muclick_paths import data_path

LICENSE_FILE = data_path("license.json")
KEY_PREFIX = "MUCLK-"


def normalize_key(key: str) -> str:
    if not key:
        return ""
    return str(key).strip().replace(" ", "").replace("\n", "").replace("\r", "")


def generate_key() -> str:
    """Key random online — không verify offline."""
    return KEY_PREFIX + secrets.token_urlsafe(24)


def _machine_guid() -> str:
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography"
        ) as key:
            val, _ = winreg.QueryValueEx(key, "MachineGuid")
            return str(val)
    except Exception:
        return "unknown-guid"


def _volume_serial() -> str:
    try:
        kernel32 = ctypes.windll.kernel32
        serial = ctypes.c_uint(0)
        kernel32.GetVolumeInformationW(
            ctypes.c_wchar_p("C:\\"),
            None,
            0,
            ctypes.byref(serial),
            None,
            None,
            None,
            0,
        )
        return f"{serial.value:08X}"
    except Exception:
        return "00000000"


def get_hwid() -> str:
    """
    Fingerprint máy (hash) — không gửi raw identifier lên repo.
    """
    raw = "|".join(
        [
            _machine_guid(),
            _volume_serial(),
            os.environ.get("USERNAME") or os.environ.get("USER") or "",
            os.environ.get("COMPUTERNAME") or "",
        ]
    )
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()


def load_saved_license():
    try:
        if not os.path.isfile(LICENSE_FILE):
            return None
        import json

        with open(LICENSE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and data.get("key"):
            return data
    except Exception:
        pass
    return None


def save_license(info: dict):
    import json

    os.makedirs(os.path.dirname(LICENSE_FILE), exist_ok=True)
    exp = info.get("exp")
    if isinstance(exp, date):
        exp = exp.isoformat()
    payload = {
        "key": normalize_key(info.get("key") or ""),
        "exp": exp or "",
        "hwid": info.get("hwid") or get_hwid(),
        "key_id": info.get("key_id") or "",
        "note": info.get("note") or "",
        "activated_at": info.get("activated_at")
        or datetime.now().isoformat(timespec="seconds"),
        "last_online_check": info.get("last_online_check")
        or datetime.now().isoformat(timespec="seconds"),
        "days_left": info.get("days_left"),
    }
    with open(LICENSE_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def clear_license():
    try:
        if os.path.isfile(LICENSE_FILE):
            os.remove(LICENSE_FILE)
    except Exception:
        pass


def days_left_from_exp(exp) -> int | None:
    try:
        if isinstance(exp, date):
            d = exp
        else:
            d = date.fromisoformat(str(exp)[:10])
        return (d - date.today()).days
    except Exception:
        return None

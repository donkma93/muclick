# -*- coding: utf-8 -*-
"""
Kiểm tra & bắt buộc cập nhật MuClick từ GitHub Releases.
Asset bắt buộc: MuClick.exe trên release tag mới nhất.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

from muclick_paths import APP_VERSION, exe_path, install_dir, is_frozen

GITHUB_OWNER = "donkma93"
GITHUB_REPO = "muclick"
RELEASE_ASSET_NAME = "MuClick.exe"
API_LATEST = (
    f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
)
USER_AGENT = "MuClick-Updater"


class UpdateCheckError(Exception):
    def __init__(self, message, *, no_releases=False):
        super().__init__(message)
        self.no_releases = no_releases


def normalize_version(text: str) -> str:
    if not text:
        return "0.0.0"
    text = str(text).strip()
    if text.lower().startswith("v"):
        text = text[1:]
    # chỉ lấy phần số.số.số đầu
    m = re.match(r"(\d+(?:\.\d+){0,3})", text)
    return m.group(1) if m else "0.0.0"


def version_tuple(text: str):
    parts = normalize_version(text).split(".")
    nums = []
    for p in parts[:3]:
        try:
            nums.append(int(p))
        except Exception:
            nums.append(0)
    while len(nums) < 3:
        nums.append(0)
    return tuple(nums)


def is_newer(remote: str, local: str) -> bool:
    return version_tuple(remote) > version_tuple(local)


def _http_get_json(url: str, timeout=20):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_latest_release():
    """
    Trả về dict:
      tag, version, asset_name, download_url, size
    Raise UpdateCheckError nếu lỗi / không có release / thiếu asset.
    """
    try:
        data = _http_get_json(API_LATEST)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise UpdateCheckError(
                "Chưa có GitHub Release nào trên repo.",
                no_releases=True,
            ) from e
        raise UpdateCheckError(f"GitHub API lỗi HTTP {e.code}.") from e
    except Exception as e:
        raise UpdateCheckError(f"Không kiểm tra được phiên bản: {e}") from e

    tag = data.get("tag_name") or ""
    version = normalize_version(tag)
    assets = data.get("assets") or []
    asset = None
    for a in assets:
        if (a.get("name") or "") == RELEASE_ASSET_NAME:
            asset = a
            break
    if not asset:
        names = [a.get("name") for a in assets if a.get("name")]
        raise UpdateCheckError(
            f"Release {tag} không có asset `{RELEASE_ASSET_NAME}`."
            + (f" Có: {', '.join(names)}" if names else " (không có asset nào)")
        )
    url = asset.get("browser_download_url")
    if not url:
        raise UpdateCheckError("Asset thiếu download URL.")
    return {
        "tag": tag,
        "version": version,
        "asset_name": RELEASE_ASSET_NAME,
        "download_url": url,
        "size": int(asset.get("size") or 0),
        "name": data.get("name") or tag,
    }


def check_for_mandatory_update(local_version: str = APP_VERSION):
    """
    Trả về:
      {"status": "ok"} — local >= latest
      {"status": "bootstrap"} — chưa có release (cho chạy lần đầu)
      {"status": "update_required", "release": {...}, "local": "..."}
    Raise UpdateCheckError với no_releases=False cho lỗi mạng/API.
    """
    try:
        release = fetch_latest_release()
    except UpdateCheckError as e:
        if e.no_releases:
            return {"status": "bootstrap", "local": normalize_version(local_version)}
        raise

    local = normalize_version(local_version)
    remote = release["version"]
    if is_newer(remote, local):
        return {
            "status": "update_required",
            "local": local,
            "release": release,
        }
    return {"status": "ok", "local": local, "remote": remote, "release": release}


def download_file(url: str, dest_path: str, progress_cb=None, timeout=60):
    """Tải file; progress_cb(downloaded, total)."""
    os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        downloaded = 0
        chunk = 1024 * 64
        with open(dest_path, "wb") as f:
            while True:
                buf = resp.read(chunk)
                if not buf:
                    break
                f.write(buf)
                downloaded += len(buf)
                if progress_cb:
                    progress_cb(downloaded, total)
    return dest_path


def target_exe_path():
    """File exe sẽ bị thay thế."""
    if is_frozen():
        return os.path.abspath(sys.executable)
    # Dev: ghi vào install_dir/MuClick.exe (không đè .py)
    return os.path.join(install_dir(), RELEASE_ASSET_NAME)


def write_and_run_replace_script(new_exe: str, dest_exe: str | None = None):
    """
    Tạo .bat: đợi process thoát → đổi tên bản cũ → copy file mới →
    Unblock-File → kiểm tra size → start lại.

    Dùng rename + copy thay vì copy đè trực tiếp để tránh file bị khóa /
    AV quét giữa chừng gây lỗi khởi động 0xc0000142.
    """
    dest_exe = dest_exe or target_exe_path()
    new_exe = os.path.abspath(new_exe)
    dest_exe = os.path.abspath(dest_exe)
    dest_dir = os.path.dirname(dest_exe) or "."
    old_bak = dest_exe + ".old"
    expected_size = os.path.getsize(new_exe)
    bat_path = os.path.join(tempfile.gettempdir(), "muclick_apply_update.bat")
    log_path = os.path.join(tempfile.gettempdir(), "muclick_update.log")

    def q(p):
        return '"' + p.replace('"', "") + '"'

    lines = [
        "@echo off",
        "setlocal EnableExtensions",
        f"echo MuClick update start > {q(log_path)}",
        f"echo new={q(new_exe)} >> {q(log_path)}",
        f"echo dest={q(dest_exe)} >> {q(log_path)}",
        "rem Cho process cũ thoát hẳn + AV nhả file",
        "timeout /t 3 /nobreak >nul",
        f"del /F /Q {q(old_bak)} >nul 2>&1",
        "set /a tries=0",
        ":retry_rename",
        "set /a tries+=1",
        f'if exist {q(dest_exe)} (',
        f"  move /Y {q(dest_exe)} {q(old_bak)} >> {q(log_path)} 2>&1",
        "  if errorlevel 1 (",
        "    if %tries% GEQ 30 (",
        f"      echo FAIL rename after %tries% >> {q(log_path)}",
        "      goto fail",
        "    )",
        "    timeout /t 1 /nobreak >nul",
        "    goto retry_rename",
        "  )",
        ")",
        "set /a tries=0",
        ":retry_copy",
        "set /a tries+=1",
        f"copy /B /Y {q(new_exe)} {q(dest_exe)} >> {q(log_path)} 2>&1",
        "if errorlevel 1 (",
        "  if %tries% GEQ 30 (",
        f"    echo FAIL copy after %tries% >> {q(log_path)}",
        "    goto restore",
        "  )",
        "  timeout /t 1 /nobreak >nul",
        "  goto retry_copy",
        ")",
        f'for %%A in ({q(dest_exe)}) do set "gotsize=%%~zA"',
        f"if not \"%gotsize%\"==\"{expected_size}\" (",
        f"  echo FAIL size got=%gotsize% expect={expected_size} >> {q(log_path)}",
        "  goto restore",
        ")",
        "rem Gỡ Zone.Identifier (Mark of the Web) nếu có — tránh SmartScreen/0xc0000142",
        f"powershell -NoProfile -ExecutionPolicy Bypass -Command \"try {{ Unblock-File -LiteralPath '{dest_exe.replace(chr(39), '')}' -ErrorAction SilentlyContinue }} catch {{}}\" >nul 2>&1",
        f'del /F /Q {q(dest_exe + ":Zone.Identifier")} >nul 2>&1',
        "timeout /t 1 /nobreak >nul",
        f"echo OK launching >> {q(log_path)}",
        f"start \"\" {q(dest_exe)}",
        f"del /F /Q {q(new_exe)} >nul 2>&1",
        f"del /F /Q {q(old_bak)} >nul 2>&1",
        f'del /F /Q "%~f0" >nul 2>&1',
        "exit /b 0",
        ":restore",
        f'if exist {q(old_bak)} move /Y {q(old_bak)} {q(dest_exe)} >> {q(log_path)} 2>&1',
        ":fail",
        f"echo FAIL see {q(log_path)}",
        f'del /F /Q "%~f0" >nul 2>&1',
        "exit /b 1",
    ]
    with open(bat_path, "w", encoding="utf-8") as f:
        f.write("\r\n".join(lines) + "\r\n")

    flags = 0
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        flags |= subprocess.CREATE_NO_WINDOW
    if hasattr(subprocess, "DETACHED_PROCESS"):
        flags |= subprocess.DETACHED_PROCESS
    subprocess.Popen(
        ["cmd.exe", "/c", bat_path],
        cwd=dest_dir,
        close_fds=True,
        creationflags=flags,
    )
    return bat_path


def apply_update_and_exit(download_url: str, progress_cb=None):
    """Tải MuClick.exe mới, chạy script replace, rồi sys.exit(0)."""
    tmp_dir = os.path.join(tempfile.gettempdir(), "MuClick_update")
    os.makedirs(tmp_dir, exist_ok=True)
    tmp_exe = os.path.join(tmp_dir, RELEASE_ASSET_NAME)
    # Tải vào file tạm rồi rename → tránh exe nửa chừng nếu bị ngắt
    tmp_part = tmp_exe + ".part"
    if os.path.isfile(tmp_part):
        try:
            os.remove(tmp_part)
        except OSError:
            pass
    download_file(download_url, tmp_part, progress_cb=progress_cb)
    if not os.path.isfile(tmp_part) or os.path.getsize(tmp_part) < 1024:
        raise UpdateCheckError("File tải về không hợp lệ.")
    if os.path.isfile(tmp_exe):
        try:
            os.remove(tmp_exe)
        except OSError:
            pass
    os.replace(tmp_part, tmp_exe)
    write_and_run_replace_script(tmp_exe, target_exe_path())
    sys.exit(0)

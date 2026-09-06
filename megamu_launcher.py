# -*- coding: utf-8 -*-
"""
MEGAMU Multi-Account Launcher
- Mở / sắp xếp nhiều cửa sổ game theo lưới
- Quản lý tài khoản
- Ghi tọa độ theo TỪNG LAYOUT + TỪNG Ô (2x2, 3x3, ...)
- Auto đăng nhập theo slot
"""

from __future__ import annotations

import ctypes
import json
import math
import os
import re
import subprocess
import threading
import time
import tkinter as tk
import winreg
from ctypes import wintypes
from tkinter import filedialog, messagebox, simpledialog, ttk

from muclick_gates import (
    is_admin_password,
    run_admin_license_dialog,
    run_license_gate,
    run_update_gate,
)
from muclick_paths import APP_VERSION, data_path, install_dir, migrate_user_files

# ---------------------------------------------------------------------------
# Win32
# ---------------------------------------------------------------------------
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.OpenClipboard.restype = wintypes.BOOL
user32.CloseClipboard.restype = wintypes.BOOL
user32.EmptyClipboard.restype = wintypes.BOOL
user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
user32.SetClipboardData.restype = wintypes.HANDLE
user32.GetClipboardData.argtypes = [wintypes.UINT]
user32.GetClipboardData.restype = wintypes.HANDLE
user32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
user32.IsClipboardFormatAvailable.restype = wintypes.BOOL
kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalUnlock.restype = wintypes.BOOL
kernel32.GlobalSize.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalSize.restype = ctypes.c_size_t

SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
SWP_FRAMECHANGED = 0x0020
SW_RESTORE = 9
GWL_STYLE = -16
WS_MAXIMIZE = 0x01000000
HWND_TOP = 0

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_VIRTUALDESK = 0x4000
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
VK_CONTROL = 0x11
VK_SHIFT = 0x10
VK_MENU = 0x12  # Alt
VK_RETURN = 0x0D
VK_TAB = 0x09
VK_A = 0x41
VK_V = 0x56
VK_F8 = 0x77
VK_F9 = 0x78
VK_ESCAPE = 0x1B
VK_BACK = 0x08
VK_HOME = 0x24
VK_END = 0x23
VK_LBUTTON = 0x01
KEYEVENTF_SCANCODE = 0x0008
KEYEVENTF_EXTENDEDKEY = 0x0001
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
WM_CHAR = 0x0102
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
MK_LBUTTON = 0x0001
EXTENDED_VKS = {VK_HOME, VK_END, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E}  # arrows/ins/del
SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79
MONITORINFOF_PRIMARY = 0x00000001

UNITY_CLASS = "UnityWndClass"
MEGAMU_PROCESS_NAMES = ("MEGAMU.exe", "Dashboard.exe")
APP_DIR = install_dir()
# Dữ liệu user nằm %APPDATA%\MuClick (survive khi update thay exe)
migrate_user_files(
    (
        "accounts.json",
        "click_coords.json",
        "autoclick_points.json",
        "app_settings.json",
        "commands.json",
    )
)
ACCOUNTS_FILE = data_path("accounts.json")
COORDS_FILE = data_path("click_coords.json")
AUTOCLICK_FILE = data_path("autoclick_points.json")
SETTINGS_FILE = data_path("app_settings.json")
COMMANDS_FILE = data_path("commands.json")


def load_app_settings() -> dict:
    if os.path.isfile(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_app_settings(settings: dict):
    try:
        cur = load_app_settings()
        cur.update(settings)
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(cur, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


DEFAULT_COMMAND_PRESETS = [
    {"name": "Tự động chấp nhận (PT/Trade)", "cmd": "/re auto"},
    {"name": "Tự động đánh quái (Attack)", "cmd": "/attack"},
    {"name": "Tự động nhặt đồ (Pick)", "cmd": "/pick"},
    {"name": "Tự động nhặt Zen", "cmd": "/pick zen"},
    {"name": "Ủy thác bán hàng (Offtrade)", "cmd": "/offtrade"},
    {"name": "Rao bài kênh thế giới", "cmd": "/post "},
    {"name": "Chuyển rương cá nhân 0", "cmd": "/ware 0"},
    {"name": "Chuyển rương cá nhân 1", "cmd": "/ware 1"},
    {"name": "Chuyển rương cá nhân 2", "cmd": "/ware 2"},
]


def default_commands_store() -> dict:
    return {
        "commands": [dict(p) for p in DEFAULT_COMMAND_PRESETS],
        "last_command": "/re auto",
        "delay_after_enter": 0.10,
        "delay_after_type": 0.05,
        "delay_between_windows": 0.15,
        "type_method": "paste",  # "paste" | "type"
        "target_mode": "all",   # "all" | "selected_monitors"
        "loop_enabled": False,
        "loop_interval": 60.0,
    }


def load_commands_store() -> dict:
    if os.path.isfile(COMMANDS_FILE):
        try:
            with open(COMMANDS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    base = default_commands_store()
                    base.update(data)
                    if not isinstance(base.get("commands"), list):
                        base["commands"] = [dict(p) for p in DEFAULT_COMMAND_PRESETS]
                    return base
        except Exception:
            pass
    return default_commands_store()


def save_commands_store(store: dict):
    try:
        with open(COMMANDS_FILE, "w", encoding="utf-8") as f:
            json.dump(store, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def find_default_megamu_path() -> str:
    saved = (load_app_settings().get("megamu_path") or "").strip()
    if saved and os.path.isfile(saved):
        return saved
    localappdata = os.environ.get("LOCALAPPDATA", "")
    if localappdata:
        p = os.path.join(localappdata, "Programs", "MEGAMU", "MEGAMU.exe")
        if os.path.isfile(p):
            return p
    candidates = [
        r"C:\Users\donpv\AppData\Local\Programs\MEGAMU\MEGAMU.exe",
        r"C:\Program Files\MEGAMU\MEGAMU.exe",
        r"C:\Program Files (x86)\MEGAMU\MEGAMU.exe",
        r"D:\MEGAMU\MEGAMU.exe",
        r"E:\MEGAMU\MEGAMU.exe",
        r"D:\Games\MEGAMU\MEGAMU.exe",
        r"E:\Games\MEGAMU\MEGAMU.exe",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    if localappdata:
        return os.path.join(localappdata, "Programs", "MEGAMU", "MEGAMU.exe")
    return r"C:\MEGAMU\MEGAMU.exe"


def get_megamu_dir(megamu_path: str | None = None) -> str:
    p = megamu_path or find_default_megamu_path()
    if p:
        d = os.path.dirname(os.path.abspath(p))
        if d:
            return d
    return r"C:\MEGAMU"


def get_dashboard_path(megamu_path: str | None = None) -> str:
    return os.path.join(get_megamu_dir(megamu_path), "Dashboard.exe")


def get_megamu_config_ini(megamu_path: str | None = None) -> str:
    return os.path.join(get_megamu_dir(megamu_path), "config.ini")


MEGAMU_PATH = find_default_megamu_path()
MEGAMU_DIR = get_megamu_dir(MEGAMU_PATH)
DASHBOARD_PATH = get_dashboard_path(MEGAMU_PATH)
MEGAMU_CONFIG_INI = get_megamu_config_ini(MEGAMU_PATH)

# Unity PlayerPrefs: danh sách account đã đăng nhập
REG_MEGAMU = (winreg.HKEY_CURRENT_USER, r"Software\MEGAMU\MEGAMU")
REG_ACCOUNT_LIST = "AccountList_h1682150822"
REG_SETTINGS = "Settings_h649772672"

POINT_KEYS = ("account", "password", "login")
POINT_LABELS = {
    "account": "Ô tài khoản",
    "password": "Ô mật khẩu",
    "login": "Nút Đăng nhập",
}

# Preset layouts: name -> (count, cols)
LAYOUT_PRESETS = {
    "2x2": (4, 2),
    "3x2": (6, 3),
    "4x2": (8, 4),
    "3x3": (9, 3),
    "4x3": (12, 4),
    "4x4": (16, 4),
    "5x3": (15, 5),
}

# Cấu hình Zen
ZEN_PER_CLICK = 10_000_000        # Trừ 10.000.000 Zen / 1 lần click
ZEN_WARN_THRESHOLD = 200_000_000  # Cảnh báo khi dưới 200.000.000 Zen

EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("union", INPUT_UNION)]


class MONITORINFOEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
        ("szDevice", wintypes.WCHAR * 32),
    ]


EnumDisplayMonitorsProc = ctypes.WINFUNCTYPE(
    ctypes.c_bool,
    wintypes.HANDLE,
    wintypes.HDC,
    ctypes.POINTER(wintypes.RECT),
    wintypes.LPARAM,
)
user32.EnumDisplayMonitors.argtypes = [
    wintypes.HDC,
    ctypes.POINTER(wintypes.RECT),
    EnumDisplayMonitorsProc,
    wintypes.LPARAM,
]
user32.EnumDisplayMonitors.restype = wintypes.BOOL
user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MONITORINFOEXW)]
user32.GetMonitorInfoW.restype = wintypes.BOOL


# ---------------------------------------------------------------------------
# Window helpers
# ---------------------------------------------------------------------------
def get_screen_size():
    return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


def get_virtual_screen_bounds():
    """Tọa độ desktop ảo, bao gồm cả màn hình nằm bên trái/trên màn hình chính."""
    return (
        user32.GetSystemMetrics(SM_XVIRTUALSCREEN),
        user32.GetSystemMetrics(SM_YVIRTUALSCREEN),
        user32.GetSystemMetrics(SM_CXVIRTUALSCREEN),
        user32.GetSystemMetrics(SM_CYVIRTUALSCREEN),
    )


def list_display_monitors():
    """Trả về các màn hình và work area theo đúng tọa độ Windows."""
    monitors = []

    @EnumDisplayMonitorsProc
    def callback(hmonitor, _hdc, _rect, _lparam):
        info = MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(info)
        if user32.GetMonitorInfoW(hmonitor, ctypes.byref(info)):
            mon = info.rcMonitor
            work = info.rcWork
            monitors.append(
                {
                    "device": info.szDevice,
                    "primary": bool(info.dwFlags & MONITORINFOF_PRIMARY),
                    "monitor": (mon.left, mon.top, mon.right, mon.bottom),
                    "work": (work.left, work.top, work.right, work.bottom),
                }
            )
        return True

    user32.EnumDisplayMonitors(None, None, callback, 0)
    # Thứ tự trực quan giúp việc phân bổ cửa sổ luôn ổn định.
    monitors.sort(key=lambda m: (m["monitor"][1], m["monitor"][0], m["device"]))
    return monitors


def monitor_label(monitor):
    left, top, right, bottom = monitor["monitor"]
    primary = " (Chính)" if monitor["primary"] else ""
    return (
        f"{monitor['device']}{primary} — {right - left}x{bottom - top} "
        f"tại ({left}, {top})"
    )


def enable_per_monitor_dpi_awareness():
    """Giữ tọa độ cửa sổ/click đúng trên màn hình có DPI scale khác nhau."""
    try:
        # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 (Windows 10 1703+)
        if user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return
    except (AttributeError, OSError):
        pass
    try:
        shcore = ctypes.windll.shcore
        # PROCESS_PER_MONITOR_DPI_AWARE
        if shcore.SetProcessDpiAwareness(2) == 0:
            return
    except (AttributeError, OSError):
        pass
    try:
        user32.SetProcessDPIAware()
    except (AttributeError, OSError):
        pass


def get_window_text(hwnd):
    buf = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, buf, 512)
    return buf.value


def get_class_name(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def get_window_rect(hwnd):
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top


def get_client_size(hwnd):
    rect = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rect))
    return rect.right - rect.left, rect.bottom - rect.top


def get_pid(hwnd):
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def screen_to_client(hwnd, x, y):
    pt = POINT(int(x), int(y))
    user32.ScreenToClient(hwnd, ctypes.byref(pt))
    return pt.x, pt.y


def client_to_screen(hwnd, x, y):
    pt = POINT(int(x), int(y))
    user32.ClientToScreen(hwnd, ctypes.byref(pt))
    return pt.x, pt.y


def is_game_window(hwnd):
    if not user32.IsWindowVisible(hwnd):
        return False
    if get_class_name(hwnd) != UNITY_CLASS:
        return False
    title = get_window_text(hwnd).strip()
    if not title:
        return False
    upper = title.upper()
    return (
        "MEGAMU" in upper
        or "MU ONLINE" in upper
        or title == "Mu Online"
        or upper.startswith("MU")
    )


def parse_game_window_title(title: str) -> dict:
    """
    Phân tích tiêu đề cửa sổ game MEGAMU:
    Ví dụ: 'Cursor (800/190rr) - MEGAMU Sv1' -> Name: Cursor, Level: 800, Reset: 190, Server: MEGAMU Sv1
    """
    t = (title or "").strip()
    if not t:
        return {
            "char_name": "",
            "level": None,
            "reset": None,
            "server": "",
            "display": "",
            "is_in_game": False,
        }

    # Pattern 1: Name (level/reset) - Server
    m = re.match(r"^(.+?)\s*\(\s*(\d+)\s*/\s*(\d+)\s*(?:rr|RR)?\s*\)\s*-\s*(.+)$", t)
    if m:
        name, lvl, rr, srv = m.groups()
        return {
            "char_name": name.strip(),
            "level": int(lvl),
            "reset": int(rr),
            "server": srv.strip(),
            "display": f"{name.strip()} ({lvl}/{rr}rr)",
            "is_in_game": True,
        }

    # Pattern 2: Name (level/reset) không có server
    m2 = re.match(r"^(.+?)\s*\(\s*(\d+)\s*/\s*(\d+)\s*(?:rr|RR)?\s*\)$", t)
    if m2:
        name, lvl, rr = m2.groups()
        return {
            "char_name": name.strip(),
            "level": int(lvl),
            "reset": int(rr),
            "server": "",
            "display": f"{name.strip()} ({lvl}/{rr}rr)",
            "is_in_game": True,
        }

    # Pattern 3: Name - MEGAMU Server
    m3 = re.match(r"^(.+?)\s*-\s*(MEGAMU.*)$", t, re.IGNORECASE)
    if m3 and not m3.group(1).upper().startswith("MEGAMU"):
        return {
            "char_name": m3.group(1).strip(),
            "level": None,
            "reset": None,
            "server": m3.group(2).strip(),
            "display": m3.group(1).strip(),
            "is_in_game": True,
        }

    return {
        "char_name": "",
        "level": None,
        "reset": None,
        "server": "",
        "display": "",
        "is_in_game": False,
    }


def list_game_hwnds():
    hwnds = []

    def callback(hwnd, _):
        if is_game_window(hwnd):
            hwnds.append(hwnd)
        return True

    user32.EnumWindows(EnumWindowsProc(callback), 0)

    def sort_key(h):
        x, y, _, _ = get_window_rect(h)
        return (y // 50, x, get_pid(h))

    hwnds.sort(key=sort_key)
    return hwnds


def window_at_point(x, y):
    hwnd = user32.WindowFromPoint(POINT(int(x), int(y)))
    while hwnd:
        if is_game_window(hwnd):
            return hwnd
        parent = user32.GetParent(hwnd)
        if not parent:
            root = user32.GetAncestor(hwnd, 2)
            if root and is_game_window(root):
                return root
            break
        hwnd = parent
    for h in list_game_hwnds():
        l, t, w, ht = get_window_rect(h)
        if l <= x < l + w and t <= y < t + ht:
            return h
    return None


def restore_window(hwnd):
    style = user32.GetWindowLongW(hwnd, GWL_STYLE)
    if style & WS_MAXIMIZE:
        user32.ShowWindow(hwnd, SW_RESTORE)
        time.sleep(0.05)
    user32.ShowWindow(hwnd, SW_RESTORE)


def move_window(hwnd, x, y, w, h, activate=False):
    restore_window(hwnd)
    flags = SWP_SHOWWINDOW | SWP_FRAMECHANGED | SWP_NOZORDER
    if not activate:
        flags |= SWP_NOACTIVATE
    user32.SetWindowPos(hwnd, HWND_TOP, int(x), int(y), int(w), int(h), flags)
    time.sleep(0.05)
    user32.SetWindowPos(hwnd, HWND_TOP, int(x), int(y), int(w), int(h), flags)


def verify_position(hwnd, x, y, w, h, tol=8):
    cx, cy, cw, ch = get_window_rect(hwnd)
    return (
        abs(cx - x) <= tol
        and abs(cy - y) <= tol
        and abs(cw - w) <= tol * 2
        and abs(ch - h) <= tol * 2
    )


def arrange_hwnds(hwnds, rects, retries=4, retry_delay=0.6):
    if not hwnds:
        return 0
    placed = 0
    for _ in range(retries):
        placed = 0
        for i, hwnd in enumerate(hwnds):
            if i >= len(rects) or not user32.IsWindow(hwnd):
                continue
            x, y, w, h = rects[i]
            move_window(hwnd, x, y, w, h)
            if verify_position(hwnd, x, y, w, h):
                placed += 1
        if placed >= min(len(hwnds), len(rects)):
            break
        time.sleep(retry_delay)
    return placed


def calc_grid(count, cols_override=None):
    if count <= 0:
        return 0, 0
    cols = cols_override if cols_override and cols_override > 0 else math.ceil(math.sqrt(count))
    rows = math.ceil(count / cols)
    return cols, rows


def layout_name(count, cols):
    cols = cols if cols and cols > 0 else math.ceil(math.sqrt(count))
    rows = math.ceil(count / cols)
    return f"{cols}x{rows}"


def focus_window(hwnd):
    """Ép foreground — dùng nhiều thủ thuật vì Windows chặn SetForegroundWindow."""
    if not hwnd or not user32.IsWindow(hwnd):
        return False
    restore_window(hwnd)
    if user32.GetForegroundWindow() == hwnd:
        return True

    pid = get_pid(hwnd)
    try:
        # Cho phép process đích set foreground
        user32.AllowSetForegroundWindow(pid)
    except Exception:
        pass
    try:
        user32.AllowSetForegroundWindow(-1)  # ASFW_ANY
    except Exception:
        pass

    fg = user32.GetForegroundWindow()
    fg_tid = user32.GetWindowThreadProcessId(fg, None) if fg else 0
    cur_tid = kernel32.GetCurrentThreadId()
    target_tid = user32.GetWindowThreadProcessId(hwnd, None)

    attached_fg = False
    attached_tg = False
    try:
        if fg_tid:
            attached_fg = bool(user32.AttachThreadInput(cur_tid, fg_tid, True))
        attached_tg = bool(user32.AttachThreadInput(cur_tid, target_tid, True))

        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.BringWindowToTop(hwnd)
        try:
            user32.SwitchToThisWindow(hwnd, True)
        except Exception:
            pass

        # Nhấn/nhả Alt để phá foreground lock
        extra = ctypes.pointer(ctypes.c_ulong(0))
        scan_alt = user32.MapVirtualKeyW(VK_MENU, 0) & 0xFF
        down = INPUT(
            type=INPUT_KEYBOARD,
            union=INPUT_UNION(ki=KEYBDINPUT(0, scan_alt, KEYEVENTF_SCANCODE, 0, extra)),
        )
        up = INPUT(
            type=INPUT_KEYBOARD,
            union=INPUT_UNION(
                ki=KEYBDINPUT(0, scan_alt, KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP, 0, extra)
            ),
        )
        _send_input(down, up)

        user32.SetForegroundWindow(hwnd)
        try:
            user32.SetActiveWindow(hwnd)
        except Exception:
            pass
        try:
            user32.BringWindowToTop(hwnd)
        except Exception:
            pass
    finally:
        if attached_tg:
            user32.AttachThreadInput(cur_tid, target_tid, False)
        if attached_fg and fg_tid:
            user32.AttachThreadInput(cur_tid, fg_tid, False)

    # Nếu vẫn chưa được: minimize rồi restore
    if user32.GetForegroundWindow() != hwnd:
        user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE
        time.sleep(0.12)
        user32.ShowWindow(hwnd, SW_RESTORE)
        time.sleep(0.12)
        user32.SetForegroundWindow(hwnd)

    time.sleep(0.15)
    return user32.GetForegroundWindow() == hwnd


# ---------------------------------------------------------------------------
# Input helpers (Unity-friendly: scancode + clipboard paste)
# ---------------------------------------------------------------------------
def _send_input(*inputs):
    n = len(inputs)
    arr = (INPUT * n)(*inputs)
    return user32.SendInput(n, ctypes.byref(arr), ctypes.sizeof(INPUT)) == n


def mouse_click_screen(x, y, settle=0.12, hwnd=None):
    """Click thật bằng SetCursorPos + SendInput (Unity cần input thật, không dùng PostMessage)."""
    x, y = int(x), int(y)
    if hwnd and user32.IsWindow(hwnd) and user32.GetForegroundWindow() != hwnd:
        focus_window(hwnd)
        time.sleep(0.05)
    user32.SetCursorPos(x, y)
    time.sleep(settle)
    vx, vy, vw, vh = get_virtual_screen_bounds()
    abs_x = int((x - vx) * 65535 / max(vw - 1, 1))
    abs_y = int((y - vy) * 65535 / max(vh - 1, 1))
    abs_x = max(0, min(65535, abs_x))
    abs_y = max(0, min(65535, abs_y))
    extra = ctypes.pointer(ctypes.c_ulong(0))
    move = INPUT(
        type=INPUT_MOUSE,
        union=INPUT_UNION(
            mi=MOUSEINPUT(
                abs_x,
                abs_y,
                0,
                MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK,
                0,
                extra,
            )
        ),
    )
    down = INPUT(
        type=INPUT_MOUSE,
        union=INPUT_UNION(mi=MOUSEINPUT(0, 0, 0, MOUSEEVENTF_LEFTDOWN, 0, extra)),
    )
    up = INPUT(
        type=INPUT_MOUSE,
        union=INPUT_UNION(mi=MOUSEINPUT(0, 0, 0, MOUSEEVENTF_LEFTUP, 0, extra)),
    )
    _send_input(move)
    time.sleep(0.02)
    _send_input(down)
    time.sleep(0.04)
    _send_input(up)
    time.sleep(0.08)


def key_vk(vk, down=True):
    """
    Gửi phím bằng cả Virtual-Key + ScanCode.
    Unity (MEGAMU) bỏ qua SendInput nếu chỉ scancode (wVk=0 + KEYEVENTF_SCANCODE).
    """
    scan = user32.MapVirtualKeyW(vk, 0) & 0xFF
    flags = 0
    if vk in EXTENDED_VKS:
        flags |= KEYEVENTF_EXTENDEDKEY
    if not down:
        flags |= KEYEVENTF_KEYUP
    extra = ctypes.pointer(ctypes.c_ulong(0))
    return INPUT(
        type=INPUT_KEYBOARD,
        union=INPUT_UNION(ki=KEYBDINPUT(vk, scan, flags, 0, extra)),
    )


def key_unicode_char(ch, down=True):
    flags = KEYEVENTF_UNICODE if down else (KEYEVENTF_UNICODE | KEYEVENTF_KEYUP)
    extra = ctypes.pointer(ctypes.c_ulong(0))
    return INPUT(
        type=INPUT_KEYBOARD,
        union=INPUT_UNION(ki=KEYBDINPUT(0, ord(ch), flags, 0, extra)),
    )


def tap_vk(vk, pause=0.05):
    _send_input(key_vk(vk, True), key_vk(vk, False))
    time.sleep(pause)


def hotkey(vk_mod, vk_key, pause=0.08):
    _send_input(
        key_vk(vk_mod, True),
        key_vk(vk_key, True),
        key_vk(vk_key, False),
        key_vk(vk_mod, False),
    )
    time.sleep(pause)


def _vk_and_shift_for_char(ch):
    """Trả (vk, need_shift) cho ký tự ASCII thường dùng trong user/pass."""
    if "a" <= ch <= "z":
        return ord(ch.upper()), False
    if "A" <= ch <= "Z":
        return ord(ch), True
    if "0" <= ch <= "9":
        return ord(ch), False
    shifted = {
        "!": "1",
        "@": "2",
        "#": "3",
        "$": "4",
        "%": "5",
        "^": "6",
        "&": "7",
        "*": "8",
        "(": "9",
        ")": "0",
        "_": "-",
        "+": "=",
        "{": "[",
        "}": "]",
        "|": "\\",
        ":": ";",
        '"': "'",
        "<": ",",
        ">": ".",
        "?": "/",
        "~": "`",
    }
    unshifted = {
        "-": 0xBD,
        "=": 0xBB,
        "[": 0xDB,
        "]": 0xDD,
        "\\": 0xDC,
        ";": 0xBA,
        "'": 0xDE,
        ",": 0xBC,
        ".": 0xBE,
        "/": 0xBF,
        "`": 0xC0,
        " ": 0x20,
    }
    if ch in shifted:
        base = shifted[ch]
        if "0" <= base <= "9":
            return ord(base), True
        return unshifted[base], True
    if ch in unshifted:
        return unshifted[ch], False
    return None, False


def type_text_scancode(text, per_char=0.03):
    """Gõ bằng virtual-key + scancode (Unity thường nhận cách này)."""
    for ch in text:
        if ch == "\n":
            tap_vk(VK_RETURN, per_char)
            continue
        vk, need_shift = _vk_and_shift_for_char(ch)
        if vk is None:
            # fallback unicode cho ký tự lạ
            _send_input(key_unicode_char(ch, True), key_unicode_char(ch, False))
            time.sleep(per_char)
            continue
        if need_shift:
            _send_input(key_vk(VK_SHIFT, True), key_vk(vk, True), key_vk(vk, False), key_vk(VK_SHIFT, False))
        else:
            _send_input(key_vk(vk, True), key_vk(vk, False))
        time.sleep(per_char)


def type_text_wm_char(hwnd, text, per_char=0.01):
    for ch in text:
        user32.PostMessageW(hwnd, WM_CHAR, ord(ch), 0)
        time.sleep(per_char)


def clipboard_set_text(text):
    """Đặt Unicode text vào clipboard; trả text cũ (nếu đọc được)."""
    old = None
    if not user32.OpenClipboard(None):
        time.sleep(0.05)
        if not user32.OpenClipboard(None):
            raise RuntimeError("Không mở được clipboard")
    try:
        if user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
            handle = user32.GetClipboardData(CF_UNICODETEXT)
            if handle:
                ptr = kernel32.GlobalLock(handle)
                if ptr:
                    try:
                        old = ctypes.wstring_at(ptr)
                    finally:
                        kernel32.GlobalUnlock(handle)
        user32.EmptyClipboard()
        data = text + "\0"
        nbytes = len(data) * 2
        h = kernel32.GlobalAlloc(GMEM_MOVEABLE, nbytes)
        if not h:
            raise RuntimeError("GlobalAlloc failed")
        p = kernel32.GlobalLock(h)
        ctypes.memmove(p, ctypes.create_unicode_buffer(data), nbytes)
        kernel32.GlobalUnlock(h)
        if not user32.SetClipboardData(CF_UNICODETEXT, h):
            raise RuntimeError("SetClipboardData failed")
    finally:
        user32.CloseClipboard()
    return old


def clipboard_get_text():
    if not user32.OpenClipboard(None):
        return None
    try:
        if not user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
            return None
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return None
        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            return None
        try:
            return ctypes.wstring_at(ptr)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def paste_text(text, settle=0.08):
    """Cách chính cho Unity: copy → Ctrl+V."""
    old = None
    try:
        old = clipboard_set_text(text)
    except Exception:
        # nếu set clipboard lỗi vẫn thử type
        type_text_scancode(text)
        return
    time.sleep(settle)
    hotkey(VK_CONTROL, VK_V, pause=0.1)
    time.sleep(0.05)
    # khôi phục clipboard cũ (best-effort)
    if old is not None:
        try:
            clipboard_set_text(old)
        except Exception:
            pass


def release_modifiers():
    """Nhả Ctrl/Shift/Alt phòng bị kẹt sau hotkey — nếu kẹt thì gõ không ra chữ."""
    for vk in (VK_CONTROL, VK_SHIFT, VK_MENU):
        _send_input(key_vk(vk, False))
    time.sleep(0.02)


def clear_field():
    """Xóa ô: Ctrl+A rồi Backspace, luôn nhả modifier sau đó."""
    release_modifiers()
    hotkey(VK_CONTROL, VK_A, pause=0.1)
    release_modifiers()
    time.sleep(0.05)
    tap_vk(VK_BACK, pause=0.06)
    # thêm vài backspace phòng select-all thất bại
    for _ in range(12):
        tap_vk(VK_BACK, pause=0.01)
    release_modifiers()


def fill_field(hwnd, text, mode="type", per_char=0.03, do_clear=True):
    """
    mode:
      - paste: clipboard + Ctrl+V
      - type: gõ phím VK+scancode (khuyên dùng cho MEGAMU)
    """
    release_modifiers()
    if do_clear:
        clear_field()
        time.sleep(0.08)
        release_modifiers()
    if mode == "paste":
        paste_text(text)
        time.sleep(0.08)
    else:
        type_text_scancode(text, per_char)
    release_modifiers()
    time.sleep(0.05)


# ---------------------------------------------------------------------------
# Config persistence — layout profiles
# ---------------------------------------------------------------------------
def empty_slot():
    return {"account": None, "password": None, "login": None}


def empty_layout(count, cols):
    cols = cols if cols and cols > 0 else math.ceil(math.sqrt(count))
    rows = math.ceil(count / cols)
    name = f"{cols}x{rows}"
    return {
        "name": name,
        "count": count,
        "cols": cols,
        "rows": rows,
        "slots": [empty_slot() for _ in range(count)],
    }


def default_coords_store():
    layouts = {}
    for name, (count, cols) in LAYOUT_PRESETS.items():
        layouts[name] = empty_layout(count, cols)
    return {
        "version": 2,
        "active_layout": "2x2",
        "layouts": layouts,
        # Màn hình được chọn để xếp cửa sổ; rỗng = tự chọn màn hình chính.
        "selected_monitor_devices": [],
    }


def parse_zen(val) -> int:
    """Chuyển đổi chuỗi/số thành số nguyên Zen. Hỗ trợ: 1000000, 1.000.000, 1,000,000, 500M, 1.5B, 2B..."""
    if val is None or val == "":
        return 0
    if isinstance(val, (int, float)):
        return max(0, int(val))
    s = str(val).strip().lower().replace(" ", "")
    if not s:
        return 0
    multiplier = 1
    if s.endswith("k"):
        multiplier = 1_000
        s = s[:-1]
    elif s.endswith("m") or s.endswith("tr"):
        multiplier = 1_000_000
        s = s.rstrip("mtr")
    elif s.endswith("b") or s.endswith("t") or s.endswith("ty") or s.endswith("tỷ"):
        multiplier = 1_000_000_000
        s = s.rstrip("btyỷ")

    if multiplier > 1:
        s = s.replace(",", ".")
    else:
        s = s.replace(",", "").replace(".", "")

    try:
        return max(0, int(float(s) * multiplier))
    except Exception:
        return 0


def format_zen(val: int) -> str:
    """Format số Zen có phân cách chấm (ví dụ: 1.000.000.000)."""
    try:
        n = int(val)
        return f"{n:,}".replace(",", ".")
    except Exception:
        return "0"


def load_json(path, default):
    try:
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


DEFAULT_ACCOUNT_GROUPS = ["Chơi game", "Moss"]


def default_account_store():
    return {
        "version": 2,
        "active_group": "Chơi game",
        "groups": {
            "Chơi game": [],
            "Moss": [],
        },
    }


def load_account_store():
    raw = load_json(ACCOUNTS_FILE, None)
    if raw is None:
        store = default_account_store()
        save_json(ACCOUNTS_FILE, store)
        return store

    if isinstance(raw, dict) and "groups" in raw and isinstance(raw["groups"], dict):
        store = raw
        if "active_group" not in store or not store["active_group"]:
            store["active_group"] = (
                list(store["groups"].keys())[0] if store["groups"] else "Chơi game"
            )
        # Đảm bảo các group mặc định luôn có
        for g in DEFAULT_ACCOUNT_GROUPS:
            if g not in store["groups"]:
                store["groups"][g] = []
        # Chuyển đổi / kiểm tra zen
        for g_name, acc_list in store["groups"].items():
            if isinstance(acc_list, list):
                for acc in acc_list:
                    if isinstance(acc, dict):
                        acc["zen"] = parse_zen(acc.get("zen", 0))
        return store

    # Bản cũ: {"accounts": [...]} hoặc list [...]
    store = default_account_store()
    old_list = []
    if isinstance(raw, dict) and "accounts" in raw and isinstance(raw["accounts"], list):
        old_list = raw["accounts"]
    elif isinstance(raw, list):
        old_list = raw

    for acc in old_list:
        if isinstance(acc, dict):
            acc["zen"] = parse_zen(acc.get("zen", 0))

    store["groups"]["Chơi game"] = old_list
    store["active_group"] = "Chơi game"
    save_json(ACCOUNTS_FILE, store)
    return store


def save_account_store(store):
    save_json(ACCOUNTS_FILE, store)


def load_accounts(group=None):
    store = load_account_store()
    g = group or store.get("active_group") or "Chơi game"
    return store.get("groups", {}).get(g, [])


def save_accounts(accounts, group=None):
    store = load_account_store()
    g = group or store.get("active_group") or "Chơi game"
    if "groups" not in store:
        store["groups"] = {}
    store["groups"][g] = accounts
    store["active_group"] = g
    save_account_store(store)


def _is_legacy_coords(data):
    """File cũ: {account, password, login} không có version/layouts."""
    if not isinstance(data, dict):
        return False
    if data.get("version") == 2 and "layouts" in data:
        return False
    return any(k in data for k in POINT_KEYS)


def load_coords_store():
    raw = load_json(COORDS_FILE, None)
    if raw is None:
        store = default_coords_store()
        save_json(COORDS_FILE, store)
        return store

    # Migrate legacy flat coords -> slot 0 of 2x2
    if _is_legacy_coords(raw):
        store = default_coords_store()
        slot0 = empty_slot()
        for k in POINT_KEYS:
            if isinstance(raw.get(k), dict) and "rx" in raw[k]:
                slot0[k] = {"rx": float(raw[k]["rx"]), "ry": float(raw[k]["ry"])}
        store["layouts"]["2x2"]["slots"][0] = slot0
        store["active_layout"] = "2x2"
        # backup cũ
        try:
            save_json(COORDS_FILE + ".legacy.bak", raw)
        except Exception:
            pass
        save_json(COORDS_FILE, store)
        return store

    store = default_coords_store()
    if isinstance(raw, dict):
        store["active_layout"] = raw.get("active_layout") or "2x2"
        selected = raw.get("selected_monitor_devices", [])
        if isinstance(selected, list):
            store["selected_monitor_devices"] = [
                str(device) for device in selected if isinstance(device, str) and device
            ]
        layouts = raw.get("layouts") or {}
        for name, layout in layouts.items():
            if not isinstance(layout, dict):
                continue
            count = int(layout.get("count") or LAYOUT_PRESETS.get(name, (4, 2))[0])
            cols = int(layout.get("cols") or LAYOUT_PRESETS.get(name, (4, 2))[1])
            normalized = empty_layout(count, cols)
            normalized["name"] = layout.get("name") or name
            slots_in = layout.get("slots") or []
            for i in range(count):
                if i < len(slots_in) and isinstance(slots_in[i], dict):
                    for k in POINT_KEYS:
                        pt = slots_in[i].get(k)
                        if isinstance(pt, dict) and "rx" in pt and "ry" in pt:
                            normalized["slots"][i][k] = {
                                "rx": float(pt["rx"]),
                                "ry": float(pt["ry"]),
                            }
            store["layouts"][name] = normalized
        # đảm bảo active tồn tại
        if store["active_layout"] not in store["layouts"]:
            store["layouts"][store["active_layout"]] = empty_layout(4, 2)
    save_json(COORDS_FILE, store)
    return store


def save_coords_store(store):
    save_json(COORDS_FILE, store)


def _reg_read_binary_json(value_name):
    """Đọc Unity PlayerPrefs REG_BINARY (UTF-8 JSON + null)."""
    try:
        with winreg.OpenKey(REG_MEGAMU[0], REG_MEGAMU[1]) as key:
            data, typ = winreg.QueryValueEx(key, value_name)
    except FileNotFoundError:
        return None
    except OSError:
        return None
    if typ != winreg.REG_BINARY or not data:
        return None
    try:
        text = data.split(b"\x00")[0].decode("utf-8", errors="replace")
        return json.loads(text)
    except Exception:
        return None


def _reg_write_binary_json(value_name, obj):
    raw = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\x00"
    with winreg.CreateKey(REG_MEGAMU[0], REG_MEGAMU[1]) as key:
        winreg.SetValueEx(key, value_name, 0, winreg.REG_BINARY, raw)


def get_saved_account_usernames():
    """Danh sách username trong AccountList (registry)."""
    obj = _reg_read_binary_json(REG_ACCOUNT_LIST)
    if not isinstance(obj, dict):
        return []
    names = []
    for item in obj.get("List") or []:
        u = (item.get("Username") or item.get("Nickname") or "").strip()
        if u:
            names.append(u)
    return names


def _process_running(image_name):
    """True nếu có process image_name đang chạy (tasklist)."""
    try:
        out = subprocess.check_output(
            ["tasklist", "/FI", f"IMAGENAME eq {image_name}", "/FO", "CSV", "/NH"],
            text=True,
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except Exception:
        return False
    return image_name.lower() in out.lower()


def list_running_megamu_processes():
    """Danh sách MEGAMU.exe / Dashboard.exe đang chạy."""
    return [name for name in MEGAMU_PROCESS_NAMES if _process_running(name)]


def close_megamu_and_dashboard(wait_seconds=8.0):
    """
    Đóng hết game (MEGAMU.exe) và Dashboard.exe.
    Trả về dict: killed, still_running, waited.
    """
    before = list_running_megamu_processes()
    info = {
        "before": before,
        "killed": [],
        "still_running": [],
        "waited": 0.0,
    }
    if not before:
        return info

    for name in before:
        subprocess.run(
            ["taskkill", "/IM", name, "/F"],
            capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        info["killed"].append(name)

    deadline = time.time() + max(0.5, float(wait_seconds))
    while time.time() < deadline:
        left = list_running_megamu_processes()
        if not left:
            info["waited"] = round(wait_seconds - (deadline - time.time()), 2)
            info["still_running"] = []
            return info
        time.sleep(0.2)

    info["waited"] = float(wait_seconds)
    info["still_running"] = list_running_megamu_processes()
    return info


def open_dashboard(megamu_path: str | None = None):
    """Mở Dashboard.exe mới. Trả về True nếu spawn được."""
    dash_path = get_dashboard_path(megamu_path)
    d_dir = get_megamu_dir(megamu_path)
    if not os.path.isfile(dash_path):
        return False
    subprocess.Popen([dash_path], cwd=d_dir)
    return True


def clear_megamu_saved_accounts(
    also_clear_dashboard=True,
    clear_last_username=True,
    close_apps=False,
    reopen_dashboard=False,
    megamu_path: str | None = None,
):
    """
    Xóa danh sách account đã đăng nhập của MEGAMU.
    - (tuỳ chọn) Đóng MEGAMU.exe + Dashboard.exe trước
    - Registry AccountList → {"List":[]}
    - Settings.LastUsername / LastCharacter (tuỳ chọn)
    - config.ini accounts / accountsM của Dashboard (tuỳ chọn)
    - (tuỳ chọn) Mở lại Dashboard.exe sau khi clear
    Trả về dict thông tin đã xóa.
    """
    before = get_saved_account_usernames()
    info = {
        "before": before,
        "account_list_cleared": False,
        "settings_cleared": False,
        "dashboard_cleared": False,
        "apps_closed": False,
        "dashboard_reopened": False,
        "close_info": None,
        "error": None,
    }
    try:
        if close_apps:
            close_info = close_megamu_and_dashboard()
            info["close_info"] = close_info
            info["apps_closed"] = bool(close_info.get("killed"))
            if close_info.get("still_running"):
                info["error"] = (
                    "Không đóng hết process: " + ", ".join(close_info["still_running"])
                )
                info["after"] = get_saved_account_usernames()
                return info
            # cho file/registry kịp nhả
            time.sleep(0.35)

        # AccountList
        _reg_write_binary_json(REG_ACCOUNT_LIST, {"List": []})
        info["account_list_cleared"] = True

        if clear_last_username:
            settings = _reg_read_binary_json(REG_SETTINGS)
            if isinstance(settings, dict):
                settings["LastUsername"] = ""
                settings["LastCharacter"] = ""
                # tắt auto-select để không nhảy account cũ
                settings["AutoSelectAccount"] = False
                settings["AutoSelectCharacter"] = False
                _reg_write_binary_json(REG_SETTINGS, settings)
                info["settings_cleared"] = True

        cfg_ini = get_megamu_config_ini(megamu_path)
        if also_clear_dashboard and os.path.isfile(cfg_ini):
            try:
                with open(cfg_ini, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                if isinstance(cfg, dict):
                    cfg["accounts"] = {}
                    cfg["accountsM"] = {}
                    with open(cfg_ini, "w", encoding="utf-8") as f:
                        json.dump(cfg, f, ensure_ascii=False, separators=(",", ":"))
                    info["dashboard_cleared"] = True
            except Exception as e:
                info["error"] = f"config.ini: {e}"

        if reopen_dashboard and also_clear_dashboard and not info.get("error"):
            info["dashboard_reopened"] = open_dashboard(megamu_path)
            if not info["dashboard_reopened"]:
                info["error"] = f"Không tìm thấy Dashboard: {get_dashboard_path(megamu_path)}"
    except Exception as e:
        info["error"] = str(e)
    info["after"] = get_saved_account_usernames()
    return info


def load_autoclick_store():
    """
    File riêng cho Auto Click, với điểm click theo từng hồ sơ:
    {
      "version": 2,
      "profiles": {
        "<layout>|<màn hình>": {"points": [{"x": int, "y": int}, ...]}
      },
      "delay_between": float,
      "run_seconds": float
    }
    """
    data = load_json(AUTOCLICK_FILE, None)
    if not isinstance(data, dict):
        data = {}

    def clean_points(raw_points):
        points = []
        for pt in raw_points or []:
            if not isinstance(pt, dict):
                continue
            try:
                points.append({"x": int(pt["x"]), "y": int(pt["y"])})
            except Exception:
                continue
        return points

    profiles = {}
    for key, profile in (data.get("profiles") or {}).items():
        if not isinstance(key, str) or not isinstance(profile, dict):
            continue
        profiles[key] = {"points": clean_points(profile.get("points"))}

    # Bản cũ chỉ có một danh sách điểm. Giữ nguyên và chuyển vào hồ sơ hiện
    # tại khi người dùng lần đầu mở tab Auto Click.
    if not profiles and data.get("points"):
        profiles["__legacy__"] = {"points": clean_points(data.get("points"))}
    try:
        delay_between = float(data.get("delay_between", 0.5))
    except Exception:
        delay_between = 0.5
    try:
        run_seconds = float(data.get("run_seconds", 30.0))
    except Exception:
        run_seconds = 30.0
    return {
        "version": 2,
        "profiles": profiles,
        "delay_between": max(0.05, delay_between),
        "run_seconds": max(1.0, run_seconds),
    }


def save_autoclick_store(store):
    profiles = {}
    for key, profile in (store.get("profiles") or {}).items():
        if not isinstance(key, str) or not isinstance(profile, dict):
            continue
        profiles[key] = {
            "points": [
                {"x": int(p["x"]), "y": int(p["y"])}
                for p in (profile.get("points") or [])
                if isinstance(p, dict) and "x" in p and "y" in p
            ]
        }
    payload = {
        "version": 2,
        "profiles": profiles,
        "delay_between": float(store.get("delay_between", 0.5)),
        "run_seconds": float(store.get("run_seconds", 30.0)),
    }
    save_json(AUTOCLICK_FILE, payload)


def slot_complete(slot):
    return all(isinstance(slot.get(k), dict) for k in POINT_KEYS)


def layout_ready_count(layout):
    return sum(1 for s in layout.get("slots", []) if slot_complete(s))


# ---------------------------------------------------------------------------
# Auto login
# ---------------------------------------------------------------------------
def rel_to_screen(hwnd, rx, ry):
    cw, ch = get_client_size(hwnd)
    cx = int(rx * cw)
    cy = int(ry * ch)
    return client_to_screen(hwnd, cx, cy)


def login_one(hwnd, username, password, coords, delays, input_mode="type", click_login=True):
    """
    Luồng đã kiểm chứng với MEGAMU:
      1) Click ô Account → gõ user thẳng (KHÔNG Ctrl+A — dễ mất focus)
      2) Tab sang Password → gõ pass thẳng (KHÔNG click lại password)
      3) Click nút Login
    """
    for key in POINT_KEYS:
        if not coords.get(key):
            raise ValueError(f"Chưa ghi tọa độ: {key}")

    focus_window(hwnd)
    time.sleep(delays["focus"])

    if user32.GetForegroundWindow() != hwnd:
        focus_window(hwnd)
        time.sleep(0.15)

    release_modifiers()

    def type_into(text):
        release_modifiers()
        time.sleep(0.05)
        if input_mode == "paste":
            paste_text(text)
        elif input_mode == "paste_then_type":
            paste_text(text)
            time.sleep(0.08)
            release_modifiers()
            type_text_scancode(text, delays["per_char"])
        else:
            type_text_scancode(text, delays["per_char"])
        release_modifiers()

    # --- Account: chỉ click + gõ ---
    ax, ay = rel_to_screen(hwnd, coords["account"]["rx"], coords["account"]["ry"])
    mouse_click_screen(ax, ay, settle=max(0.15, delays.get("after_click", 0.25)), hwnd=hwnd)
    time.sleep(max(0.2, delays["after_click"]))
    type_into(username)
    time.sleep(delays["after_type"])

    # --- Password: chỉ Tab + gõ (click password làm lệch focus trên Unity) ---
    if user32.GetForegroundWindow() != hwnd:
        focus_window(hwnd)
        time.sleep(0.1)
        # nếu vừa mất focus, click lại account rồi Tab
        mouse_click_screen(ax, ay, settle=0.15, hwnd=hwnd)
        time.sleep(0.15)
        # gõ lại user nếu focus bị mất giữa chừng là rủi ro — bỏ qua, chỉ Tab
    release_modifiers()
    tap_vk(VK_TAB, pause=0.15)
    time.sleep(0.2)
    type_into(password)
    time.sleep(delays["after_type"])

    if not click_login:
        return

    if user32.GetForegroundWindow() != hwnd:
        focus_window(hwnd)
        time.sleep(0.1)

    lx, ly = rel_to_screen(hwnd, coords["login"]["rx"], coords["login"]["ry"])
    mouse_click_screen(lx, ly, settle=max(0.15, delays.get("after_click", 0.25)), hwnd=hwnd)
    time.sleep(delays["after_login"])


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------
class MegamuLauncherApp(tk.Tk):
    def __init__(self):
        super().__init__()
        lic = getattr(self, "_license_info", None) or {}
        exp = lic.get("exp")
        exp_txt = f"  |  License đến {exp}" if exp else ""
        self.title(f"MuClick {APP_VERSION} — MEGAMU Multi Launcher{exp_txt}")
        self.resizable(False, False)
        self.configure(padx=10, pady=8)

        self._busy = False
        self._capture_target = None  # point key or wizard step tuple
        self._capture_job = None
        self._wizard_queue = []  # list of (slot_index, point_key)
        self._stop_login = False
        self._ac_picking = False
        self._ac_pick_job = None
        self._ac_pick_needed = 0
        self._ac_pick_armed = False  # chờ nhả chuột trước khi nhận click mới
        self._ac_running = False
        self._stop_autoclick = False
        self._cmd_running = False
        self._stop_cmd = False
        self._license_info = lic

        self.account_store = load_account_store()
        self.account_group_var = tk.StringVar(
            value=self.account_store.get("active_group", "Chơi game")
        )
        self.auto_account_group_var = tk.StringVar(
            value=self.account_store.get("active_group", "Chơi game")
        )
        self.accounts = self.get_current_accounts()
        self.coords_store = load_coords_store()
        self.autoclick_store = load_autoclick_store()
        self.commands_store = load_commands_store()
        self.monitor_vars = {}
        self._monitors = []
        self._monitor_choices_initialized = False

        nb = ttk.Notebook(self)
        nb.grid(row=0, column=0, sticky="nsew")

        self.tab_launch = ttk.Frame(nb, padding=10)
        self.tab_accounts = ttk.Frame(nb, padding=10)
        self.tab_auto = ttk.Frame(nb, padding=10)
        self.tab_autoclick = ttk.Frame(nb, padding=10)
        self.tab_commands = ttk.Frame(nb, padding=10)
        nb.add(self.tab_launch, text="  Mở & Sắp xếp  ")
        nb.add(self.tab_accounts, text="  Tài khoản  ")
        nb.add(self.tab_auto, text="  Auto Login  ")
        nb.add(self.tab_autoclick, text="  Auto Click  ")
        nb.add(self.tab_commands, text="  Gõ lệnh  ")

        self._build_launch_tab()
        self._build_accounts_tab()
        self._build_auto_tab()
        self._build_autoclick_tab()
        self._build_commands_tab()

        # Đồng bộ layout từ store
        self._sync_launch_from_active_layout()

        status_frame = ttk.Frame(self)
        status_frame.grid(row=1, column=0, sticky="ew", pady=(8, 0))

        self.status = tk.StringVar(value="Sẵn sàng.")
        ttk.Label(status_frame, textvariable=self.status, wraplength=480).pack(
            side="left", fill="x", expand=True
        )
        ttk.Button(
            status_frame,
            text="🔑 Quản lý License",
            command=self.open_admin_license,
            width=17,
        ).pack(side="right", padx=(8, 0))

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.bind("<F8>", self._on_f8)
        self.bind("<F9>", self._on_f9)
        self.bind("<Escape>", self._on_escape)

        self._closing = False
        self._title_poll_job = self.after(1000, self._poll_game_window_titles)

    # ----- Account group helpers -----
    def get_current_group(self):
        return self.account_group_var.get() or "Chơi game"

    def get_current_accounts(self):
        g = self.get_current_group()
        groups = self.account_store.setdefault("groups", {})
        if g not in groups or not isinstance(groups[g], list):
            groups[g] = []
        return groups[g]

    def get_group_list(self):
        groups = self.account_store.setdefault("groups", {})
        for default_g in DEFAULT_ACCOUNT_GROUPS:
            if default_g not in groups:
                groups[default_g] = []
        return list(groups.keys())

    def _refresh_group_combos(self):
        groups = self.get_group_list()
        if hasattr(self, "acc_group_combo"):
            self.acc_group_combo.configure(values=groups)
        if hasattr(self, "auto_group_combo"):
            self.auto_group_combo.configure(values=groups)
        if hasattr(self, "acc_group_count_lbl"):
            cur_accs = self.get_current_accounts()
            self.acc_group_count_lbl.configure(
                text=f"({len(cur_accs)} tài khoản)"
            )
        if hasattr(self, "auto_group_info_lbl"):
            auto_g = (
                self.auto_account_group_var.get()
                if hasattr(self, "auto_account_group_var")
                else self.get_current_group()
            )
            g_accs = self.account_store.get("groups", {}).get(auto_g, [])
            self.auto_group_info_lbl.configure(
                text=f"({len(g_accs)} tài khoản)"
            )

    def _on_acc_group_selected(self, _event=None):
        g = self.account_group_var.get()
        if not g:
            return
        self.account_store["active_group"] = g
        save_account_store(self.account_store)
        self.accounts = self.get_current_accounts()
        self._refresh_group_combos()
        self._refresh_acc_tree()
        self.status.set(f"Đang chọn loại tài khoản: [{g}] ({len(self.accounts)} TK)")

    def _on_auto_group_selected(self, _event=None):
        g = self.auto_account_group_var.get()
        if not g:
            return
        self._refresh_group_combos()
        if hasattr(self, "slot_tree"):
            self._refresh_slot_ui()
        g_accs = self.account_store.get("groups", {}).get(g, [])
        self.status.set(f"Auto Login sẽ dùng danh sách: [{g}] ({len(g_accs)} TK)")

    def on_add_account_group(self):
        name = simpledialog.askstring(
            "Thêm loại tài khoản",
            "Nhập tên loại tài khoản mới (ví dụ: Moss, Chơi game, Farm Zen, Buff...):",
            parent=self,
        )
        if not name:
            return
        name = name.strip()
        if not name:
            return
        groups = self.account_store.setdefault("groups", {})
        if name in groups:
            messagebox.showinfo("Đã tồn tại", f"Loại tài khoản '{name}' đã có sẵn.", parent=self)
            self.account_group_var.set(name)
            self._on_acc_group_selected()
            return
        groups[name] = []
        self.account_group_var.set(name)
        self._on_acc_group_selected()
        self.status.set(f"Đã tạo loại tài khoản mới: '{name}'")

    def on_rename_account_group(self):
        old_name = self.get_current_group()
        new_name = simpledialog.askstring(
            "Đổi tên loại tài khoản",
            f"Nhập tên mới cho loại tài khoản '{old_name}':",
            initialvalue=old_name,
            parent=self,
        )
        if not new_name:
            return
        new_name = new_name.strip()
        if not new_name or new_name == old_name:
            return
        groups = self.account_store.setdefault("groups", {})
        if new_name in groups:
            messagebox.showwarning("Trùng tên", f"Tên '{new_name}' đã tồn tại.", parent=self)
            return
        groups[new_name] = groups.pop(old_name, [])
        self.account_store["active_group"] = new_name
        self.account_group_var.set(new_name)
        if hasattr(self, "auto_account_group_var") and self.auto_account_group_var.get() == old_name:
            self.auto_account_group_var.set(new_name)
        save_account_store(self.account_store)
        self.accounts = self.get_current_accounts()
        self._refresh_group_combos()
        self._refresh_acc_tree()
        self.status.set(f"Đã đổi tên '{old_name}' → '{new_name}'")

    def on_delete_account_group(self):
        g = self.get_current_group()
        groups = self.account_store.setdefault("groups", {})
        if len(groups) <= 1:
            messagebox.showwarning(
                "Không thể xóa", "Phải giữ lại ít nhất 1 loại tài khoản.", parent=self
            )
            return
        count = len(groups.get(g, []))
        if not messagebox.askyesno(
            "Xác nhận xóa",
            f"Bạn có chắc muốn xóa loại tài khoản '{g}'?\n"
            f"(Sẽ xóa {count} tài khoản trong danh sách này)",
            parent=self,
        ):
            return
        groups.pop(g, None)
        next_g = list(groups.keys())[0]
        self.account_store["active_group"] = next_g
        self.account_group_var.set(next_g)
        if hasattr(self, "auto_account_group_var") and self.auto_account_group_var.get() == g:
            self.auto_account_group_var.set(next_g)
        save_account_store(self.account_store)
        self.accounts = self.get_current_accounts()
        self._refresh_group_combos()
        self._refresh_acc_tree()
        self.status.set(f"Đã xóa loại tài khoản '{g}'. Chuyển sang '{next_g}'.")

    def open_admin_license(self):
        pwd = simpledialog.askstring(
            "Admin Login",
            "Nhập mật khẩu quản trị (admin):",
            show="*",
            parent=self,
        )
        if pwd is None:
            return
        if not is_admin_password(pwd):
            messagebox.showerror("Lỗi", "Mật khẩu quản trị không đúng!", parent=self)
            return
        run_admin_license_dialog(self)

    # ----- layout helpers -----
    def active_layout_name(self):
        return self.coords_store.get("active_layout", "2x2")

    def active_layout(self):
        name = self.active_layout_name()
        layouts = self.coords_store.setdefault("layouts", {})
        if name not in layouts:
            layouts[name] = empty_layout(4, 2)
        return layouts[name]

    def ensure_layout(self, name, count, cols):
        layouts = self.coords_store.setdefault("layouts", {})
        if name not in layouts or layouts[name].get("count") != count:
            # giữ slot cũ nếu cùng tên và đủ dài
            old = layouts.get(name)
            layout = empty_layout(count, cols)
            if old and isinstance(old.get("slots"), list):
                for i in range(min(count, len(old["slots"]))):
                    layout["slots"][i] = old["slots"][i]
            layouts[name] = layout
        self.coords_store["active_layout"] = name
        save_coords_store(self.coords_store)
        if hasattr(self, "ac_profile_var"):
            self._refresh_ac_profile()
        return layouts[name]

    def _sync_launch_from_active_layout(self):
        layout = self.active_layout()
        self.count_var.set(int(layout["count"]))
        self.cols_var.set(int(layout["cols"]))
        if hasattr(self, "layout_var"):
            self.layout_var.set(layout.get("name") or self.active_layout_name())
            self._refresh_slot_ui()
        if hasattr(self, "ac_profile_var"):
            self._refresh_ac_profile()

    def current_slot_index(self):
        try:
            return max(0, int(self.slot_var.get()) - 1)
        except Exception:
            return 0

    def current_slot(self):
        layout = self.active_layout()
        idx = self.current_slot_index()
        slots = layout["slots"]
        if idx >= len(slots):
            idx = 0
            self.slot_var.set(1)
        return slots[idx], idx

    # ----- monitor selection / tiling -----
    def _selected_monitors(self):
        selected_devices = {
            device for device, var in self.monitor_vars.items() if bool(var.get())
        }
        return [m for m in self._monitors if m["device"] in selected_devices]

    def _save_monitor_selection(self):
        self.coords_store["selected_monitor_devices"] = [
            m["device"] for m in self._selected_monitors()
        ]
        save_coords_store(self.coords_store)

    def _update_monitor_selection_summary(self):
        if not hasattr(self, "monitor_summary_var"):
            return
        count = len(self._selected_monitors())
        if count:
            self.monitor_summary_var.set(
                f"Đã chọn {count} màn hình. Cửa sổ sẽ được chia đều; số cột áp dụng cho từng màn hình."
            )
        else:
            self.monitor_summary_var.set("Chưa chọn màn hình nào.")

    def _on_monitor_selection_changed(self):
        self._save_monitor_selection()
        self._update_monitor_selection_summary()
        if hasattr(self, "ac_profile_var"):
            self._refresh_ac_profile()
            self.refresh_ac_window_count()

    def refresh_monitor_choices(self):
        """Nạp lại màn hình để dùng được cả khi vừa cắm/rút màn hình phụ."""
        if self._monitor_choices_initialized:
            selected_devices = {
                device for device, var in self.monitor_vars.items() if bool(var.get())
            }
        else:
            selected_devices = set(self.coords_store.get("selected_monitor_devices", []))

        self._monitors = list_display_monitors()
        if not self._monitor_choices_initialized and not selected_devices:
            selected_devices = {
                monitor["device"] for monitor in self._monitors if monitor["primary"]
            }

        for child in self.monitor_choices.winfo_children():
            child.destroy()
        self.monitor_vars = {}
        for row, monitor in enumerate(self._monitors):
            device = monitor["device"]
            var = tk.BooleanVar(value=device in selected_devices)
            self.monitor_vars[device] = var
            ttk.Checkbutton(
                self.monitor_choices,
                text=monitor_label(monitor),
                variable=var,
                command=self._on_monitor_selection_changed,
            ).grid(row=row, column=0, sticky="w")

        self._monitor_choices_initialized = True
        self._save_monitor_selection()
        self._update_monitor_selection_summary()
        if hasattr(self, "ac_profile_var"):
            self._refresh_ac_profile()
            self.refresh_ac_window_count()

    def _grid_columns(self, count, monitors):
        try:
            requested = int(self.cols_var.get())
        except Exception:
            requested = 0
        if requested > 0:
            return requested
        per_monitor = math.ceil(count / max(1, len(monitors)))
        return max(1, math.ceil(math.sqrt(per_monitor)))

    def _tile_rects_on_monitor(self, count, monitor, cols):
        left, top, right, bottom = monitor["work"]
        rows = math.ceil(count / cols)
        ml, mt = self.margin_left.get(), self.margin_top.get()
        mr, mb = self.margin_right.get(), self.margin_bottom.get()
        gap = self.gap.get()
        usable_w = max(100, (right - left) - ml - mr - gap * max(0, cols - 1))
        usable_h = max(100, (bottom - top) - mt - mb - gap * max(0, rows - 1))
        cell_w = max(200, usable_w // cols)
        cell_h = max(150, usable_h // rows)
        return [
            (
                left + ml + (i % cols) * (cell_w + gap),
                top + mt + (i // cols) * (cell_h + gap),
                cell_w,
                cell_h,
            )
            for i in range(count)
        ], rows

    def _on_path_changed(self, *args):
        p = self.path_var.get().strip()
        if p:
            save_app_settings({"megamu_path": p})

    def browse_megamu_path(self):
        cur = self.path_var.get().strip()
        init_dir = (
            os.path.dirname(cur)
            if cur and os.path.exists(os.path.dirname(cur))
            else (os.environ.get("LOCALAPPDATA") or "")
        )
        file_path = filedialog.askopenfilename(
            title="Chọn file MEGAMU.exe hoặc Launcher",
            initialdir=init_dir or None,
            filetypes=[
                ("MEGAMU Executable", "MEGAMU.exe"),
                ("File thực thi (*.exe)", "*.exe"),
                ("Tất cả tập tin (*.*)", "*.*"),
            ],
        )
        if file_path:
            file_path = os.path.normpath(file_path)
            self.path_var.set(file_path)
            save_app_settings({"megamu_path": file_path})
            self.status.set(f"Đã chọn đường dẫn: {file_path}")

    def open_megamu_folder(self):
        p = self.path_var.get().strip()
        folder = get_megamu_dir(p)
        if os.path.isdir(folder):
            try:
                os.startfile(folder)
            except Exception as e:
                messagebox.showerror("Lỗi mở thư mục", str(e))
        else:
            messagebox.showwarning(
                "Thư mục không tồn tại", f"Không tìm thấy thư mục:\n{folder}"
            )

    # ----- Launch tab -----
    def _build_launch_tab(self):
        frm = self.tab_launch
        sw, sh = get_screen_size()

        ttk.Label(frm, text="Đường dẫn MEGAMU:", font=("", 9, "bold")).grid(
            row=0, column=0, columnspan=4, sticky="w"
        )
        path_box = ttk.Frame(frm)
        path_box.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(2, 8))

        self.path_var = tk.StringVar(value=find_default_megamu_path())
        self.path_var.trace_add("write", self._on_path_changed)

        path_entry = ttk.Entry(path_box, textvariable=self.path_var)
        path_entry.pack(side="left", fill="x", expand=True)

        ttk.Button(
            path_box,
            text="Duyệt / Chọn file...",
            command=self.browse_megamu_path,
        ).pack(side="left", padx=(6, 0))
        ttk.Button(
            path_box,
            text="Mở thư mục",
            command=self.open_megamu_folder,
        ).pack(side="left", padx=(4, 0))

        opts = ttk.LabelFrame(frm, text=" Cấu hình ", padding=8)
        opts.grid(row=2, column=0, columnspan=4, sticky="ew")

        self.count_var = tk.IntVar(value=4)
        self.cols_var = tk.IntVar(value=2)
        self.delay_var = tk.DoubleVar(value=1.5)
        self.wait_var = tk.DoubleVar(value=25.0)

        ttk.Label(opts, text="Số cửa sổ:").grid(row=0, column=0, sticky="w")
        ttk.Spinbox(opts, from_=1, to=36, textvariable=self.count_var, width=7).grid(
            row=0, column=1, padx=(6, 16)
        )
        ttk.Label(opts, text="Số cột / màn hình:").grid(row=0, column=2, sticky="w")
        ttk.Spinbox(opts, from_=0, to=12, textvariable=self.cols_var, width=7).grid(
            row=0, column=3, padx=(6, 0)
        )
        ttk.Label(opts, text="Delay mở (s):").grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Spinbox(
            opts, from_=0.0, to=10.0, increment=0.25, textvariable=self.delay_var, width=7
        ).grid(row=1, column=1, padx=(6, 16), pady=(6, 0))
        ttk.Label(opts, text="Chờ cửa sổ (s):").grid(row=1, column=2, sticky="w", pady=(6, 0))
        ttk.Spinbox(
            opts, from_=5.0, to=90.0, increment=1.0, textvariable=self.wait_var, width=7
        ).grid(row=1, column=3, padx=(6, 0), pady=(6, 0))

        monitors = ttk.LabelFrame(frm, text=" Màn hình hiển thị cửa sổ ", padding=8)
        monitors.grid(row=3, column=0, columnspan=4, sticky="ew", pady=(8, 0))
        self.monitor_choices = ttk.Frame(monitors)
        self.monitor_choices.grid(row=0, column=0, sticky="w")
        self.monitor_summary_var = tk.StringVar(value="")
        ttk.Label(monitors, textvariable=self.monitor_summary_var, foreground="#055").grid(
            row=1, column=0, sticky="w", pady=(5, 0)
        )
        ttk.Button(monitors, text="Làm mới màn hình", width=17, command=self.refresh_monitor_choices).grid(
            row=1, column=1, sticky="e", padx=(12, 0), pady=(5, 0)
        )
        self.refresh_monitor_choices()

        margin = ttk.LabelFrame(frm, text=" Lề (px) ", padding=8)
        margin.grid(row=4, column=0, columnspan=4, sticky="ew", pady=(8, 0))
        self.margin_left = tk.IntVar(value=0)
        self.margin_top = tk.IntVar(value=0)
        self.margin_right = tk.IntVar(value=0)
        self.margin_bottom = tk.IntVar(value=48)
        self.gap = tk.IntVar(value=6)
        for i, (label, var) in enumerate(
            [
                ("Trái", self.margin_left),
                ("Trên", self.margin_top),
                ("Phải", self.margin_right),
                ("Dưới", self.margin_bottom),
                ("Khe", self.gap),
            ]
        ):
            ttk.Label(margin, text=label).grid(row=0, column=i * 2)
            ttk.Spinbox(margin, from_=0, to=400, textvariable=var, width=5).grid(
                row=0, column=i * 2 + 1, padx=(2, 10)
            )

        saved = ttk.LabelFrame(frm, text=" Danh sách account đã lưu trong MEGAMU ", padding=8)
        saved.grid(row=5, column=0, columnspan=4, sticky="ew", pady=(8, 0))

        self.clear_before_launch_var = tk.BooleanVar(value=True)
        self.clear_dashboard_var = tk.BooleanVar(value=True)
        self.reopen_dashboard_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            saved,
            text="Trước khi mở: xóa danh sách account đã đăng nhập (để màn hình trắng)",
            variable=self.clear_before_launch_var,
        ).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Checkbutton(
            saved,
            text="Đồng thời xóa accounts trong Dashboard (config.ini)",
            variable=self.clear_dashboard_var,
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 0))
        ttk.Checkbutton(
            saved,
            text="Đóng hết MEGAMU + Dashboard trước khi xóa, rồi mở lại Dashboard mới",
            variable=self.reopen_dashboard_var,
        ).grid(row=2, column=0, columnspan=3, sticky="w", pady=(4, 0))

        self.saved_acc_status = tk.StringVar(value="")
        ttk.Label(saved, textvariable=self.saved_acc_status, foreground="#055").grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(6, 0)
        )
        ttk.Button(saved, text="Làm mới", width=10, command=self.refresh_saved_accounts).grid(
            row=3, column=2, sticky="e", pady=(6, 0)
        )
        ttk.Button(
            saved,
            text="Xóa danh sách ngay",
            width=18,
            command=self.on_clear_saved_accounts,
        ).grid(row=4, column=0, sticky="w", pady=(8, 0))

        btns = ttk.Frame(frm)
        btns.grid(row=6, column=0, columnspan=4, sticky="w", pady=(10, 0))
        self.btn_launch = ttk.Button(btns, text="Mở & Sắp xếp", command=self.on_launch, width=16)
        self.btn_launch.pack(side="left", padx=(0, 6))
        self.btn_arrange = ttk.Button(
            btns, text="Sắp xếp lại", command=self.on_arrange, width=14
        )
        self.btn_arrange.pack(side="left", padx=(0, 6))
        self.btn_close_all = ttk.Button(
            btns, text="Đóng tất cả MEGAMU", command=self.on_close_all, width=18
        )
        self.btn_close_all.pack(side="left")

        presets = ttk.Frame(frm)
        presets.grid(row=7, column=0, columnspan=4, sticky="w", pady=(8, 0))
        ttk.Label(presets, text="Preset:").pack(side="left")
        for label, n, c in [
            ("2x2", 4, 2),
            ("3x2", 6, 3),
            ("4x2", 8, 4),
            ("3x3", 9, 3),
            ("4x3", 12, 4),
            ("4x4", 16, 4),
            ("5x3", 15, 5),
        ]:
            ttk.Button(
                presets, text=label, width=5, command=lambda n=n, c=c: self.apply_preset(n, c)
            ).pack(side="left", padx=2)

        ttk.Label(
            frm,
            text=(
                f"Màn hình {sw}x{sh}  |  AccountList: "
                r"HKCU\Software\MEGAMU\MEGAMU"
            ),
            foreground="#555",
        ).grid(row=8, column=0, sticky="w", pady=(8, 0))

        self.refresh_saved_accounts()

    # ----- Accounts tab -----
    def _build_accounts_tab(self):
        frm = self.tab_accounts

        group_frame = ttk.LabelFrame(frm, text=" Loại / Mục đích tài khoản ", padding=8)
        group_frame.grid(row=0, column=0, columnspan=7, sticky="ew", pady=(0, 8))

        ttk.Label(group_frame, text="Loại tài khoản:", font=("", 9, "bold")).pack(
            side="left", padx=(0, 6)
        )

        self.acc_group_combo = ttk.Combobox(
            group_frame,
            textvariable=self.account_group_var,
            values=self.get_group_list(),
            state="readonly",
            width=16,
        )
        self.acc_group_combo.pack(side="left", padx=(0, 8))
        self.acc_group_combo.bind("<<ComboboxSelected>>", self._on_acc_group_selected)

        ttk.Button(
            group_frame,
            text="➕ Thêm loại...",
            command=self.on_add_account_group,
            width=13,
        ).pack(side="left", padx=(0, 4))
        ttk.Button(
            group_frame,
            text="✏️ Đổi tên...",
            command=self.on_rename_account_group,
            width=11,
        ).pack(side="left", padx=(0, 4))
        ttk.Button(
            group_frame,
            text="🗑️ Xóa loại",
            command=self.on_delete_account_group,
            width=10,
        ).pack(side="left", padx=(0, 8))

        self.acc_group_count_lbl = ttk.Label(group_frame, text="", foreground="#055")
        self.acc_group_count_lbl.pack(side="left")

        cols = ("slot", "user", "pass", "char", "zen", "status")
        self.acc_tree = ttk.Treeview(frm, columns=cols, show="headings", height=11)
        self.acc_tree.heading("slot", text="Vị trí")
        self.acc_tree.heading("user", text="Tài khoản")
        self.acc_tree.heading("pass", text="Mật khẩu")
        self.acc_tree.heading("char", text="Nhân vật (Lv/RR)")
        self.acc_tree.heading("zen", text="Zen hiện có")
        self.acc_tree.heading("status", text="Trạng thái")
        self.acc_tree.column("slot", width=55, anchor="center")
        self.acc_tree.column("user", width=125)
        self.acc_tree.column("pass", width=95)
        self.acc_tree.column("char", width=175, anchor="w")
        self.acc_tree.column("zen", width=115, anchor="e")
        self.acc_tree.column("status", width=125, anchor="center")
        self.acc_tree.tag_configure("low_zen", foreground="#c00000")
        self.acc_tree.tag_configure("online", foreground="#008800")
        self.acc_tree.tag_configure("normal", foreground="#000000")
        self.acc_tree.grid(row=1, column=0, columnspan=6, sticky="nsew")
        self.acc_tree.bind("<<TreeviewSelect>>", self._on_acc_select)

        sb = ttk.Scrollbar(frm, orient="vertical", command=self.acc_tree.yview)
        self.acc_tree.configure(yscrollcommand=sb.set)
        sb.grid(row=1, column=6, sticky="ns")

        inp_frm = ttk.Frame(frm)
        inp_frm.grid(row=2, column=0, columnspan=7, sticky="w", pady=(8, 0))

        ttk.Label(inp_frm, text="User:").pack(side="left")
        self.user_var = tk.StringVar()
        ttk.Entry(inp_frm, textvariable=self.user_var, width=15).pack(side="left", padx=(4, 8))

        ttk.Label(inp_frm, text="Pass:").pack(side="left")
        self.pass_var = tk.StringVar()
        ttk.Entry(inp_frm, textvariable=self.pass_var, width=13, show="*").pack(side="left", padx=(4, 8))

        ttk.Label(inp_frm, text="Zen:").pack(side="left")
        self.zen_var = tk.StringVar(value="0")
        ttk.Entry(inp_frm, textvariable=self.zen_var, width=15).pack(side="left", padx=(4, 6))

        ttk.Button(inp_frm, text="+500M", width=6, command=lambda: self._quick_add_zen(500_000_000)).pack(side="left", padx=2)
        ttk.Button(inp_frm, text="+1B", width=5, command=lambda: self._quick_add_zen(1_000_000_000)).pack(side="left", padx=2)
        ttk.Button(inp_frm, text="2B", width=4, command=lambda: self.zen_var.set("2.000.000.000")).pack(side="left", padx=2)

        bf = ttk.Frame(frm)
        bf.grid(row=3, column=0, columnspan=7, sticky="w", pady=(8, 0))
        ttk.Button(bf, text="Thêm", command=self.acc_add, width=10).pack(side="left", padx=(0, 6))
        ttk.Button(bf, text="Sửa dòng chọn", command=self.acc_edit, width=14).pack(
            side="left", padx=(0, 6)
        )
        ttk.Button(bf, text="Xóa dòng chọn", command=self.acc_delete, width=14).pack(
            side="left", padx=(0, 6)
        )
        ttk.Button(bf, text="Lên", command=lambda: self.acc_move(-1), width=6).pack(
            side="left", padx=(0, 4)
        )
        ttk.Button(bf, text="Xuống", command=lambda: self.acc_move(1), width=6).pack(
            side="left", padx=(0, 6)
        )
        ttk.Button(bf, text="Lưu file", command=self.acc_save, width=10).pack(side="left")

        ttk.Label(
            frm,
            text=(
                f"Lưu tại: {ACCOUNTS_FILE}\n"
                "• Mỗi loại tài khoản (Chơi game, Moss...) có danh sách tài khoản riêng biệt để Auto Login.\n"
                "• Thứ tự trên→dưới = Slot 1, Slot 2, Slot 3... tương ứng với từng điểm click trong Auto Click.\n"
                "• Tự động nhận diện Tên nhân vật, Level, Reset và Server khi cửa sổ game đang chạy.\n"
                "• Auto Click: Mỗi lần click trừ 10.000.000 Zen. Khi còn dưới 200.000.000 Zen hệ thống sẽ bật cảnh báo."
            ),
            foreground="#555",
            justify="left",
        ).grid(row=4, column=0, columnspan=7, sticky="w", pady=(10, 0))

        self._refresh_group_combos()
        self._refresh_acc_tree()

    def _quick_add_zen(self, delta):
        cur = parse_zen(self.zen_var.get())
        new_val = min(2_000_000_000, cur + delta)
        self.zen_var.set(format_zen(new_val))

    def _refresh_acc_tree(self):
        for i in self.acc_tree.get_children():
            self.acc_tree.delete(i)
        self.accounts = self.get_current_accounts()
        for idx, acc in enumerate(self.accounts):
            shown_pass = "*" * min(len(acc.get("password", "")), 12) or ""
            zen = parse_zen(acc.get("zen", 0))
            zen_txt = format_zen(zen)
            char_info = acc.get("char_display", "")
            if not char_info and acc.get("char_name"):
                lvl = acc.get("char_level", "")
                rr = acc.get("char_reset", "")
                char_info = f"{acc['char_name']} ({lvl}/{rr}rr)"
            if not char_info:
                char_info = "—"

            online_srv = acc.get("online_server", "")
            if online_srv and online_srv != "Đang mở game":
                status_txt = f"🟢 {online_srv}"
                tag = "online"
            elif online_srv == "Đang mở game":
                status_txt = "🟡 Đang mở game"
                tag = "normal"
            elif zen < ZEN_WARN_THRESHOLD:
                status_txt = "⚠️ < 200M Zen"
                tag = "low_zen"
            else:
                status_txt = "Sẵn sàng"
                tag = "normal"
            self.acc_tree.insert(
                "",
                "end",
                values=(f"Slot {idx + 1}", acc.get("username", ""), shown_pass, char_info, zen_txt, status_txt),
                tags=(tag,),
            )

    def _on_acc_select(self, _event=None):
        sel = self.acc_tree.selection()
        if not sel:
            return
        idx = self.acc_tree.index(sel[0])
        accs = self.get_current_accounts()
        if 0 <= idx < len(accs):
            self.user_var.set(accs[idx].get("username", ""))
            self.pass_var.set(accs[idx].get("password", ""))
            zen = accs[idx].get("zen", 0)
            self.zen_var.set(format_zen(zen))

    def acc_add(self):
        u = self.user_var.get().strip()
        p = self.pass_var.get()
        z = parse_zen(self.zen_var.get())
        if not u:
            messagebox.showwarning("Thiếu dữ liệu", "Nhập tài khoản.")
            return
        accs = self.get_current_accounts()
        accs.append({"username": u, "password": p, "zen": z})
        self.user_var.set("")
        self.pass_var.set("")
        self.zen_var.set("0")
        save_account_store(self.account_store)
        self._refresh_group_combos()
        self._refresh_acc_tree()
        self.status.set(f"Đã thêm tài khoản vào [{self.get_current_group()}]. Tổng: {len(accs)}")

    def acc_edit(self):
        sel = self.acc_tree.selection()
        if not sel:
            return
        idx = self.acc_tree.index(sel[0])
        u = self.user_var.get().strip()
        p = self.pass_var.get()
        z = parse_zen(self.zen_var.get())
        if not u:
            messagebox.showwarning("Thiếu dữ liệu", "Nhập tài khoản.")
            return
        accs = self.get_current_accounts()
        cur = accs[idx]
        cur.update({"username": u, "password": p, "zen": z})
        save_account_store(self.account_store)
        self._refresh_group_combos()
        self._refresh_acc_tree()
        self.status.set(f"Đã sửa tài khoản #{idx + 1} trong [{self.get_current_group()}]")

    def acc_delete(self):
        sel = self.acc_tree.selection()
        if not sel:
            return
        idx = self.acc_tree.index(sel[0])
        accs = self.get_current_accounts()
        del accs[idx]
        save_account_store(self.account_store)
        self._refresh_group_combos()
        self._refresh_acc_tree()

    def acc_move(self, delta):
        sel = self.acc_tree.selection()
        if not sel:
            return
        idx = self.acc_tree.index(sel[0])
        j = idx + delta
        accs = self.get_current_accounts()
        if j < 0 or j >= len(accs):
            return
        accs[idx], accs[j] = accs[j], accs[idx]
        save_account_store(self.account_store)
        self._refresh_acc_tree()
        kids = self.acc_tree.get_children()
        self.acc_tree.selection_set(kids[j])

    def acc_save(self):
        save_account_store(self.account_store)
        self._refresh_group_combos()
        self.status.set(f"Đã lưu {len(self.get_current_accounts())} tài khoản trong [{self.get_current_group()}].")

    # ----- Auto login tab -----
    def _build_auto_tab(self):
        frm = self.tab_auto

        top = ttk.LabelFrame(frm, text=" Hồ sơ layout & Tài khoản đăng nhập ", padding=8)
        top.grid(row=0, column=0, columnspan=4, sticky="ew")

        ttk.Label(top, text="Layout:").grid(row=0, column=0, sticky="w")
        self.layout_var = tk.StringVar(value=self.active_layout_name())
        self.layout_combo = ttk.Combobox(
            top,
            textvariable=self.layout_var,
            values=list(LAYOUT_PRESETS.keys()),
            width=10,
            state="readonly",
        )
        self.layout_combo.grid(row=0, column=1, sticky="w", padx=(6, 12))
        self.layout_combo.bind("<<ComboboxSelected>>", self._on_layout_combo)

        ttk.Button(top, text="Dùng layout đang mở/sắp", command=self.use_launch_layout, width=22).grid(
            row=0, column=2, sticky="w"
        )

        ttk.Label(top, text="Loại tài khoản:", font=("", 9, "bold")).grid(
            row=1, column=0, sticky="w", pady=(6, 0)
        )
        self.auto_group_combo = ttk.Combobox(
            top,
            textvariable=self.auto_account_group_var,
            values=self.get_group_list(),
            width=16,
            state="readonly",
        )
        self.auto_group_combo.grid(row=1, column=1, sticky="w", padx=(6, 12), pady=(6, 0))
        self.auto_group_combo.bind("<<ComboboxSelected>>", self._on_auto_group_selected)

        self.auto_group_info_lbl = ttk.Label(top, text="", foreground="#055")
        self.auto_group_info_lbl.grid(row=1, column=2, sticky="w", pady=(6, 0))

        self.layout_status = tk.StringVar(value="")
        ttk.Label(top, textvariable=self.layout_status, foreground="#055").grid(
            row=2, column=0, columnspan=4, sticky="w", pady=(6, 0)
        )

        # Slot list
        mid = ttk.LabelFrame(frm, text=" Tọa độ theo từng ô cửa sổ ", padding=8)
        mid.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(8, 0))

        self.slot_tree = ttk.Treeview(
            mid,
            columns=("slot", "status", "char", "account", "password", "login"),
            show="headings",
            height=7,
        )
        self.slot_tree.heading("slot", text="Ô")
        self.slot_tree.heading("status", text="Trạng thái")
        self.slot_tree.heading("char", text="Nhân vật / Game")
        self.slot_tree.heading("account", text="Account")
        self.slot_tree.heading("password", text="Password")
        self.slot_tree.heading("login", text="Login")
        self.slot_tree.column("slot", width=35, anchor="center")
        self.slot_tree.column("status", width=75, anchor="center")
        self.slot_tree.column("char", width=160, anchor="w")
        self.slot_tree.column("account", width=105)
        self.slot_tree.column("password", width=105)
        self.slot_tree.column("login", width=105)
        self.slot_tree.grid(row=0, column=0, columnspan=4, sticky="ew")
        self.slot_tree.bind("<<TreeviewSelect>>", self._on_slot_tree_select)

        sel = ttk.Frame(mid)
        sel.grid(row=1, column=0, columnspan=4, sticky="w", pady=(8, 0))
        ttk.Label(sel, text="Đang chỉnh ô:").pack(side="left")
        self.slot_var = tk.IntVar(value=1)
        self.slot_spin = ttk.Spinbox(
            sel,
            from_=1,
            to=4,
            textvariable=self.slot_var,
            width=5,
            command=self._on_slot_spin,
        )
        self.slot_spin.pack(side="left", padx=(6, 12))
        ttk.Button(sel, text="Làm mới danh sách", command=self._refresh_slot_ui, width=16).pack(
            side="left", padx=(0, 6)
        )

        # Capture current slot points
        cap = ttk.LabelFrame(frm, text=" Ghi tọa độ cho ô đang chọn ", padding=8)
        cap.grid(row=2, column=0, columnspan=4, sticky="ew", pady=(8, 0))

        ttk.Label(
            cap,
            text=(
                "Đưa chuột vào đúng vị trí trên ĐÚNG cửa sổ ô đó → nhấn F8.\n"
                "Hoặc dùng 'Ghi lần lượt cả layout' để đi hết ô 1→N."
            ),
            justify="left",
        ).grid(row=0, column=0, columnspan=4, sticky="w")

        self.coord_labels = {}
        row = 1
        for key, title in POINT_LABELS.items():
            ttk.Label(cap, text=title + ":", width=16).grid(row=row, column=0, sticky="w", pady=3)
            lbl = ttk.Label(cap, text="(chưa ghi)", width=34)
            lbl.grid(row=row, column=1, sticky="w")
            self.coord_labels[key] = lbl
            ttk.Button(
                cap, text="Ghi (F8)", width=10, command=lambda k=key: self.start_capture(k)
            ).grid(row=row, column=2, padx=(8, 0))
            row += 1

        actions = ttk.Frame(cap)
        actions.grid(row=row, column=0, columnspan=4, sticky="w", pady=(8, 0))
        ttk.Button(
            actions, text="Ghi lần lượt cả layout (F8)", command=self.start_wizard, width=26
        ).pack(side="left", padx=(0, 6))
        ttk.Button(
            actions, text="Chép ô 1 → tất cả ô", command=self.copy_slot0_to_all, width=18
        ).pack(side="left", padx=(0, 6))
        ttk.Button(
            actions, text="Xóa ô đang chọn", command=self.clear_current_slot, width=16
        ).pack(side="left", padx=(0, 6))
        ttk.Button(
            actions, text="Xóa cả layout", command=self.clear_layout_coords, width=14
        ).pack(side="left")

        opts = ttk.LabelFrame(frm, text=" Tùy chọn auto login ", padding=8)
        opts.grid(row=3, column=0, columnspan=4, sticky="ew", pady=(8, 0))

        self.login_delay_var = tk.DoubleVar(value=1.5)
        self.after_click_var = tk.DoubleVar(value=0.35)
        self.after_type_var = tk.DoubleVar(value=0.25)
        self.per_char_var = tk.DoubleVar(value=0.04)
        self.after_login_var = tk.DoubleVar(value=0.8)
        self.between_win_var = tk.DoubleVar(value=1.5)
        self.input_mode_var = tk.StringVar(value="type")

        ttk.Label(opts, text="Cách nhập:").grid(row=0, column=0, sticky="w", pady=3)
        ttk.Combobox(
            opts,
            textvariable=self.input_mode_var,
            values=["type", "paste", "paste_then_type"],
            width=16,
            state="readonly",
        ).grid(row=0, column=1, sticky="w", padx=(0, 12), pady=3)
        ttk.Label(
            opts,
            text="type = gõ phím (khuyên dùng cho MEGAMU) | paste = Ctrl+V | paste_then_type = cả hai",
            foreground="#555",
        ).grid(row=0, column=2, columnspan=4, sticky="w")

        fields = [
            ("Delay giữa cửa sổ (s)", self.between_win_var),
            ("Sau khi focus (s)", self.login_delay_var),
            ("Sau mỗi click (s)", self.after_click_var),
            ("Sau khi gõ (s)", self.after_type_var),
            ("Mỗi ký tự (s)", self.per_char_var),
            ("Sau nút Login (s)", self.after_login_var),
        ]
        for i, (label, var) in enumerate(fields):
            r, c = divmod(i, 3)
            r += 1
            ttk.Label(opts, text=label).grid(row=r, column=c * 2, sticky="w", padx=(0, 4), pady=3)
            ttk.Spinbox(
                opts, from_=0.0, to=10.0, increment=0.05, textvariable=var, width=7
            ).grid(row=r, column=c * 2 + 1, sticky="w", padx=(0, 12), pady=3)

        btns = ttk.Frame(frm)
        btns.grid(row=4, column=0, columnspan=4, sticky="w", pady=(10, 0))
        self.btn_auto = ttk.Button(
            btns, text="Chạy Auto Login", command=self.on_auto_login, width=18
        )
        self.btn_auto.pack(side="left", padx=(0, 8))
        self.btn_stop = ttk.Button(
            btns, text="Dừng", command=self.on_stop_login, width=10, state="disabled"
        )
        self.btn_stop.pack(side="left", padx=(0, 8))
        ttk.Button(btns, text="Thử ô đang chọn", command=self.on_test_one, width=16).pack(
            side="left"
        )

        ttk.Label(
            frm,
            text=(
                "Account theo thứ tự danh sách (trên→dưới): ô 1←TK1, ô 2←TK2, ...\n"
                "Chỉ login các ô trong layout đang có cửa sổ. Dòng account dư sẽ được bỏ qua."
            ),
            foreground="#555",
            justify="left",
        ).grid(row=5, column=0, columnspan=4, sticky="w", pady=(8, 0))

        self._refresh_slot_ui()

    def _fmt_pt(self, pt):
        if not isinstance(pt, dict):
            return "—"
        return f"{pt['rx']:.3f},{pt['ry']:.3f}"

    def _refresh_slot_ui(self):
        layout = self.active_layout()
        name = layout.get("name") or self.active_layout_name()
        ready = layout_ready_count(layout)
        total = layout["count"]
        auto_g = (
            self.auto_account_group_var.get()
            if hasattr(self, "auto_account_group_var")
            else self.get_current_group()
        )
        g_accs = self.account_store.get("groups", {}).get(auto_g, [])
        self.layout_status.set(
            f"Layout {name}: đã ghi đủ {ready}/{total} ô  |  Loại TK: [{auto_g}] ({len(g_accs)} TK)"
        )
        if hasattr(self, "auto_group_info_lbl"):
            self.auto_group_info_lbl.configure(
                text=f"({len(g_accs)} tài khoản)"
            )

        # update spin range
        self.slot_spin.configure(to=max(1, total))
        if self.slot_var.get() > total:
            self.slot_var.set(total)

        # refresh tree
        for i in self.slot_tree.get_children():
            self.slot_tree.delete(i)
        for i, slot in enumerate(layout["slots"]):
            status = "Đủ" if slot_complete(slot) else "Thiếu"
            char_disp = "—"
            if i < len(g_accs):
                acc = g_accs[i]
                char_disp = acc.get("char_display") or (
                    f"{acc['char_name']} ({acc['char_level']}/{acc['char_reset']}rr)"
                    if acc.get("char_name")
                    else (f"TK: {acc.get('username')}" if acc.get("username") else "—")
                )
            self.slot_tree.insert(
                "",
                "end",
                iid=str(i),
                values=(
                    i + 1,
                    status,
                    char_disp,
                    self._fmt_pt(slot.get("account")),
                    self._fmt_pt(slot.get("password")),
                    self._fmt_pt(slot.get("login")),
                ),
            )

        # highlight current
        idx = self.current_slot_index()
        if 0 <= idx < total:
            self.slot_tree.selection_set(str(idx))
            self.slot_tree.see(str(idx))

        # labels for current slot
        slot, _ = self.current_slot()
        for key, lbl in self.coord_labels.items():
            pt = slot.get(key)
            lbl.configure(text=self._fmt_pt(pt) if pt else "(chưa ghi)")

        # combo values may include custom
        names = sorted(set(list(LAYOUT_PRESETS.keys()) + list(self.coords_store["layouts"].keys())))
        self.layout_combo.configure(values=names)
        if name not in names:
            names.append(name)
            self.layout_combo.configure(values=names)
        self.layout_var.set(name)

    def _on_layout_combo(self, _event=None):
        name = self.layout_var.get()
        if name in LAYOUT_PRESETS:
            count, cols = LAYOUT_PRESETS[name]
            self.ensure_layout(name, count, cols)
            self.count_var.set(count)
            self.cols_var.set(cols)
        else:
            # custom existing
            self.coords_store["active_layout"] = name
            save_coords_store(self.coords_store)
            layout = self.active_layout()
            self.count_var.set(layout["count"])
            self.cols_var.set(layout["cols"])
        self.slot_var.set(1)
        self._refresh_slot_ui()
        if hasattr(self, "ac_profile_var"):
            self._refresh_ac_profile()
        self.status.set(f"Đã chọn hồ sơ layout {name}.")

    def use_launch_layout(self):
        count = int(self.count_var.get())
        cols = int(self.cols_var.get()) if int(self.cols_var.get()) > 0 else math.ceil(math.sqrt(count))
        name = layout_name(count, cols)
        self.ensure_layout(name, count, cols)
        self.layout_var.set(name)
        self.slot_var.set(1)
        self._refresh_slot_ui()
        self.status.set(f"Dùng layout từ cấu hình mở cửa sổ: {name} ({count} ô).")

    def _on_slot_spin(self):
        self._refresh_slot_ui()

    def _on_slot_tree_select(self, _event=None):
        sel = self.slot_tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        self.slot_var.set(idx + 1)
        slot, _ = self.current_slot()
        for key, lbl in self.coord_labels.items():
            pt = slot.get(key)
            lbl.configure(text=self._fmt_pt(pt) if pt else "(chưa ghi)")

    def start_capture(self, key):
        if self._busy:
            return
        self._wizard_queue = []
        self._capture_target = ("single", self.current_slot_index(), key)
        slot_no = self.current_slot_index() + 1
        self.status.set(
            f"[Ô {slot_no}] Đưa chuột vào [{POINT_LABELS[key]}] trên đúng cửa sổ đó, rồi F8 (Esc hủy)."
        )
        self._poll_capture_hint()

    def start_wizard(self):
        if self._busy:
            return
        layout = self.active_layout()
        queue = []
        for i in range(layout["count"]):
            for key in POINT_KEYS:
                queue.append((i, key))
        if not queue:
            return
        self._wizard_queue = queue
        self._begin_next_wizard_step()

    def _begin_next_wizard_step(self):
        if not self._wizard_queue:
            self._capture_target = None
            self._refresh_slot_ui()
            self.status.set("Đã ghi xong toàn bộ điểm của layout.")
            return
        slot_i, key = self._wizard_queue[0]
        self.slot_var.set(slot_i + 1)
        self._refresh_slot_ui()
        self._capture_target = ("wizard", slot_i, key)
        left = len(self._wizard_queue)
        self.status.set(
            f"Wizard: Ô {slot_i + 1}/{self.active_layout()['count']} → {POINT_LABELS[key]} "
            f"(còn {left} điểm). Đưa chuột đúng chỗ rồi F8. Esc dừng."
        )
        self._poll_capture_hint()

    def _poll_capture_hint(self):
        if not self._capture_target:
            return
        if user32.GetAsyncKeyState(VK_F8) & 0x0001:
            self._do_capture()
            return
        if user32.GetAsyncKeyState(VK_ESCAPE) & 0x0001:
            self._capture_target = None
            self._wizard_queue = []
            self.status.set("Đã hủy ghi tọa độ.")
            return
        self._capture_job = self.after(50, self._poll_capture_hint)

    def _on_f8(self, _event=None):
        if self._capture_target:
            self._do_capture()

    def _on_escape(self, _event=None):
        if getattr(self, "_cmd_running", False):
            self.on_cmd_stop()
            return
        if self._ac_running:
            self.on_ac_stop()
            return
        if self._ac_picking:
            self._cancel_ac_pick("Đã hủy chọn điểm Auto Click.")
            return
        if self._capture_target:
            self._capture_target = None
            self._wizard_queue = []
            if self._capture_job:
                self.after_cancel(self._capture_job)
                self._capture_job = None
            self.status.set("Đã hủy ghi tọa độ.")

    def _do_capture(self):
        target = self._capture_target
        self._capture_target = None
        if self._capture_job:
            try:
                self.after_cancel(self._capture_job)
            except Exception:
                pass
            self._capture_job = None
        if not target:
            return

        mode, slot_i, key = target

        pt = POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        hwnd = window_at_point(pt.x, pt.y)
        if not hwnd:
            messagebox.showwarning(
                "Không thấy cửa sổ game",
                "Đặt chuột bên trong đúng cửa sổ MEGAMU của ô đang ghi, rồi F8.",
            )
            self.status.set("Ghi thất bại — chuột không nằm trên cửa sổ game.")
            # nếu wizard, giữ bước hiện tại
            if mode == "wizard":
                self._capture_target = target
                self._poll_capture_hint()
            return

        cx, cy = screen_to_client(hwnd, pt.x, pt.y)
        cw, ch = get_client_size(hwnd)
        if cw <= 0 or ch <= 0:
            messagebox.showerror("Lỗi", "Không đọc được kích thước cửa sổ.")
            return
        rx, ry = cx / cw, cy / ch

        layout = self.active_layout()
        if slot_i < 0 or slot_i >= len(layout["slots"]):
            messagebox.showerror("Lỗi", f"Ô {slot_i + 1} không hợp lệ.")
            return

        layout["slots"][slot_i][key] = {"rx": rx, "ry": ry}
        # lưu kích thước client lúc ghi để tham khảo
        layout["slots"][slot_i]["_client"] = {"w": cw, "h": ch}
        save_coords_store(self.coords_store)

        self.slot_var.set(slot_i + 1)
        self._refresh_slot_ui()
        self.status.set(
            f"Đã ghi layout {layout.get('name')} ô {slot_i + 1} [{key}] "
            f"= ({rx:.4f}, {ry:.4f}) client {cw}x{ch}"
        )

        if mode == "wizard":
            if self._wizard_queue and self._wizard_queue[0] == (slot_i, key):
                self._wizard_queue.pop(0)
            # delay nhẹ rồi sang bước tiếp
            self.after(200, self._begin_next_wizard_step)

    def copy_slot0_to_all(self):
        layout = self.active_layout()
        if not layout["slots"]:
            return
        src = layout["slots"][0]
        if not slot_complete(src):
            messagebox.showwarning(
                "Ô 1 chưa đủ",
                "Hãy ghi đủ Account/Password/Login cho ô 1 trước.",
            )
            return
        if not messagebox.askyesno(
            "Xác nhận",
            f"Chép tọa độ ô 1 sang cả {layout['count']} ô của layout {layout.get('name')}?\n"
            "Chỉ nên dùng nếu UI login giống nhau trên mọi ô cùng kích thước.",
        ):
            return
        for i in range(1, layout["count"]):
            layout["slots"][i] = {
                "account": dict(src["account"]),
                "password": dict(src["password"]),
                "login": dict(src["login"]),
            }
            if "_client" in src:
                layout["slots"][i]["_client"] = dict(src["_client"])
        save_coords_store(self.coords_store)
        self._refresh_slot_ui()
        self.status.set(f"Đã chép ô 1 → {layout['count']} ô.")

    def clear_current_slot(self):
        layout = self.active_layout()
        idx = self.current_slot_index()
        if not messagebox.askyesno("Xác nhận", f"Xóa tọa độ ô {idx + 1}?"):
            return
        layout["slots"][idx] = empty_slot()
        save_coords_store(self.coords_store)
        self._refresh_slot_ui()

    def clear_layout_coords(self):
        layout = self.active_layout()
        if not messagebox.askyesno(
            "Xác nhận", f"Xóa toàn bộ tọa độ layout {layout.get('name')}?"
        ):
            return
        layout["slots"] = [empty_slot() for _ in range(layout["count"])]
        save_coords_store(self.coords_store)
        self._refresh_slot_ui()
        self.status.set(f"Đã xóa tọa độ layout {layout.get('name')}.")

    # ----- Shared busy / tiling -----
    def apply_preset(self, count, cols):
        self.count_var.set(count)
        self.cols_var.set(cols)
        name = layout_name(count, cols)
        self.ensure_layout(name, count, cols)
        if hasattr(self, "layout_var"):
            self.layout_var.set(name)
            self.slot_var.set(1)
            self._refresh_slot_ui()
        self.status.set(f"Preset {name}: mở {count} cửa sổ + hồ sơ tọa độ {name}.")

    def set_busy(self, busy, msg=None):
        self._busy = busy
        state = "disabled" if busy else "normal"
        for b in (
            self.btn_launch,
            self.btn_arrange,
            self.btn_close_all,
            self.btn_auto,
        ):
            try:
                b.configure(state=state)
            except Exception:
                pass
        # Auto Click & Commands controls (có thể chưa tạo nếu lỗi UI)
        for attr in (
            "btn_ac_pick",
            "btn_ac_clear",
            "btn_ac_start",
            "btn_ac_refresh",
            "btn_cmd_run",
        ):
            btn = getattr(self, attr, None)
            if btn is not None:
                try:
                    # khi đang chạy autoclick vẫn cho bấm Dừng
                    btn.configure(state=state)
                except Exception:
                    pass
        if msg is not None:
            self.status.set(msg)

    def tile_rects(self, count, monitors=None, cols=None):
        """Chia đều cửa sổ giữa các màn hình đã chọn, rồi tạo lưới trên từng màn hình."""
        monitors = monitors if monitors is not None else self._selected_monitors()
        if not monitors:
            raise ValueError("Chưa chọn màn hình để hiển thị cửa sổ.")
        cols = cols if cols and cols > 0 else self._grid_columns(count, monitors)
        base, remainder = divmod(count, len(monitors))
        rects = []
        max_rows = 0
        for index, monitor in enumerate(monitors):
            on_this_monitor = base + (1 if index < remainder else 0)
            if on_this_monitor <= 0:
                continue
            monitor_rects, rows = self._tile_rects_on_monitor(
                on_this_monitor, monitor, cols
            )
            rects.extend(monitor_rects)
            max_rows = max(max_rows, rows)
        return rects, cols, max_rows

    def refresh_saved_accounts(self):
        names = get_saved_account_usernames()
        if not hasattr(self, "saved_acc_status"):
            return
        if not names:
            self.saved_acc_status.set("Hiện không có account đã lưu (danh sách trống).")
        else:
            preview = ", ".join(names[:6])
            more = f" ... (+{len(names) - 6})" if len(names) > 6 else ""
            self.saved_acc_status.set(f"Đang lưu {len(names)} account: {preview}{more}")

    def on_clear_saved_accounts(self):
        if self._busy:
            return
        names = get_saved_account_usernames()
        running = list_running_megamu_processes()
        close_and_reopen = bool(self.reopen_dashboard_var.get())
        clear_dash = bool(self.clear_dashboard_var.get())
        detail = (
            "Sẽ xóa Registry AccountList + LastUsername"
            + (" + Dashboard config.ini" if clear_dash else "")
            + "."
        )
        if close_and_reopen:
            detail += (
                "\n\nSẽ ĐÓNG hết MEGAMU.exe + Dashboard.exe rồi mở lại Dashboard mới."
            )
            if running:
                detail += f"\nĐang chạy: {', '.join(running)}"
        elif running:
            if not messagebox.askyesno(
                "MEGAMU / Dashboard đang mở",
                "Nên đóng hết trước khi xóa, nếu không app có thể ghi đè lại list.\n"
                f"Đang chạy: {', '.join(running)}\n\n"
                "Vẫn xóa ngay (không đóng app)?",
            ):
                return
        if not messagebox.askyesno(
            "Xác nhận",
            "Xóa danh sách account đã đăng nhập trong MEGAMU?\n"
            f"Hiện có: {', '.join(names) if names else '(trống)'}\n\n"
            f"{detail}",
        ):
            return

        self.set_busy(True, "Đang đóng MEGAMU/Dashboard và xóa danh sách...")

        def worker():
            info = clear_megamu_saved_accounts(
                also_clear_dashboard=clear_dash,
                clear_last_username=True,
                close_apps=close_and_reopen,
                reopen_dashboard=close_and_reopen and clear_dash,
                megamu_path=self.path_var.get().strip(),
            )
            def done():
                self.refresh_saved_accounts()
                if info.get("error"):
                    self.set_busy(False, "Lỗi khi xóa danh sách.")
                    messagebox.showerror("Lỗi", info["error"])
                    return
                parts = [
                    f"AccountList {len(info.get('before') or [])} → {len(info.get('after') or [])}",
                    f"Dashboard={'có' if info.get('dashboard_cleared') else 'không'}",
                ]
                if info.get("apps_closed"):
                    killed = (info.get("close_info") or {}).get("killed") or []
                    parts.append("đã đóng " + (", ".join(killed) if killed else "apps"))
                if info.get("dashboard_reopened"):
                    parts.append("đã mở lại Dashboard")
                self.set_busy(False, " | ".join(parts))
            self.after(0, done)

        threading.Thread(target=worker, daemon=True).start()

    def on_launch(self):
        if self._busy:
            return
        path = self.path_var.get().strip()
        count = int(self.count_var.get())
        if count < 1:
            return
        monitors = self._selected_monitors()
        if not monitors:
            messagebox.showwarning(
                "Chưa chọn màn hình", "Hãy chọn ít nhất một màn hình để hiển thị cửa sổ."
            )
            return
        if not os.path.isfile(path):
            messagebox.showerror("Không tìm thấy", path)
            return

        # gắn hồ sơ layout theo cấu hình hiện tại
        cols = self._grid_columns(count, monitors)
        name = layout_name(count, cols)
        self.ensure_layout(name, count, cols)
        if hasattr(self, "layout_var"):
            self.layout_var.set(name)
            self._refresh_slot_ui()

        already = list_game_hwnds()
        close_and_reopen = bool(self.reopen_dashboard_var.get())
        clear_dash = bool(self.clear_dashboard_var.get())
        do_clear = bool(self.clear_before_launch_var.get())

        if already:
            if do_clear and close_and_reopen:
                if not messagebox.askyesno(
                    "Sẽ đóng cửa sổ đang mở",
                    f"Đang có {len(already)} cửa sổ MEGAMU.\n"
                    "Để xóa danh sách sạch, launcher sẽ ĐÓNG hết game + Dashboard,\n"
                    "xóa list, mở lại Dashboard, rồi mở cửa sổ mới.\n\n"
                    "Tiếp tục?",
                ):
                    return
            elif not messagebox.askyesno(
                "Đã có cửa sổ",
                f"Đang có {len(already)} cửa sổ.\nVẫn mở thêm {count}?",
            ):
                return

        self.set_busy(True, f"Đang mở {count} cửa sổ ({name}) trên {len(monitors)} màn hình...")

        def worker():
            if do_clear:
                self.after(
                    0,
                    lambda: self.status.set(
                        "Đang đóng MEGAMU/Dashboard và xóa danh sách..."
                        if close_and_reopen
                        else "Đang xóa danh sách account đã lưu..."
                    ),
                )
                info = clear_megamu_saved_accounts(
                    also_clear_dashboard=clear_dash,
                    clear_last_username=True,
                    close_apps=close_and_reopen,
                    reopen_dashboard=close_and_reopen and clear_dash,
                    megamu_path=path,
                )
                self.after(0, self.refresh_saved_accounts)
                if info.get("error"):
                    self.after(
                        0,
                        lambda: (
                            self.set_busy(False, "Không xóa được danh sách."),
                            messagebox.showerror(
                                "Không xóa được AccountList", info["error"]
                            ),
                        ),
                    )
                    return
            self._launch_worker(path, count, monitors, cols)

        threading.Thread(target=worker, daemon=True).start()

    def _launch_worker(self, path, count, monitors, cols):
        delay = float(self.delay_var.get())
        wait = float(self.wait_var.get())
        before = set(list_game_hwnds())
        launched = 0
        game_dir = get_megamu_dir(path)
        for i in range(count):
            self.after(0, lambda i=i: self.status.set(f"Đang mở {i + 1}/{count}..."))
            try:
                subprocess.Popen([path], cwd=game_dir)
                launched += 1
            except Exception as e:
                self.after(0, lambda: self.set_busy(False, f"Lỗi: {e}"))
                return
            if i < count - 1 and delay > 0:
                time.sleep(delay)

        target = len(before) + count
        deadline = time.time() + wait
        hwnds = []
        while time.time() < deadline:
            hwnds = list_game_hwnds()
            new_count = len([h for h in hwnds if h not in before])
            self.after(
                0,
                lambda n=len(hwnds): self.status.set(f"Thấy {n} cửa sổ game, đang chờ..."),
            )
            if len(hwnds) >= target or new_count >= count:
                break
            time.sleep(0.4)

        to_arrange = [h for h in hwnds if h not in before] or hwnds
        if not to_arrange:
            self.after(
                0,
                lambda: self.set_busy(
                    False, "Không thấy cửa sổ Unity. Đợi game hiện rồi bấm Sắp xếp lại."
                ),
            )
            return

        rects, cols, rows = self.tile_rects(len(to_arrange), monitors, cols)
        time.sleep(0.8)
        placed = arrange_hwnds(to_arrange, rects, retries=5, retry_delay=0.7)
        self.after(
            0,
            lambda: self.set_busy(
                False,
                f"Mở {launched}, sắp {placed}/{len(to_arrange)} trên {len(monitors)} màn hình "
                f"(lưới tối đa {cols}x{rows}/màn). "
                f"Hồ sơ tọa độ: {layout_name(count, cols)}.",
            ),
        )

    def on_arrange(self):
        if self._busy:
            return
        hwnds = list_game_hwnds()
        if not hwnds:
            messagebox.showinfo("Thông báo", "Không tìm thấy cửa sổ game.")
            return

        count = len(hwnds)
        monitors = self._selected_monitors()
        if not monitors:
            messagebox.showwarning(
                "Chưa chọn màn hình", "Hãy chọn ít nhất một màn hình để hiển thị cửa sổ."
            )
            return
        cols = self._grid_columns(count, monitors)
        name = layout_name(count, cols)
        self.ensure_layout(name, count, cols)
        self.count_var.set(count)
        self.cols_var.set(cols)
        if hasattr(self, "layout_var"):
            self.layout_var.set(name)
            self._refresh_slot_ui()

        self.set_busy(True, f"Đang sắp {count} cửa sổ ({name}) trên {len(monitors)} màn hình...")

        def worker():
            current = list_game_hwnds()
            rects, used_cols, rows = self.tile_rects(len(current), monitors, cols)
            placed = arrange_hwnds(current, rects, retries=5, retry_delay=0.5)
            self.after(
                0,
                lambda: self.set_busy(
                    False,
                    f"Đã sắp {placed}/{len(current)} cửa sổ trên {len(monitors)} màn hình "
                    f"(lưới tối đa {used_cols}x{rows}/màn).",
                ),
            )

        threading.Thread(target=worker, daemon=True).start()

    def on_close_all(self):
        if self._busy:
            return
        if not messagebox.askyesno(
            "Xác nhận", "Đóng TẤT CẢ MEGAMU.exe và Dashboard.exe?"
        ):
            return
        info = close_megamu_and_dashboard()
        if info.get("still_running"):
            self.status.set(
                "Chưa đóng hết: " + ", ".join(info["still_running"])
            )
        elif info.get("killed"):
            self.status.set("Đã đóng: " + ", ".join(info["killed"]))
        else:
            self.status.set("Không có MEGAMU/Dashboard đang chạy.")

    # ----- Auto login actions -----
    def _login_delays(self):
        return {
            "focus": float(self.login_delay_var.get()),
            "after_click": float(self.after_click_var.get()),
            "after_type": float(self.after_type_var.get()),
            "per_char": float(self.per_char_var.get()),
            "after_login": float(self.after_login_var.get()),
        }

    def _input_mode(self):
        mode = (self.input_mode_var.get() or "type").strip()
        if mode not in ("paste", "type", "paste_then_type"):
            return "type"
        return mode

    def _account_at(self, index):
        """Account theo thứ tự danh sách của loại tài khoản được chọn; thiếu hoặc user trống = ô để trống."""
        auto_g = (
            self.auto_account_group_var.get()
            if hasattr(self, "auto_account_group_var")
            else self.get_current_group()
        )
        acc_list = self.account_store.get("groups", {}).get(auto_g, [])
        if index < 0 or index >= len(acc_list):
            return None
        acc = acc_list[index]
        if not isinstance(acc, dict):
            return None
        username = (acc.get("username") or "").strip()
        if not username:
            return None
        return {"username": username, "password": acc.get("password") or ""}

    def _build_login_plan(self, hwnds):
        """
        Ghép account theo thứ tự bố cục cửa sổ (trên→dưới, trái→phải).
        Chỉ xét các ô vừa có trong layout vừa đang có cửa sổ; các dòng account
        dư không làm chặn Auto Login.
        """
        layout = self.active_layout()
        slot_count = layout["count"]
        plan = []  # list of dicts: index, hwnd, acc, slot
        skipped_empty = []
        missing_coords = []
        usable_count = min(len(hwnds), slot_count)

        for i in range(usable_count):
            acc = self._account_at(i)
            if not acc:
                skipped_empty.append(i + 1)
                continue

            # Có account trong ô đang hiển thị → cần tọa độ tương ứng.
            if i >= len(layout["slots"]):
                missing_coords.append(i + 1)
                continue
            slot = layout["slots"][i]
            if not slot_complete(slot):
                missing_coords.append(i + 1)
                continue

            plan.append(
                {
                    "index": i,
                    "hwnd": hwnds[i],
                    "acc": acc,
                    "slot": slot,
                }
            )

        auto_g = (
            self.auto_account_group_var.get()
            if hasattr(self, "auto_account_group_var")
            else self.get_current_group()
        )
        acc_list = self.account_store.get("groups", {}).get(auto_g, [])
        unused_accounts = [
            i + 1 for i in range(usable_count, len(acc_list)) if self._account_at(i)
        ]
        return plan, skipped_empty, missing_coords, unused_accounts

    def on_stop_login(self):
        self._stop_login = True
        self.status.set("Đang dừng auto login...")

    def on_test_one(self):
        if self._busy:
            return
        hwnds = list_game_hwnds()
        if not hwnds:
            messagebox.showinfo("Thông báo", "Không có cửa sổ game.")
            return

        slot, idx = self.current_slot()
        acc = self._account_at(idx)
        auto_g = (
            self.auto_account_group_var.get()
            if hasattr(self, "auto_account_group_var")
            else self.get_current_group()
        )
        if not acc:
            messagebox.showinfo(
                "Ô trống",
                f"Ô {idx + 1} không có tài khoản trong loại [{auto_g}] (để trống).\n"
                f"Thêm account ở dòng #{idx + 1} của loại [{auto_g}] nếu muốn login ô này.",
            )
            return
        if not slot_complete(slot):
            messagebox.showwarning(
                "Ô chưa đủ tọa độ",
                f"Ô {idx + 1} chưa ghi đủ Account/Password/Login.",
            )
            return
        if idx >= len(hwnds):
            messagebox.showwarning(
                "Thiếu cửa sổ",
                f"Chưa có cửa sổ cho ô {idx + 1} (đang mở {len(hwnds)} cửa sổ).",
            )
            return

        hwnd = hwnds[idx]
        self._stop_login = False
        self.set_busy(True, f"Thử login ô {idx + 1} ({acc['username']}) - [{auto_g}]...")
        self.btn_stop.configure(state="normal")
        self.iconify()

        def worker():
            try:
                login_one(
                    hwnd,
                    acc["username"],
                    acc["password"],
                    slot,
                    self._login_delays(),
                    input_mode=self._input_mode(),
                )
                msg = f"Đã thử ô {idx + 1}: {acc['username']} - [{auto_g}] (mode={self._input_mode()})"
            except Exception as e:
                msg = f"Lỗi: {e}"
            self.after(0, lambda: self._finish_login(msg))

        threading.Thread(target=worker, daemon=True).start()

    def on_auto_login(self):
        if self._busy:
            return
        hwnds = list_game_hwnds()
        if not hwnds:
            messagebox.showinfo("Thông báo", "Không có cửa sổ game đang mở.")
            return

        layout = self.active_layout()
        auto_g = (
            self.auto_account_group_var.get()
            if hasattr(self, "auto_account_group_var")
            else self.get_current_group()
        )
        plan, skipped_empty, missing_coords, unused_accounts = self._build_login_plan(hwnds)

        if missing_coords:
            messagebox.showwarning(
                "Thiếu tọa độ",
                f"Các ô có tài khoản nhưng chưa ghi tọa độ: {missing_coords}\n"
                "Ghi từng ô, hoặc ghi ô 1 rồi 'Chép ô 1 → tất cả ô'.\n"
                f"Các ô không có TK sẽ bỏ qua: {skipped_empty or '—'}",
            )
            return

        if not plan:
            messagebox.showinfo(
                "Không có ô để login",
                f"Không có cặp (tài khoản [{auto_g}] + cửa sổ + tọa độ) nào để chạy.\n"
                f"Thêm tài khoản vào loại [{auto_g}], hoặc mở thêm cửa sổ.",
            )
            return

        skip_txt = (
            f"\nÔ để trống (không có TK trong [{auto_g}]): {skipped_empty}" if skipped_empty else ""
        )
        unused_txt = (
            f"\nDòng account [{auto_g}] chưa dùng (vượt số ô/cửa sổ): {unused_accounts}"
            if unused_accounts
            else ""
        )
        if not messagebox.askyesno(
            "Xác nhận Auto Login",
            f"Layout {layout.get('name')}  |  Loại TK: [{auto_g}]\n"
            f"Sẽ login {len(plan)} ô: "
            + ", ".join(f"#{p['index'] + 1}={p['acc']['username']}" for p in plan)
            + skip_txt
            + unused_txt
            + "\nTiếp tục?",
        ):
            return

        self._stop_login = False
        self.set_busy(
            True,
            f"Auto login {len(plan)} ô (Layout {layout.get('name')}, Loại [{auto_g}])...",
        )
        self.btn_stop.configure(state="normal")
        self.iconify()

        mode = self._input_mode()

        def worker():
            ok = 0
            skipped = 0
            err = None
            between = float(self.between_win_var.get())
            delays = self._login_delays()
            total = len(plan)
            try:
                for step, item in enumerate(plan):
                    if self._stop_login:
                        break
                    i = item["index"]
                    hwnd = item["hwnd"]
                    acc = item["acc"]
                    slot = item["slot"]
                    self.after(
                        0,
                        lambda i=i, u=acc["username"], step=step: self.status.set(
                            f"Login ô {i + 1} ({step + 1}/{total}): {u}"
                        ),
                    )
                    if not user32.IsWindow(hwnd):
                        skipped += 1
                        continue
                    login_one(
                        hwnd,
                        acc["username"],
                        acc["password"],
                        slot,
                        delays,
                        input_mode=mode,
                    )
                    ok += 1
                    if step < total - 1 and between > 0:
                        time.sleep(between)
            except Exception as e:
                err = str(e)
            msg = (
                f"Auto login xong: {ok}/{total} "
                f"(layout {layout.get('name')}, mode={mode}, bỏ trống {len(skipped_empty)} ô)."
            )
            if skipped:
                msg += f" Bỏ qua {skipped} cửa sổ đã đóng."
            if self._stop_login:
                msg += " (đã dừng)"
            if err:
                msg += f" Lỗi: {err}"
            self.after(0, lambda: self._finish_login(msg))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_login(self, msg):
        try:
            self.deiconify()
            self.lift()
        except Exception:
            pass
        self.btn_stop.configure(state="disabled")
        self.set_busy(False, msg)

    # ----- Auto Click tab -----
    def _ac_profile_context(self):
        layout_name = self.active_layout().get("name") or self.active_layout_name()
        devices = tuple(monitor["device"] for monitor in self._selected_monitors())
        return layout_name, devices

    def _ac_profile_key(self):
        layout_name, devices = self._ac_profile_context()
        return f"{layout_name}||{'|'.join(devices) if devices else '(chưa chọn màn hình)'}"

    def _ac_profile_description(self):
        layout_name, devices = self._ac_profile_context()
        screens = ", ".join(devices) if devices else "chưa chọn màn hình"
        return f"Layout {layout_name} | {screens}"

    def _current_ac_profile(self):
        profiles = self.autoclick_store.setdefault("profiles", {})
        key = self._ac_profile_key()
        profile = profiles.get(key)
        if not isinstance(profile, dict):
            # Migrate danh sách điểm duy nhất của bản cũ vào profile đầu tiên.
            legacy = profiles.pop("__legacy__", None)
            points = legacy.get("points", []) if isinstance(legacy, dict) else []
            profile = {"points": list(points)}
            profiles[key] = profile
        if not isinstance(profile.get("points"), list):
            profile["points"] = []
        return profile

    def _ac_points(self):
        return self._current_ac_profile()["points"]

    def _refresh_ac_profile(self):
        profile = self._current_ac_profile()
        if hasattr(self, "ac_profile_var"):
            self.ac_profile_var.set(
                f"Hồ sơ điểm: {self._ac_profile_description()}  |  {len(profile['points'])} điểm"
            )
        if hasattr(self, "ac_list"):
            self._refresh_ac_list()

    def _ac_game_hwnds(self):
        """Chỉ lấy cửa sổ nằm trên các màn hình hiện được chọn."""
        monitors = self._selected_monitors()
        if not monitors:
            return []
        hwnds = []
        for hwnd in list_game_hwnds():
            x, y, w, h = get_window_rect(hwnd)
            center_x, center_y = x + w // 2, y + h // 2
            if any(
                left <= center_x < right and top <= center_y < bottom
                for left, top, right, bottom in (m["monitor"] for m in monitors)
            ):
                hwnds.append(hwnd)
        return hwnds

    def _build_autoclick_tab(self):
        frm = self.tab_autoclick
        ttk.Label(
            frm,
            text=(
                "Điểm click được lưu riêng theo layout và các màn hình đã chọn. "
                "Mỗi lần click chuột trái = 1 điểm, đến đủ số cửa sổ trong hồ sơ hiện tại thì dừng chọn."
            ),
            wraplength=620,
            justify="left",
        ).grid(row=0, column=0, columnspan=4, sticky="w")

        profile = ttk.LabelFrame(frm, text=" Hồ sơ điểm đang dùng ", padding=8)
        profile.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(10, 0))
        self.ac_profile_var = tk.StringVar(value="")
        ttk.Label(profile, textvariable=self.ac_profile_var, foreground="#055", wraplength=620).grid(
            row=0, column=0, sticky="w"
        )

        info = ttk.LabelFrame(frm, text=" Số điểm ", padding=8)
        info.grid(row=2, column=0, columnspan=4, sticky="ew", pady=(10, 0))
        self.ac_window_count_var = tk.StringVar(value="Cửa sổ đang mở: 0")
        ttk.Label(info, textvariable=self.ac_window_count_var).grid(
            row=0, column=0, sticky="w"
        )
        self.btn_ac_refresh = ttk.Button(
            info, text="Làm mới số cửa sổ", width=18, command=self.refresh_ac_window_count
        )
        self.btn_ac_refresh.grid(row=0, column=1, padx=(12, 0))

        timing = ttk.LabelFrame(frm, text=" Thời gian ", padding=8)
        timing.grid(row=3, column=0, columnspan=4, sticky="ew", pady=(10, 0))
        self.ac_delay_var = tk.DoubleVar(
            value=float(self.autoclick_store.get("delay_between", 0.5))
        )
        self.ac_run_var = tk.DoubleVar(
            value=float(self.autoclick_store.get("run_seconds", 30.0))
        )
        ttk.Label(timing, text="Delay giữa mỗi điểm (giây)").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Spinbox(
            timing,
            from_=0.05,
            to=30.0,
            increment=0.05,
            textvariable=self.ac_delay_var,
            width=8,
        ).grid(row=0, column=1, padx=(6, 16), sticky="w")
        ttk.Label(timing, text="Chạy trong (giây) rồi tự dừng").grid(
            row=0, column=2, sticky="w"
        )
        ttk.Spinbox(
            timing,
            from_=1.0,
            to=3600.0,
            increment=1.0,
            textvariable=self.ac_run_var,
            width=8,
        ).grid(row=0, column=3, padx=(6, 0), sticky="w")

        pts = ttk.LabelFrame(frm, text=" Danh sách điểm (tọa độ màn hình) ", padding=8)
        pts.grid(row=4, column=0, columnspan=4, sticky="nsew", pady=(10, 0))
        self.ac_list = tk.Listbox(pts, height=10, width=72, exportselection=False)
        self.ac_list.grid(row=0, column=0, columnspan=4, sticky="nsew")
        pts.columnconfigure(0, weight=1)

        btns = ttk.Frame(frm)
        btns.grid(row=5, column=0, columnspan=4, sticky="w", pady=(10, 0))
        self.btn_ac_pick = ttk.Button(
            btns, text="Chọn điểm (click chuột)", width=22, command=self.on_ac_start_pick
        )
        self.btn_ac_pick.pack(side="left", padx=(0, 6))
        self.btn_ac_clear = ttk.Button(
            btns, text="Xóa điểm", width=12, command=self.on_ac_clear_points
        )
        self.btn_ac_clear.pack(side="left", padx=(0, 6))
        self.btn_ac_start = ttk.Button(
            btns, text="Bắt đầu Auto Click", width=18, command=self.on_ac_start
        )
        self.btn_ac_start.pack(side="left", padx=(0, 6))
        self.btn_ac_stop = ttk.Button(
            btns, text="Dừng", width=10, command=self.on_ac_stop, state="disabled"
        )
        self.btn_ac_stop.pack(side="left")

        self.ac_status_var = tk.StringVar(
            value="Esc để dừng khi đang chạy hoặc hủy khi đang chọn điểm. F8 không dùng ở tab này."
        )
        ttk.Label(frm, textvariable=self.ac_status_var, wraplength=620).grid(
            row=6, column=0, columnspan=4, sticky="w", pady=(10, 0)
        )

        self.ac_zen_warn_var = tk.StringVar(value="")
        self.lbl_ac_zen_warn = ttk.Label(
            frm,
            textvariable=self.ac_zen_warn_var,
            foreground="#c00000",
            font=("Segoe UI", 9, "bold"),
            wraplength=620,
        )
        self.lbl_ac_zen_warn.grid(
            row=7, column=0, columnspan=4, sticky="w", pady=(4, 0)
        )

        self.refresh_ac_window_count()
        self._refresh_ac_profile()

    def refresh_ac_window_count(self):
        n = len(self._ac_game_hwnds())
        monitor_count = len(self._selected_monitors())
        self.ac_window_count_var.set(
            f"Cửa sổ trong {monitor_count} màn hình đã chọn: {n}  →  cần chọn {n} điểm"
        )
        return n

    def _refresh_ac_list(self):
        if not hasattr(self, "ac_list"):
            return
        self.ac_list.delete(0, tk.END)
        points = self._ac_points()
        if not points:
            self.ac_list.insert(tk.END, "(chưa có điểm)")
            return
        for i, pt in enumerate(points):
            self.ac_list.insert(tk.END, f"Điểm {i + 1}:  x={pt['x']}  y={pt['y']}")

    def _persist_ac_timing(self):
        try:
            self.autoclick_store["delay_between"] = float(self.ac_delay_var.get())
        except Exception:
            self.autoclick_store["delay_between"] = 0.5
        try:
            self.autoclick_store["run_seconds"] = float(self.ac_run_var.get())
        except Exception:
            self.autoclick_store["run_seconds"] = 30.0
        save_autoclick_store(self.autoclick_store)

    def on_ac_clear_points(self):
        if self._busy or self._ac_picking or self._ac_running:
            return
        if not messagebox.askyesno("Xác nhận", "Xóa toàn bộ điểm Auto Click đã chọn?"):
            return
        self._ac_points().clear()
        save_autoclick_store(self.autoclick_store)
        self._refresh_ac_profile()
        self.ac_status_var.set("Đã xóa danh sách điểm.")
        self.status.set("Đã xóa điểm Auto Click.")

    def on_ac_start_pick(self):
        if self._busy or self._ac_picking or self._ac_running:
            return
        if self._capture_target:
            messagebox.showwarning(
                "Đang ghi tọa độ",
                "Đang ghi tọa độ Auto Login (F8). Hủy (Esc) trước rồi mới chọn điểm Auto Click.",
            )
            return
        needed = self.refresh_ac_window_count()
        if needed < 1:
            messagebox.showwarning(
                "Chưa có cửa sổ",
                "Chưa có cửa sổ MEGAMU nào đang mở.\n"
                "Hãy mở/sắp xếp cửa sổ trước, rồi chọn điểm.",
            )
            return
        if not messagebox.askyesno(
            "Chọn điểm Auto Click",
            f"Sẽ ghi {needed} điểm (theo số cửa sổ đang mở).\n\n"
            "Cách chọn:\n"
            "1) Đưa chuột tới vị trí cần click trên từng cửa sổ\n"
            "2) Click chuột trái = ghi 1 điểm\n"
            "3) Lặp đến đủ số điểm\n\n"
            "Esc để hủy. Danh sách điểm cũ sẽ bị thay thế.",
        ):
            return

        # Xóa điểm cũ của đúng hồ sơ hiện tại rồi bắt đầu chọn.
        self._ac_points().clear()
        save_autoclick_store(self.autoclick_store)
        self._refresh_ac_profile()

        self._ac_picking = True
        self._ac_pick_needed = needed
        # chờ nhả nút chuột (tránh bắt luôn click của hộp thoại Yes)
        self._ac_pick_armed = False
        self.set_busy(True, f"Đang chọn điểm Auto Click 0/{needed} — click chuột trái...")
        self.ac_status_var.set(
            f"Click chuột trái để ghi điểm 1/{needed}. Esc hủy."
        )
        # cho phép bấm Esc / thấy trạng thái; nút Dừng không liên quan ở đây
        self._poll_ac_pick()

    def _cancel_ac_pick(self, msg="Đã hủy chọn điểm Auto Click."):
        self._ac_picking = False
        self._ac_pick_needed = 0
        self._ac_pick_armed = False
        if self._ac_pick_job:
            try:
                self.after_cancel(self._ac_pick_job)
            except Exception:
                pass
            self._ac_pick_job = None
        save_autoclick_store(self.autoclick_store)
        self._refresh_ac_list()
        self.set_busy(False, msg)
        self.ac_status_var.set(msg)

    def _poll_ac_pick(self):
        if not self._ac_picking:
            return
        if (user32.GetAsyncKeyState(VK_ESCAPE) & 0x8000) or (user32.GetAsyncKeyState(VK_ESCAPE) & 0x0001):
            self._cancel_ac_pick()
            return

        down = bool(user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000)
        if not self._ac_pick_armed:
            # đợi nhả chuột trước khi nhận click mới
            if not down:
                self._ac_pick_armed = True
            self._ac_pick_job = self.after(30, self._poll_ac_pick)
            return

        if down:
            # cạnh xuống: ghi điểm tại vị trí chuột hiện tại
            pt = POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            x, y = int(pt.x), int(pt.y)
            points = self._ac_points()
            points.append({"x": x, "y": y})
            save_autoclick_store(self.autoclick_store)
            self._refresh_ac_profile()

            got = len(points)
            needed = self._ac_pick_needed
            self.status.set(f"Đã ghi điểm {got}/{needed}: ({x}, {y})")
            self.ac_status_var.set(
                f"Đã ghi điểm {got}/{needed}: ({x}, {y}). "
                + (f"Click tiếp cho điểm {got + 1}." if got < needed else "Xong.")
            )

            if got >= needed:
                self._ac_picking = False
                self._ac_pick_armed = False
                self._ac_pick_job = None
                self.set_busy(
                    False,
                    f"Đã chọn đủ {needed} điểm Auto Click.",
                )
                self.ac_status_var.set(
                    f"Đủ {needed} điểm. Chỉnh delay / thời gian chạy rồi bấm Bắt đầu."
                )
                return

            # chờ nhả chuột rồi mới nhận điểm tiếp
            self._ac_pick_armed = False

        self._ac_pick_job = self.after(30, self._poll_ac_pick)

    def on_ac_start(self):
        if self._busy or self._ac_picking or self._ac_running:
            return
        self._persist_ac_timing()
        points = list(self._ac_points())
        if not points:
            messagebox.showwarning(
                "Chưa có điểm",
                "Hãy bấm “Chọn điểm (click chuột)” trước.",
            )
            return
        delay = max(0.05, float(self.autoclick_store.get("delay_between", 0.5)))
        run_seconds = max(1.0, float(self.autoclick_store.get("run_seconds", 30.0)))
        if not messagebox.askyesno(
            "Bắt đầu Auto Click",
            f"{self._ac_profile_description()}\n"
            f"Sẽ click lần lượt {len(points)} điểm,\n"
            f"cách nhau {delay:.2f}s, chạy trong {run_seconds:.0f}s rồi tự dừng.\n"
            f"Mỗi click trừ 10.000.000 Zen của tài khoản tương ứng.\n"
            "Có thể bấm Dừng hoặc nhấn phím ESC bất cứ lúc nào.\n\nTiếp tục?",
        ):
            return

        self._ac_running = True
        self._stop_autoclick = False
        self.set_busy(True, f"Auto Click (ESC để dừng): 0s / {run_seconds:.0f}s...")
        self.btn_ac_stop.configure(state="normal")
        try:
            self.btn_ac_stop.configure(state="normal")
        except Exception:
            pass

        self.ac_zen_warn_var.set("")

        def worker():
            start = time.time()
            clicks = 0
            idx = 0
            err = None
            last_save_time = start
            warned_slots = set()

            # Xóa trạng thái phím ESC còn tồn trước khi vào vòng lặp
            user32.GetAsyncKeyState(VK_ESCAPE)

            try:
                while not self._stop_autoclick:
                    if (user32.GetAsyncKeyState(VK_ESCAPE) & 0x8000) or (
                        user32.GetAsyncKeyState(VK_ESCAPE) & 0x0001
                    ):
                        self._stop_autoclick = True
                        break
                    elapsed = time.time() - start
                    if elapsed >= run_seconds:
                        break
                    p_idx = idx % len(points)
                    pt = points[p_idx]
                    mouse_click_screen(pt["x"], pt["y"], settle=0.05, hwnd=None)
                    clicks += 1
                    idx += 1

                    # Trừ 10.000.000 Zen cho tài khoản tương ứng
                    warn_msg = None
                    active_accs = self.get_current_accounts()
                    if p_idx < len(active_accs):
                        acc = active_accs[p_idx]
                        cur_zen = parse_zen(acc.get("zen", 0))
                        new_zen = max(0, cur_zen - ZEN_PER_CLICK)
                        acc["zen"] = new_zen

                        if new_zen < ZEN_WARN_THRESHOLD:
                            slot_num = p_idx + 1
                            u_name = acc.get("username", f"Slot {slot_num}")
                            warn_msg = f"⚠️ CẢNH BÁO: Slot {slot_num} ({u_name}) còn {format_zen(new_zen)} Zen (< 200M)!"
                            if slot_num not in warned_slots:
                                warned_slots.add(slot_num)
                                try:
                                    user32.MessageBeep(0x00000030)
                                except Exception:
                                    pass

                    self.after(
                        0,
                        lambda e=elapsed, c=clicks, i=p_idx + 1, wm=warn_msg: self._on_ac_tick(
                            e, run_seconds, c, i, len(points), wm
                        ),
                    )

                    # Lưu accounts định kỳ mỗi 5s
                    if time.time() - last_save_time >= 5.0:
                        save_account_store(self.account_store)
                        last_save_time = time.time()

                    # ngủ theo delay, nhưng vẫn kiểm tra stop / hết giờ / phím ESC
                    end_sleep = time.time() + delay
                    while time.time() < end_sleep:
                        if (user32.GetAsyncKeyState(VK_ESCAPE) & 0x8000) or (
                            user32.GetAsyncKeyState(VK_ESCAPE) & 0x0001
                        ):
                            self._stop_autoclick = True
                            break
                        if self._stop_autoclick:
                            break
                        if time.time() - start >= run_seconds:
                            break
                        time.sleep(0.02)
            except Exception as e:
                err = str(e)

            try:
                save_account_store(self.account_store)
            except Exception:
                pass

            def done():
                self._ac_running = False
                self.btn_ac_stop.configure(state="disabled")
                self._refresh_acc_tree()
                elapsed = time.time() - start
                if self._stop_autoclick:
                    msg = f"Đã dừng Auto Click sau {elapsed:.1f}s ({clicks} click)."
                elif err:
                    msg = f"Auto Click lỗi: {err} (đã click {clicks})."
                else:
                    msg = (
                        f"Auto Click xong: {clicks} click trong {elapsed:.1f}s "
                        f"({len(points)} điểm)."
                    )
                self.set_busy(False, msg)
                self.ac_status_var.set(msg)

            self.after(0, done)

        threading.Thread(target=worker, daemon=True).start()

    def _on_ac_tick(self, elapsed, run_seconds, clicks, point_idx, total_points, warn_msg):
        status_txt = (
            f"Auto Click (ESC để dừng): {elapsed:.1f}s/{run_seconds:.0f}s | "
            f"click #{clicks} tại điểm {point_idx}/{total_points}"
        )
        if warn_msg:
            status_txt += f" | {warn_msg}"
            self.ac_zen_warn_var.set(warn_msg)
        self.status.set(status_txt)
        self._refresh_acc_tree()

    def on_ac_stop(self):
        self._stop_autoclick = True
        self.status.set("Đang dừng Auto Click...")

    # ----- Commands Tab -----
    def _persist_commands_settings(self):
        try:
            if hasattr(self, "cmd_text_var"):
                self.commands_store["last_command"] = self.cmd_text_var.get().strip()
            if hasattr(self, "cmd_delay_enter_var"):
                self.commands_store["delay_after_enter"] = float(self.cmd_delay_enter_var.get())
            if hasattr(self, "cmd_delay_win_var"):
                self.commands_store["delay_between_windows"] = float(self.cmd_delay_win_var.get())
            if hasattr(self, "cmd_method_var"):
                self.commands_store["type_method"] = self.cmd_method_var.get()
            if hasattr(self, "cmd_target_mode_var"):
                self.commands_store["target_mode"] = self.cmd_target_mode_var.get()
            if hasattr(self, "cmd_loop_var"):
                self.commands_store["loop_enabled"] = bool(self.cmd_loop_var.get())
            if hasattr(self, "cmd_loop_sec_var"):
                self.commands_store["loop_interval"] = float(self.cmd_loop_sec_var.get())
            save_commands_store(self.commands_store)
        except Exception:
            pass

    def _build_commands_tab(self):
        frm = self.tab_commands

        ttk.Label(
            frm,
            text=(
                "Tự động chuyển qua từng cửa sổ game MEGAMU → Nhấn Enter → Gõ lệnh yêu cầu → Nhấn Enter gửi."
            ),
            wraplength=620,
            justify="left",
        ).grid(row=0, column=0, columnspan=4, sticky="w")

        # Frame 1: Lệnh cần thực hiện
        box_cmd = ttk.LabelFrame(frm, text=" Lệnh thực hiện ", padding=8)
        box_cmd.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(8, 0))

        self.cmd_text_var = tk.StringVar(
            value=self.commands_store.get("last_command", "/re auto")
        )

        row1 = ttk.Frame(box_cmd)
        row1.pack(fill="x", expand=True)

        ttk.Label(row1, text="Chuỗi lệnh:", font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 6))
        self.cmd_entry = ttk.Entry(
            row1,
            textvariable=self.cmd_text_var,
            font=("Segoe UI", 10, "bold"),
        )
        self.cmd_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.btn_cmd_run = ttk.Button(
            row1,
            text="🚀 Gõ lệnh ngay (F9)",
            width=20,
            command=self.on_cmd_start,
        )
        self.btn_cmd_run.pack(side="left", padx=(0, 6))

        self.btn_cmd_stop = ttk.Button(
            row1,
            text="🛑 Dừng (Esc)",
            width=12,
            command=self.on_cmd_stop,
            state="disabled",
        )
        self.btn_cmd_stop.pack(side="left")

        # Quick action buttons row
        quick_row = ttk.Frame(box_cmd)
        quick_row.pack(fill="x", expand=True, pady=(8, 2))

        ttk.Label(quick_row, text="Lệnh nhanh:").pack(side="left", padx=(0, 6))
        quick_cmds = [
            ("/re auto", "/re auto"),
            ("/attack", "/attack"),
            ("/pick zen", "/pick zen"),
            ("/pick", "/pick"),
            ("/offtrade", "/offtrade"),
            ("/post", "/post "),
            ("/ware 0", "/ware 0"),
            ("/ware 1", "/ware 1"),
        ]
        for label, cmd_val in quick_cmds:
            ttk.Button(
                quick_row,
                text=label,
                width=len(label) + 2,
                command=lambda c=cmd_val: self.on_cmd_quick(c),
            ).pack(side="left", padx=(0, 4))

        # Frame 2: Danh sách lệnh mẫu đã lưu
        box_list = ttk.LabelFrame(frm, text=" Danh sách lệnh mẫu đã lưu ", padding=8)
        box_list.grid(row=2, column=0, columnspan=4, sticky="nsew", pady=(8, 0))

        tree_frame = ttk.Frame(box_list)
        tree_frame.pack(fill="both", expand=True)

        self.cmd_tree = ttk.Treeview(
            tree_frame,
            columns=("name", "cmd"),
            show="headings",
            height=6,
            selectmode="browse",
        )
        self.cmd_tree.heading("name", text="Tên gợi nhớ")
        self.cmd_tree.heading("cmd", text="Chuỗi lệnh game")
        self.cmd_tree.column("name", width=220, anchor="w")
        self.cmd_tree.column("cmd", width=380, anchor="w")

        cmd_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.cmd_tree.yview)
        self.cmd_tree.configure(yscrollcommand=cmd_scroll.set)
        self.cmd_tree.pack(side="left", fill="both", expand=True)
        cmd_scroll.pack(side="right", fill="y")

        self.cmd_tree.bind("<Double-1>", self._on_cmd_tree_double_click)
        self.cmd_tree.bind("<<TreeviewSelect>>", self._on_cmd_tree_select)

        # Buttons under list
        tree_btns = ttk.Frame(box_list)
        tree_btns.pack(fill="x", expand=True, pady=(6, 0))

        ttk.Button(tree_btns, text="➕ Thêm lệnh...", width=14, command=self.on_cmd_add).pack(
            side="left", padx=(0, 6)
        )
        ttk.Button(tree_btns, text="✏️ Sửa...", width=10, command=self.on_cmd_edit).pack(
            side="left", padx=(0, 6)
        )
        ttk.Button(tree_btns, text="🗑️ Xóa", width=10, command=self.on_cmd_delete).pack(
            side="left", padx=(0, 6)
        )
        ttk.Button(tree_btns, text="📋 Chọn lệnh này", width=16, command=self.on_cmd_select_preset).pack(
            side="left", padx=(0, 6)
        )
        ttk.Button(tree_btns, text="⚡ Gõ lệnh này ngay", width=18, command=self.on_cmd_run_selected_preset).pack(
            side="left"
        )

        # Frame 3: Cấu hình & Tùy chọn
        opts = ttk.LabelFrame(frm, text=" Cấu hình & Tùy chọn ", padding=8)
        opts.grid(row=3, column=0, columnspan=4, sticky="ew", pady=(8, 0))

        # Target & method
        self.cmd_target_mode_var = tk.StringVar(
            value=self.commands_store.get("target_mode", "all")
        )
        self.cmd_method_var = tk.StringVar(
            value=self.commands_store.get("type_method", "paste")
        )

        row_opt1 = ttk.Frame(opts)
        row_opt1.pack(fill="x", expand=True, pady=(0, 4))
        ttk.Label(row_opt1, text="Mục tiêu:").pack(side="left", padx=(0, 6))
        ttk.Radiobutton(
            row_opt1,
            text="Tất cả cửa sổ MEGAMU đang mở",
            variable=self.cmd_target_mode_var,
            value="all",
            command=self._persist_commands_settings,
        ).pack(side="left", padx=(0, 12))
        ttk.Radiobutton(
            row_opt1,
            text="Chỉ các màn hình đã chọn (tab Mở & Sắp xếp)",
            variable=self.cmd_target_mode_var,
            value="selected_monitors",
            command=self._persist_commands_settings,
        ).pack(side="left")

        row_opt2 = ttk.Frame(opts)
        row_opt2.pack(fill="x", expand=True, pady=(0, 4))
        ttk.Label(row_opt2, text="Cách nhập:").pack(side="left", padx=(0, 6))
        ttk.Radiobutton(
            row_opt2,
            text="Dán nhanh Clipboard (Khuyên dùng — chuẩn xác 100%, hỗ trợ tiếng Việt)",
            variable=self.cmd_method_var,
            value="paste",
            command=self._persist_commands_settings,
        ).pack(side="left", padx=(0, 12))
        ttk.Radiobutton(
            row_opt2,
            text="Gõ Scancode (SendInput)",
            variable=self.cmd_method_var,
            value="type",
            command=self._persist_commands_settings,
        ).pack(side="left")

        # Delays & loop
        row_opt3 = ttk.Frame(opts)
        row_opt3.pack(fill="x", expand=True, pady=(2, 0))

        self.cmd_delay_enter_var = tk.DoubleVar(
            value=float(self.commands_store.get("delay_after_enter", 0.10))
        )
        self.cmd_delay_win_var = tk.DoubleVar(
            value=float(self.commands_store.get("delay_between_windows", 0.15))
        )
        self.cmd_loop_var = tk.BooleanVar(
            value=bool(self.commands_store.get("loop_enabled", False))
        )
        self.cmd_loop_sec_var = tk.DoubleVar(
            value=float(self.commands_store.get("loop_interval", 60.0))
        )

        ttk.Label(row_opt3, text="Chờ sau khi mở Chat:").pack(side="left", padx=(0, 4))
        ttk.Spinbox(
            row_opt3,
            from_=0.02,
            to=3.0,
            increment=0.02,
            textvariable=self.cmd_delay_enter_var,
            width=6,
            command=self._persist_commands_settings,
        ).pack(side="left", padx=(0, 14))

        ttk.Label(row_opt3, text="Chờ giữa các cửa sổ:").pack(side="left", padx=(0, 4))
        ttk.Spinbox(
            row_opt3,
            from_=0.02,
            to=5.0,
            increment=0.05,
            textvariable=self.cmd_delay_win_var,
            width=6,
            command=self._persist_commands_settings,
        ).pack(side="left", padx=(0, 14))

        ttk.Checkbutton(
            row_opt3,
            text="Tự động lặp lại sau",
            variable=self.cmd_loop_var,
            command=self._persist_commands_settings,
        ).pack(side="left", padx=(0, 4))
        ttk.Spinbox(
            row_opt3,
            from_=1.0,
            to=3600.0,
            increment=5.0,
            textvariable=self.cmd_loop_sec_var,
            width=6,
            command=self._persist_commands_settings,
        ).pack(side="left", padx=(0, 4))
        ttk.Label(row_opt3, text="giây").pack(side="left")

        # Frame 4: Status line & Shortcut info
        self.cmd_status_var = tk.StringVar(
            value="Phím tắt: F9 = Gõ lệnh ngay cho tất cả cửa sổ  |  Esc = Dừng khẩn cấp."
        )
        ttk.Label(
            frm,
            textvariable=self.cmd_status_var,
            foreground="#055",
            wraplength=620,
        ).grid(row=4, column=0, columnspan=4, sticky="w", pady=(8, 0))

        self._refresh_cmd_tree()

    def _refresh_cmd_tree(self):
        for item in self.cmd_tree.get_children():
            self.cmd_tree.delete(item)
        presets = self.commands_store.get("commands", [])
        for i, p in enumerate(presets):
            self.cmd_tree.insert(
                "",
                "end",
                iid=str(i),
                values=(p.get("name", ""), p.get("cmd", "")),
            )

    def _on_cmd_tree_select(self, _event=None):
        sel = self.cmd_tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        presets = self.commands_store.get("commands", [])
        if 0 <= idx < len(presets):
            cmd_val = presets[idx].get("cmd", "")
            if cmd_val:
                self.cmd_text_var.set(cmd_val)

    def _on_cmd_tree_double_click(self, _event=None):
        self._on_cmd_tree_select()

    def on_cmd_quick(self, cmd_val: str):
        self.cmd_text_var.set(cmd_val)
        self.commands_store["last_command"] = cmd_val
        self._persist_commands_settings()
        self.status.set(f"Đã chọn lệnh nhanh: {cmd_val}")

    def on_cmd_select_preset(self):
        sel = self.cmd_tree.selection()
        if not sel:
            messagebox.showinfo("Chọn lệnh", "Vui lòng chọn 1 lệnh từ danh sách phía trên.", parent=self)
            return
        idx = int(sel[0])
        presets = self.commands_store.get("commands", [])
        if 0 <= idx < len(presets):
            self.cmd_text_var.set(presets[idx].get("cmd", ""))
            self.status.set(f"Đã chọn lệnh: {presets[idx].get('name')}")

    def on_cmd_run_selected_preset(self):
        sel = self.cmd_tree.selection()
        if not sel:
            messagebox.showinfo("Chọn lệnh", "Vui lòng chọn 1 lệnh từ danh sách phía trên.", parent=self)
            return
        idx = int(sel[0])
        presets = self.commands_store.get("commands", [])
        if 0 <= idx < len(presets):
            cmd_val = presets[idx].get("cmd", "")
            self.cmd_text_var.set(cmd_val)
            self.on_cmd_start(cmd_val)

    def on_cmd_add(self):
        name = simpledialog.askstring("Thêm lệnh mẫu", "Nhập tên gợi nhớ (ví dụ: Party tự động, Rao bán Wing...):", parent=self)
        if not name or not name.strip():
            return
        cmd = simpledialog.askstring("Thêm lệnh mẫu", "Nhập chuỗi lệnh game (ví dụ: /re auto, /post ...):", parent=self)
        if not cmd or not cmd.strip():
            return
        presets = self.commands_store.setdefault("commands", [])
        presets.append({"name": name.strip(), "cmd": cmd.strip()})
        save_commands_store(self.commands_store)
        self._refresh_cmd_tree()
        self.status.set(f"Đã thêm lệnh mẫu '{name.strip()}': {cmd.strip()}")

    def on_cmd_edit(self):
        sel = self.cmd_tree.selection()
        if not sel:
            messagebox.showinfo("Sửa lệnh", "Vui lòng chọn 1 lệnh trong danh sách để sửa.", parent=self)
            return
        idx = int(sel[0])
        presets = self.commands_store.get("commands", [])
        if not (0 <= idx < len(presets)):
            return
        cur = presets[idx]
        new_name = simpledialog.askstring(
            "Sửa lệnh mẫu",
            "Tên gợi nhớ:",
            initialvalue=cur.get("name", ""),
            parent=self,
        )
        if new_name is None:
            return
        new_cmd = simpledialog.askstring(
            "Sửa lệnh mẫu",
            "Chuỗi lệnh game:",
            initialvalue=cur.get("cmd", ""),
            parent=self,
        )
        if new_cmd is None:
            return
        cur["name"] = new_name.strip()
        cur["cmd"] = new_cmd.strip()
        save_commands_store(self.commands_store)
        self._refresh_cmd_tree()
        self.status.set(f"Đã cập nhật lệnh: '{cur['name']}' → {cur['cmd']}")

    def on_cmd_delete(self):
        sel = self.cmd_tree.selection()
        if not sel:
            messagebox.showinfo("Xóa lệnh", "Vui lòng chọn 1 lệnh trong danh sách để xóa.", parent=self)
            return
        idx = int(sel[0])
        presets = self.commands_store.get("commands", [])
        if not (0 <= idx < len(presets)):
            return
        cur = presets[idx]
        if not messagebox.askyesno("Xác nhận xóa", f"Bạn có chắc muốn xóa lệnh '{cur.get('name')}' ({cur.get('cmd')})?", parent=self):
            return
        presets.pop(idx)
        save_commands_store(self.commands_store)
        self._refresh_cmd_tree()
        self.status.set(f"Đã xóa lệnh '{cur.get('name')}'.")

    def _on_f9(self, _event=None):
        if not self._busy and not getattr(self, "_cmd_running", False):
            self.on_cmd_start()

    def on_cmd_start(self, custom_cmd=None):
        if getattr(self, "_cmd_running", False):
            return
        cmd = (custom_cmd if custom_cmd is not None else self.cmd_text_var.get()).strip()
        if not cmd:
            messagebox.showwarning("Chưa nhập lệnh", "Vui lòng nhập lệnh cần gõ (ví dụ: /re auto).", parent=self)
            return

        target_mode = self.cmd_target_mode_var.get()
        if target_mode == "selected_monitors":
            hwnds = self._ac_game_hwnds()
        else:
            hwnds = list_game_hwnds()

        if not hwnds:
            msg = "Không tìm thấy cửa sổ game MEGAMU nào đang mở!"
            messagebox.showinfo("Thông báo", msg, parent=self)
            self.status.set(msg)
            return

        self.commands_store["last_command"] = cmd
        self._persist_commands_settings()

        self._cmd_running = True
        self._stop_cmd = False
        self.btn_cmd_run.configure(state="disabled")
        self.btn_cmd_stop.configure(state="normal")
        self.set_busy(True, f"Bắt đầu gõ lệnh '{cmd}' trên {len(hwnds)} cửa sổ...")

        def worker():
            loop = bool(self.cmd_loop_var.get())
            loop_interval = max(1.0, float(self.cmd_loop_sec_var.get()))
            delay_enter = max(0.02, float(self.cmd_delay_enter_var.get()))
            delay_win = max(0.02, float(self.cmd_delay_win_var.get()))
            method = self.cmd_method_var.get()

            iteration = 0
            total_typed = 0
            err = None

            try:
                while not self._stop_cmd:
                    iteration += 1
                    if target_mode == "selected_monitors":
                        cur_hwnds = self._ac_game_hwnds()
                    else:
                        cur_hwnds = list_game_hwnds()

                    if not cur_hwnds:
                        break

                    for idx, hwnd in enumerate(cur_hwnds):
                        if self._stop_cmd or (user32.GetAsyncKeyState(VK_ESCAPE) & 0x8000) or (user32.GetAsyncKeyState(VK_ESCAPE) & 0x0001):
                            self._stop_cmd = True
                            break

                        if not user32.IsWindow(hwnd):
                            continue

                        title = get_window_text(hwnd) or f"MEGAMU {idx + 1}"
                        self.after(
                            0,
                            lambda i=idx + 1, n=len(cur_hwnds), t=title, c=cmd: self._on_cmd_tick(
                                i, n, t, c
                            ),
                        )

                        # 1. Ép cửa sổ lên foreground
                        focus_window(hwnd)
                        time.sleep(0.08)

                        # 2. Nhấn Enter mở thanh chat
                        release_modifiers()
                        tap_vk(VK_RETURN, pause=delay_enter)

                        # 3. Gõ hoặc dán nội dung lệnh
                        if method == "type":
                            type_text_scancode(cmd)
                        else:
                            paste_text(cmd, settle=0.04)
                        time.sleep(0.04)

                        # 4. Nhấn Enter gửi lệnh
                        tap_vk(VK_RETURN, pause=0.05)
                        release_modifiers()

                        total_typed += 1
                        if idx < len(cur_hwnds) - 1 and delay_win > 0:
                            time.sleep(delay_win)

                    if not loop or self._stop_cmd:
                        break

                    loop_end = time.time() + loop_interval
                    while time.time() < loop_end and not self._stop_cmd:
                        if (user32.GetAsyncKeyState(VK_ESCAPE) & 0x8000) or (
                            user32.GetAsyncKeyState(VK_ESCAPE) & 0x0001
                        ):
                            self._stop_cmd = True
                            break
                        rem = max(0.0, loop_end - time.time())
                        self.after(
                            0,
                            lambda r=rem, c=cmd: self.cmd_status_var.set(
                                f"Đang chờ {r:.1f}s để lặp lại lệnh '{c}' (Esc để dừng)..."
                            ),
                        )
                        time.sleep(0.1)

            except Exception as e:
                err = str(e)

            def done():
                self._cmd_running = False
                self.btn_cmd_run.configure(state="normal")
                self.btn_cmd_stop.configure(state="disabled")
                self.set_busy(False)
                if self._stop_cmd:
                    msg = f"Đã dừng gõ lệnh. Đã thực hiện {total_typed} lượt."
                elif err:
                    msg = f"Gõ lệnh lỗi: {err} (đã gõ {total_typed} lượt)."
                else:
                    msg = f"Đã gõ lệnh '{cmd}' thành công trên {total_typed} cửa sổ."
                self.status.set(msg)
                self.cmd_status_var.set(msg)

            self.after(0, done)

        threading.Thread(target=worker, daemon=True).start()

    def _on_cmd_tick(self, current, total, title, cmd):
        info = parse_game_window_title(title)
        disp = info["display"] if info["is_in_game"] else title
        status_txt = f"Đang gõ lệnh [{current}/{total}] '{cmd}' → {disp} (Esc để dừng)"
        self.status.set(status_txt)
        self.cmd_status_var.set(status_txt)

    def on_cmd_stop(self):
        self._stop_cmd = True
        self.status.set("Đang dừng gõ lệnh...")

    def _poll_game_window_titles(self):
        try:
            hwnds = list_game_hwnds()
            active_accs = self.get_current_accounts()
            changed = False
            for idx, hwnd in enumerate(hwnds):
                if idx < len(active_accs):
                    title = get_window_text(hwnd)
                    info = parse_game_window_title(title)
                    acc = active_accs[idx]
                    if info["is_in_game"]:
                        srv = info["server"] or "Online"
                        if (
                            acc.get("char_name") != info["char_name"]
                            or acc.get("char_level") != info["level"]
                            or acc.get("char_reset") != info["reset"]
                            or acc.get("char_server") != info["server"]
                            or acc.get("char_display") != info["display"]
                            or acc.get("online_server") != srv
                        ):
                            acc["char_name"] = info["char_name"]
                            acc["char_level"] = info["level"]
                            acc["char_reset"] = info["reset"]
                            acc["char_server"] = info["server"]
                            acc["char_display"] = info["display"]
                            acc["online_server"] = srv
                            changed = True
                    else:
                        if acc.get("online_server") != "Đang mở game":
                            acc["online_server"] = "Đang mở game"
                            changed = True
            for idx in range(len(hwnds), len(active_accs)):
                if active_accs[idx].get("online_server"):
                    active_accs[idx]["online_server"] = ""
                    changed = True

            if changed:
                save_account_store(self.account_store)
                self._refresh_acc_tree()
                if hasattr(self, "slot_tree"):
                    self._refresh_slot_ui()
        except Exception:
            pass
        finally:
            if not getattr(self, "_closing", False):
                self._title_poll_job = self.after(1500, self._poll_game_window_titles)

    def on_close(self):
        self._closing = True
        if getattr(self, "_title_poll_job", None):
            try:
                self.after_cancel(self._title_poll_job)
            except Exception:
                pass
        self._capture_target = None
        self._wizard_queue = []
        self._stop_login = True
        self._stop_autoclick = True
        self._stop_cmd = True
        if self._ac_picking:
            self._ac_picking = False
        if self._ac_pick_job:
            try:
                self.after_cancel(self._ac_pick_job)
            except Exception:
                pass
        try:
            self._persist_ac_timing()
        except Exception:
            pass
        try:
            self._persist_commands_settings()
        except Exception:
            pass
        self.destroy()


def main():
    enable_per_monitor_dpi_awareness()
    # Root ẩn cho các gate (update → license), rồi mở app chính.
    boot = tk.Tk()
    boot.withdraw()
    try:
        if not run_update_gate(boot):
            boot.destroy()
            return
        if not run_license_gate(boot):
            boot.destroy()
            return
        license_info = getattr(boot, "_license_info", None)
    except Exception as e:
        try:
            messagebox.showerror("MuClick", f"Không khởi động được: {e}")
        except Exception:
            pass
        try:
            boot.destroy()
        except Exception:
            pass
        return

    boot.destroy()

    app = MegamuLauncherApp()
    app._license_info = license_info or {}
    # cập nhật title sau khi gán license (constructor đã chạy)
    exp = (license_info or {}).get("exp")
    exp_txt = f"  |  License đến {exp}" if exp else ""
    app.title(f"MuClick {APP_VERSION} — MEGAMU Multi Launcher{exp_txt}")
    if license_info:
        days = license_info.get("days_left")
        app.status.set(
            f"Sẵn sàng. v{APP_VERSION}"
            + (f" — license còn {days} ngày." if days is not None else "")
        )
    app.mainloop()


if __name__ == "__main__":
    main()

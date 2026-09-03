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
import subprocess
import threading
import time
import tkinter as tk
import winreg
from ctypes import wintypes
from tkinter import messagebox, ttk

from muclick_gates import run_license_gate, run_update_gate
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

MEGAMU_PATH = r"C:\Users\donpv\AppData\Local\Programs\MEGAMU\MEGAMU.exe"
MEGAMU_DIR = r"C:\Users\donpv\AppData\Local\Programs\MEGAMU"
DASHBOARD_PATH = os.path.join(MEGAMU_DIR, "Dashboard.exe")
MEGAMU_CONFIG_INI = os.path.join(MEGAMU_DIR, "config.ini")
UNITY_CLASS = "UnityWndClass"
MEGAMU_PROCESS_NAMES = ("MEGAMU.exe", "Dashboard.exe")
APP_DIR = install_dir()
# Dữ liệu user nằm %APPDATA%\MuClick (survive khi update thay exe)
migrate_user_files(
    ("accounts.json", "click_coords.json", "autoclick_points.json")
)
ACCOUNTS_FILE = data_path("accounts.json")
COORDS_FILE = data_path("click_coords.json")
AUTOCLICK_FILE = data_path("autoclick_points.json")

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
    "3x3": (9, 3),
    "4x3": (12, 4),
}

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


# ---------------------------------------------------------------------------
# Window helpers
# ---------------------------------------------------------------------------
def get_screen_size():
    return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


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
    sw, sh = get_screen_size()
    abs_x = int(x * 65535 / max(sw - 1, 1))
    abs_y = int(y * 65535 / max(sh - 1, 1))
    extra = ctypes.pointer(ctypes.c_ulong(0))
    move = INPUT(
        type=INPUT_MOUSE,
        union=INPUT_UNION(
            mi=MOUSEINPUT(abs_x, abs_y, 0, MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, 0, extra)
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
    return {"version": 2, "active_layout": "2x2", "layouts": layouts}


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


def load_accounts():
    data = load_json(ACCOUNTS_FILE, {"accounts": []})
    return data.get("accounts", [])


def save_accounts(accounts):
    save_json(ACCOUNTS_FILE, {"accounts": accounts})


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


def open_dashboard():
    """Mở Dashboard.exe mới. Trả về True nếu spawn được."""
    if not os.path.isfile(DASHBOARD_PATH):
        return False
    subprocess.Popen([DASHBOARD_PATH], cwd=MEGAMU_DIR)
    return True


def clear_megamu_saved_accounts(
    also_clear_dashboard=True,
    clear_last_username=True,
    close_apps=False,
    reopen_dashboard=False,
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

        if also_clear_dashboard and os.path.isfile(MEGAMU_CONFIG_INI):
            try:
                with open(MEGAMU_CONFIG_INI, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                if isinstance(cfg, dict):
                    cfg["accounts"] = {}
                    cfg["accountsM"] = {}
                    with open(MEGAMU_CONFIG_INI, "w", encoding="utf-8") as f:
                        json.dump(cfg, f, ensure_ascii=False, separators=(",", ":"))
                    info["dashboard_cleared"] = True
            except Exception as e:
                info["error"] = f"config.ini: {e}"

        if reopen_dashboard and also_clear_dashboard and not info.get("error"):
            info["dashboard_reopened"] = open_dashboard()
            if not info["dashboard_reopened"]:
                info["error"] = f"Không tìm thấy Dashboard: {DASHBOARD_PATH}"
    except Exception as e:
        info["error"] = str(e)
    info["after"] = get_saved_account_usernames()
    return info


def load_autoclick_store():
    """
    File riêng cho Auto Click:
    {
      "points": [{"x": int, "y": int}, ...],
      "delay_between": float,
      "run_seconds": float
    }
    """
    data = load_json(AUTOCLICK_FILE, None)
    if not isinstance(data, dict):
        data = {}
    points = []
    for pt in data.get("points") or []:
        if not isinstance(pt, dict):
            continue
        try:
            points.append({"x": int(pt["x"]), "y": int(pt["y"])})
        except Exception:
            continue
    try:
        delay_between = float(data.get("delay_between", 0.5))
    except Exception:
        delay_between = 0.5
    try:
        run_seconds = float(data.get("run_seconds", 30.0))
    except Exception:
        run_seconds = 30.0
    return {
        "points": points,
        "delay_between": max(0.05, delay_between),
        "run_seconds": max(1.0, run_seconds),
    }


def save_autoclick_store(store):
    payload = {
        "points": [
            {"x": int(p["x"]), "y": int(p["y"])}
            for p in (store.get("points") or [])
            if isinstance(p, dict) and "x" in p and "y" in p
        ],
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
        self._license_info = lic

        self.accounts = load_accounts()
        self.coords_store = load_coords_store()
        self.autoclick_store = load_autoclick_store()

        nb = ttk.Notebook(self)
        nb.grid(row=0, column=0, sticky="nsew")

        self.tab_launch = ttk.Frame(nb, padding=10)
        self.tab_accounts = ttk.Frame(nb, padding=10)
        self.tab_auto = ttk.Frame(nb, padding=10)
        self.tab_autoclick = ttk.Frame(nb, padding=10)
        nb.add(self.tab_launch, text="  Mở & Sắp xếp  ")
        nb.add(self.tab_accounts, text="  Tài khoản  ")
        nb.add(self.tab_auto, text="  Auto Login  ")
        nb.add(self.tab_autoclick, text="  Auto Click  ")

        self._build_launch_tab()
        self._build_accounts_tab()
        self._build_auto_tab()
        self._build_autoclick_tab()

        # Đồng bộ layout từ store
        self._sync_launch_from_active_layout()

        self.status = tk.StringVar(value="Sẵn sàng.")
        ttk.Label(self, textvariable=self.status, wraplength=620).grid(
            row=1, column=0, sticky="w", pady=(8, 0)
        )

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.bind("<F8>", self._on_f8)
        self.bind("<Escape>", self._on_escape)

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
        return layouts[name]

    def _sync_launch_from_active_layout(self):
        layout = self.active_layout()
        self.count_var.set(int(layout["count"]))
        self.cols_var.set(int(layout["cols"]))
        if hasattr(self, "layout_var"):
            self.layout_var.set(layout.get("name") or self.active_layout_name())
            self._refresh_slot_ui()

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

    # ----- Launch tab -----
    def _build_launch_tab(self):
        frm = self.tab_launch
        sw, sh = get_screen_size()

        ttk.Label(frm, text="Đường dẫn MEGAMU:", font=("", 9, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        self.path_var = tk.StringVar(value=MEGAMU_PATH)
        ttk.Entry(frm, textvariable=self.path_var, width=64).grid(
            row=1, column=0, columnspan=4, sticky="ew", pady=(2, 8)
        )

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
        ttk.Label(opts, text="Số cột:").grid(row=0, column=2, sticky="w")
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

        margin = ttk.LabelFrame(frm, text=" Lề (px) ", padding=8)
        margin.grid(row=3, column=0, columnspan=4, sticky="ew", pady=(8, 0))
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
        saved.grid(row=4, column=0, columnspan=4, sticky="ew", pady=(8, 0))

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
        btns.grid(row=5, column=0, columnspan=4, sticky="w", pady=(10, 0))
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
        presets.grid(row=6, column=0, columnspan=4, sticky="w", pady=(8, 0))
        ttk.Label(presets, text="Preset:").pack(side="left")
        for label, n, c in [("2x2", 4, 2), ("3x2", 6, 3), ("3x3", 9, 3), ("4x3", 12, 4)]:
            ttk.Button(
                presets, text=label, width=6, command=lambda n=n, c=c: self.apply_preset(n, c)
            ).pack(side="left", padx=3)

        ttk.Label(
            frm,
            text=(
                f"Màn hình {sw}x{sh}  |  AccountList: "
                r"HKCU\Software\MEGAMU\MEGAMU"
            ),
            foreground="#555",
        ).grid(row=7, column=0, sticky="w", pady=(8, 0))

        self.refresh_saved_accounts()

    # ----- Accounts tab -----
    def _build_accounts_tab(self):
        frm = self.tab_accounts

        cols = ("user", "pass")
        self.acc_tree = ttk.Treeview(frm, columns=cols, show="headings", height=12)
        self.acc_tree.heading("user", text="Tài khoản")
        self.acc_tree.heading("pass", text="Mật khẩu")
        self.acc_tree.column("user", width=220)
        self.acc_tree.column("pass", width=220)
        self.acc_tree.grid(row=0, column=0, columnspan=4, sticky="nsew")
        self.acc_tree.bind("<<TreeviewSelect>>", self._on_acc_select)

        sb = ttk.Scrollbar(frm, orient="vertical", command=self.acc_tree.yview)
        self.acc_tree.configure(yscrollcommand=sb.set)
        sb.grid(row=0, column=4, sticky="ns")

        ttk.Label(frm, text="User:").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.user_var = tk.StringVar()
        ttk.Entry(frm, textvariable=self.user_var, width=24).grid(
            row=1, column=1, sticky="w", pady=(8, 0)
        )
        ttk.Label(frm, text="Pass:").grid(row=1, column=2, sticky="w", padx=(8, 0), pady=(8, 0))
        self.pass_var = tk.StringVar()
        ttk.Entry(frm, textvariable=self.pass_var, width=24, show="*").grid(
            row=1, column=3, sticky="w", pady=(8, 0)
        )

        bf = ttk.Frame(frm)
        bf.grid(row=2, column=0, columnspan=4, sticky="w", pady=(8, 0))
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
                "Thứ tự trên→dưới = ô 1, ô 2, ô 3... "
                "Ít hơn số cửa sổ thì các ô còn lại để trống (không login)."
            ),
            foreground="#555",
            justify="left",
        ).grid(row=3, column=0, columnspan=4, sticky="w", pady=(10, 0))

        self._refresh_acc_tree()

    def _refresh_acc_tree(self):
        for i in self.acc_tree.get_children():
            self.acc_tree.delete(i)
        for acc in self.accounts:
            shown_pass = "*" * min(len(acc.get("password", "")), 12) or ""
            self.acc_tree.insert("", "end", values=(acc.get("username", ""), shown_pass))

    def _on_acc_select(self, _event=None):
        sel = self.acc_tree.selection()
        if not sel:
            return
        idx = self.acc_tree.index(sel[0])
        if 0 <= idx < len(self.accounts):
            self.user_var.set(self.accounts[idx].get("username", ""))
            self.pass_var.set(self.accounts[idx].get("password", ""))

    def acc_add(self):
        u = self.user_var.get().strip()
        p = self.pass_var.get()
        if not u:
            messagebox.showwarning("Thiếu dữ liệu", "Nhập tài khoản.")
            return
        self.accounts.append({"username": u, "password": p})
        self.user_var.set("")
        self.pass_var.set("")
        self._refresh_acc_tree()
        save_accounts(self.accounts)
        self.status.set(f"Đã thêm tài khoản. Tổng: {len(self.accounts)}")

    def acc_edit(self):
        sel = self.acc_tree.selection()
        if not sel:
            return
        idx = self.acc_tree.index(sel[0])
        u = self.user_var.get().strip()
        p = self.pass_var.get()
        if not u:
            messagebox.showwarning("Thiếu dữ liệu", "Nhập tài khoản.")
            return
        self.accounts[idx] = {"username": u, "password": p}
        self._refresh_acc_tree()
        save_accounts(self.accounts)
        self.status.set(f"Đã sửa tài khoản #{idx + 1}")

    def acc_delete(self):
        sel = self.acc_tree.selection()
        if not sel:
            return
        idx = self.acc_tree.index(sel[0])
        del self.accounts[idx]
        self._refresh_acc_tree()
        save_accounts(self.accounts)

    def acc_move(self, delta):
        sel = self.acc_tree.selection()
        if not sel:
            return
        idx = self.acc_tree.index(sel[0])
        j = idx + delta
        if j < 0 or j >= len(self.accounts):
            return
        self.accounts[idx], self.accounts[j] = self.accounts[j], self.accounts[idx]
        self._refresh_acc_tree()
        kids = self.acc_tree.get_children()
        self.acc_tree.selection_set(kids[j])
        save_accounts(self.accounts)

    def acc_save(self):
        save_accounts(self.accounts)
        self.status.set(f"Đã lưu {len(self.accounts)} tài khoản.")

    # ----- Auto login tab -----
    def _build_auto_tab(self):
        frm = self.tab_auto

        top = ttk.LabelFrame(frm, text=" Hồ sơ layout (mỗi kích thước lưới 1 bộ tọa độ) ", padding=8)
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

        self.layout_status = tk.StringVar(value="")
        ttk.Label(top, textvariable=self.layout_status, foreground="#055").grid(
            row=1, column=0, columnspan=4, sticky="w", pady=(6, 0)
        )

        # Slot list
        mid = ttk.LabelFrame(frm, text=" Tọa độ theo từng ô cửa sổ ", padding=8)
        mid.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(8, 0))

        self.slot_tree = ttk.Treeview(
            mid,
            columns=("slot", "status", "account", "password", "login"),
            show="headings",
            height=7,
        )
        self.slot_tree.heading("slot", text="Ô")
        self.slot_tree.heading("status", text="Trạng thái")
        self.slot_tree.heading("account", text="Account")
        self.slot_tree.heading("password", text="Password")
        self.slot_tree.heading("login", text="Login")
        self.slot_tree.column("slot", width=40, anchor="center")
        self.slot_tree.column("status", width=90, anchor="center")
        self.slot_tree.column("account", width=120)
        self.slot_tree.column("password", width=120)
        self.slot_tree.column("login", width=120)
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
                "Thiếu tài khoản thì ô đó bỏ qua (để trống). Chỉ login các ô có TK + đã ghi tọa độ."
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
        self.layout_status.set(
            f"Layout {name}: đã ghi đủ {ready}/{total} ô  |  file: click_coords.json"
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
            self.slot_tree.insert(
                "",
                "end",
                iid=str(i),
                values=(
                    i + 1,
                    status,
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
        # Auto Click controls (có thể chưa tạo nếu lỗi UI)
        for attr in (
            "btn_ac_pick",
            "btn_ac_clear",
            "btn_ac_start",
            "btn_ac_refresh",
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

    def tile_rects(self, count):
        sw, sh = get_screen_size()
        cols, rows = calc_grid(count, self.cols_var.get() if self.cols_var.get() > 0 else None)
        ml, mt = self.margin_left.get(), self.margin_top.get()
        mr, mb = self.margin_right.get(), self.margin_bottom.get()
        gap = self.gap.get()
        usable_w = max(100, sw - ml - mr - gap * max(0, cols - 1))
        usable_h = max(100, sh - mt - mb - gap * max(0, rows - 1))
        cell_w = max(200, usable_w // cols)
        cell_h = max(150, usable_h // rows)
        rects = []
        for i in range(count):
            col, row = i % cols, i // cols
            x = ml + col * (cell_w + gap)
            y = mt + row * (cell_h + gap)
            rects.append((x, y, cell_w, cell_h))
        return rects, cols, rows

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
        if not os.path.isfile(path):
            messagebox.showerror("Không tìm thấy", path)
            return

        # gắn hồ sơ layout theo cấu hình hiện tại
        cols = int(self.cols_var.get()) if int(self.cols_var.get()) > 0 else math.ceil(math.sqrt(count))
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

        self.set_busy(True, f"Đang mở {count} cửa sổ ({name})...")

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
            self._launch_worker(path, count)

        threading.Thread(target=worker, daemon=True).start()

    def _launch_worker(self, path, count):
        delay = float(self.delay_var.get())
        wait = float(self.wait_var.get())
        before = set(list_game_hwnds())
        launched = 0
        for i in range(count):
            self.after(0, lambda i=i: self.status.set(f"Đang mở {i + 1}/{count}..."))
            try:
                subprocess.Popen([path], cwd=MEGAMU_DIR)
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

        rects, cols, rows = self.tile_rects(len(to_arrange))
        time.sleep(0.8)
        placed = arrange_hwnds(to_arrange, rects, retries=5, retry_delay=0.7)
        self.after(
            0,
            lambda: self.set_busy(
                False,
                f"Mở {launched}, sắp {placed}/{len(to_arrange)} (lưới {cols}x{rows}). "
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
        cols = int(self.cols_var.get()) if int(self.cols_var.get()) > 0 else math.ceil(math.sqrt(count))
        name = layout_name(count, cols)
        self.ensure_layout(name, count, cols)
        self.count_var.set(count)
        self.cols_var.set(cols)
        if hasattr(self, "layout_var"):
            self.layout_var.set(name)
            self._refresh_slot_ui()

        self.set_busy(True, f"Đang sắp {count} cửa sổ ({name})...")

        def worker():
            current = list_game_hwnds()
            rects, cols, rows = self.tile_rects(len(current))
            placed = arrange_hwnds(current, rects, retries=5, retry_delay=0.5)
            self.after(
                0,
                lambda: self.set_busy(
                    False, f"Đã sắp {placed}/{len(current)} cửa sổ ({cols}x{rows})."
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
        """Account theo thứ tự danh sách; thiếu hoặc user trống = ô để trống."""
        if index < 0 or index >= len(self.accounts):
            return None
        acc = self.accounts[index]
        username = (acc.get("username") or "").strip()
        if not username:
            return None
        return {"username": username, "password": acc.get("password") or ""}

    def _build_login_plan(self, hwnds):
        """
        Ghép ô/cửa sổ/account theo index.
        Ô không có account → bỏ qua (để trống).
        Chỉ yêu cầu tọa độ cho các ô sẽ login.
        """
        layout = self.active_layout()
        slot_count = layout["count"]
        plan = []  # list of dicts: index, hwnd, acc, slot
        skipped_empty = []
        missing_coords = []
        missing_window = []

        max_i = max(len(hwnds), len(self.accounts), slot_count)
        for i in range(max_i):
            acc = self._account_at(i)
            if not acc:
                if i < slot_count:
                    skipped_empty.append(i + 1)
                continue

            # Có account → cần cửa sổ + tọa độ tương ứng
            if i >= len(hwnds):
                missing_window.append(i + 1)
                continue
            if i >= slot_count or i >= len(layout["slots"]):
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

        return plan, skipped_empty, missing_coords, missing_window

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
        if not acc:
            messagebox.showinfo(
                "Ô trống",
                f"Ô {idx + 1} không có tài khoản trong danh sách (để trống).\n"
                f"Thêm account ở dòng #{idx + 1} nếu muốn login ô này.",
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
        self.set_busy(True, f"Thử login ô {idx + 1} ({acc['username']})...")
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
                msg = f"Đã thử ô {idx + 1}: {acc['username']} (mode={self._input_mode()})"
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
        plan, skipped_empty, missing_coords, missing_window = self._build_login_plan(hwnds)

        if missing_coords:
            messagebox.showwarning(
                "Thiếu tọa độ",
                f"Các ô có tài khoản nhưng chưa ghi tọa độ: {missing_coords}\n"
                "Ghi từng ô, hoặc ghi ô 1 rồi 'Chép ô 1 → tất cả ô'.\n"
                f"Các ô không có TK sẽ bỏ qua: {skipped_empty or '—'}",
            )
            return

        if missing_window:
            messagebox.showwarning(
                "Thiếu cửa sổ",
                f"Có tài khoản ở dòng {missing_window} nhưng chưa đủ cửa sổ game đang mở.\n"
                f"Đang mở {len(hwnds)} cửa sổ.",
            )
            return

        if not plan:
            messagebox.showinfo(
                "Không có ô để login",
                "Không có cặp (tài khoản + cửa sổ + tọa độ) nào để chạy.\n"
                "Thêm tài khoản theo thứ tự trên→dưới, hoặc mở thêm cửa sổ.",
            )
            return

        skip_txt = (
            f"\nÔ để trống (không có TK): {skipped_empty}" if skipped_empty else ""
        )
        if not messagebox.askyesno(
            "Xác nhận Auto Login",
            f"Layout {layout.get('name')}\n"
            f"Sẽ login {len(plan)} ô: "
            + ", ".join(f"#{p['index'] + 1}={p['acc']['username']}" for p in plan)
            + skip_txt
            + "\nTiếp tục?",
        ):
            return

        self._stop_login = False
        self.set_busy(
            True,
            f"Auto login {len(plan)} ô (layout {layout.get('name')})...",
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
    def _build_autoclick_tab(self):
        frm = self.tab_autoclick
        ttk.Label(
            frm,
            text=(
                "Chức năng riêng: chọn điểm click tuyệt đối trên màn hình theo số cửa sổ "
                "MEGAMU đang mở. Mỗi lần click chuột trái = 1 điểm, đến đủ số cửa sổ thì dừng chọn."
            ),
            wraplength=620,
            justify="left",
        ).grid(row=0, column=0, columnspan=4, sticky="w")

        info = ttk.LabelFrame(frm, text=" Số điểm ", padding=8)
        info.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(10, 0))
        self.ac_window_count_var = tk.StringVar(value="Cửa sổ đang mở: 0")
        ttk.Label(info, textvariable=self.ac_window_count_var).grid(
            row=0, column=0, sticky="w"
        )
        self.btn_ac_refresh = ttk.Button(
            info, text="Làm mới số cửa sổ", width=18, command=self.refresh_ac_window_count
        )
        self.btn_ac_refresh.grid(row=0, column=1, padx=(12, 0))

        timing = ttk.LabelFrame(frm, text=" Thời gian ", padding=8)
        timing.grid(row=2, column=0, columnspan=4, sticky="ew", pady=(10, 0))
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
        pts.grid(row=3, column=0, columnspan=4, sticky="nsew", pady=(10, 0))
        self.ac_list = tk.Listbox(pts, height=10, width=72, exportselection=False)
        self.ac_list.grid(row=0, column=0, columnspan=4, sticky="nsew")
        pts.columnconfigure(0, weight=1)

        btns = ttk.Frame(frm)
        btns.grid(row=4, column=0, columnspan=4, sticky="w", pady=(10, 0))
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
            value="Esc để hủy khi đang chọn điểm. F8 không dùng ở tab này."
        )
        ttk.Label(frm, textvariable=self.ac_status_var, wraplength=620).grid(
            row=5, column=0, columnspan=4, sticky="w", pady=(10, 0)
        )

        self.refresh_ac_window_count()
        self._refresh_ac_list()

    def refresh_ac_window_count(self):
        n = len(list_game_hwnds())
        self.ac_window_count_var.set(f"Cửa sổ đang mở: {n}  →  cần chọn {n} điểm")
        return n

    def _refresh_ac_list(self):
        if not hasattr(self, "ac_list"):
            return
        self.ac_list.delete(0, tk.END)
        points = self.autoclick_store.get("points") or []
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
        self.autoclick_store["points"] = []
        save_autoclick_store(self.autoclick_store)
        self._refresh_ac_list()
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

        # xóa điểm cũ rồi bắt đầu chọn
        self.autoclick_store["points"] = []
        save_autoclick_store(self.autoclick_store)
        self._refresh_ac_list()

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
        if user32.GetAsyncKeyState(VK_ESCAPE) & 0x0001:
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
            self.autoclick_store.setdefault("points", []).append({"x": x, "y": y})
            save_autoclick_store(self.autoclick_store)
            self._refresh_ac_list()

            got = len(self.autoclick_store["points"])
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
        points = list(self.autoclick_store.get("points") or [])
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
            f"Sẽ click lần lượt {len(points)} điểm,\n"
            f"cách nhau {delay:.2f}s, chạy trong {run_seconds:.0f}s rồi tự dừng.\n"
            "Có thể bấm Dừng bất cứ lúc nào.\n\nTiếp tục?",
        ):
            return

        self._ac_running = True
        self._stop_autoclick = False
        self.set_busy(True, f"Auto Click: 0s / {run_seconds:.0f}s...")
        self.btn_ac_stop.configure(state="normal")
        # giữ nút Dừng bấm được khi busy
        try:
            self.btn_ac_stop.configure(state="normal")
        except Exception:
            pass

        def worker():
            start = time.time()
            clicks = 0
            idx = 0
            err = None
            try:
                while not self._stop_autoclick:
                    elapsed = time.time() - start
                    if elapsed >= run_seconds:
                        break
                    pt = points[idx % len(points)]
                    mouse_click_screen(pt["x"], pt["y"], settle=0.05, hwnd=None)
                    clicks += 1
                    idx += 1
                    self.after(
                        0,
                        lambda e=elapsed, c=clicks, i=idx: self.status.set(
                            f"Auto Click: {e:.1f}s/{run_seconds:.0f}s | "
                            f"click #{c} tại điểm {(i - 1) % len(points) + 1}/{len(points)}"
                        ),
                    )
                    # ngủ theo delay, nhưng vẫn kiểm tra stop / hết giờ
                    end_sleep = time.time() + delay
                    while time.time() < end_sleep:
                        if self._stop_autoclick:
                            break
                        if time.time() - start >= run_seconds:
                            break
                        time.sleep(0.05)
            except Exception as e:
                err = str(e)

            def done():
                self._ac_running = False
                self.btn_ac_stop.configure(state="disabled")
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

    def on_ac_stop(self):
        self._stop_autoclick = True
        self.status.set("Đang dừng Auto Click...")

    def on_close(self):
        self._capture_target = None
        self._wizard_queue = []
        self._stop_login = True
        self._stop_autoclick = True
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
        self.destroy()


def main():
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

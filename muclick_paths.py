# -*- coding: utf-8 -*-
"""Đường dẫn cài đặt / dữ liệu user cho MuClick."""

from __future__ import annotations

import os
import shutil
import sys


APP_NAME = "MuClick"
APP_VERSION = "1.0.0"


def is_frozen():
    return bool(getattr(sys, "frozen", False))


def install_dir():
    """Thư mục chứa exe (frozen) hoặc thư mục source."""
    if is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def exe_path():
    if is_frozen():
        return os.path.abspath(sys.executable)
    return os.path.join(install_dir(), "MuClick.exe")


def user_data_dir():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    path = os.path.join(base, APP_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def _legacy_dir():
    """Thư mục source / cạnh exe — nơi từng lưu json trước khi migrate."""
    return install_dir()


def migrate_user_files(filenames):
    """
    Copy 1 lần file cũ từ thư mục cài/source → %APPDATA%\\MuClick
    nếu đích chưa có.
    """
    src_dir = _legacy_dir()
    dst_dir = user_data_dir()
    for name in filenames:
        src = os.path.join(src_dir, name)
        dst = os.path.join(dst_dir, name)
        if os.path.isfile(dst):
            continue
        if os.path.isfile(src):
            try:
                shutil.copy2(src, dst)
            except Exception:
                pass


def data_path(filename):
    return os.path.join(user_data_dir(), filename)

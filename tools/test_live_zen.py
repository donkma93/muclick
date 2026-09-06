import sys
import os
import time
import json
import ctypes
from ctypes import wintypes
import cv2
import numpy as np

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import megamu_launcher as launcher
from muclick_paths import data_path

print("=== KIEM TRA DOC ZEN TRUC TIEP TU CUA SO GAME ===")

hwnds = launcher.list_game_hwnds()
print(f"Tìm thấy {len(hwnds)} cửa sổ MEGAMU đang chạy:")
for idx, h in enumerate(hwnds):
    t = launcher.get_window_text(h)
    l, top, w, ht = launcher.get_window_rect(h)
    print(f"  [{idx + 1}] HWND={h} | Rect=({l}, {top}, {w}, {ht}) | Title='{t}'")

if not hwnds:
    print("Không có cửa sổ game nào đang chạy!")
    sys.exit(0)

accounts_file = data_path("accounts.json")
with open(accounts_file, "r", encoding="utf-8") as f:
    store = json.load(f)

active_group = store.get("active_group", "Chơi game")
accs = store.get("groups", {}).get(active_group, [])
print(f"\nNhóm tài khoản đang chọn: [{active_group}] (có {len(accs)} tài khoản)")

results = []
for idx, h in enumerate(hwnds):
    title = launcher.get_window_text(h)
    info = launcher.parse_game_window_title(title)
    char_name = info.get("char_name") or f"Cửa sổ {idx + 1}"
    print(f"\n--- Đang xử lý Cửa sổ {idx + 1}/{len(hwnds)}: [{char_name}] ---")

    # 1. Focus
    launcher.focus_window(h)
    time.sleep(0.25)

    # 2. Bấm V
    launcher.release_modifiers()
    launcher.tap_vk(ord("V"), pause=0.10)
    time.sleep(0.50)

    # 3. Chụp ảnh
    img = launcher.capture_window_bgr(h)
    if img is not None:
        raw_path = f"debug_slot_{idx + 1}_raw.png"
        cv2.imwrite(raw_path, img)
        print(f"  -> Đã lưu ảnh chụp cửa sổ vào '{raw_path}' (kích thước: {img.shape})")

    zen_val = launcher.extract_zen_from_image(img)
    if zen_val is None and img is not None:
        # Thử lại nếu V bị đóng
        print("  -> Chưa đọc được, thử bấm 'V' lần 2...")
        launcher.tap_vk(ord("V"), pause=0.10)
        time.sleep(0.50)
        img2 = launcher.capture_window_bgr(h)
        if img2 is not None:
            cv2.imwrite(f"debug_slot_{idx + 1}_retry.png", img2)
        zen_val = launcher.extract_zen_from_image(img2)

    # 4. Đóng V
    launcher.tap_vk(ord("V"), pause=0.10)
    launcher.release_modifiers()

    print(f"  -> KẾT QUẢ ĐỌC ZEN: {launcher.format_zen(zen_val) if zen_val is not None else 'KHÔNG ĐỌC ĐƯỢC'}")
    results.append((h, char_name, zen_val))

# Cập nhật vào accounts
hwnd_map = {r[1].lower(): r[2] for r in results if r[2] is not None}
updated_count = 0
for idx, acc in enumerate(accs):
    cname = (acc.get("char_name") or "").lower()
    z = None
    if cname and cname in hwnd_map:
        z = hwnd_map[cname]
    elif idx < len(results) and results[idx][2] is not None:
        z = results[idx][2]

    if z is not None:
        acc["zen"] = z
        updated_count += 1
        print(f"  [Cập nhật] {acc.get('username')} ({acc.get('char_name')}): {launcher.format_zen(z)} Zen")

with open(accounts_file, "w", encoding="utf-8") as f:
    json.dump(store, f, ensure_ascii=False, indent=2)

print(f"\n=== HOÀN TẤT: Đã cập nhật {updated_count}/{len(accs)} tài khoản trong [{active_group}] ===")

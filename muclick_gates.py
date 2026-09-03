# -*- coding: utf-8 -*-
"""
Gate trước khi vào app: bắt buộc update GitHub Release, rồi license key.
Trả về True nếu được phép vào main UI; False nếu user thoát.

Worker thread chỉ đẩy kết quả vào queue; main thread poll bằng after()
(tránh RuntimeError: main thread is not in main loop).
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from muclick_github_license import (
    ADMIN_PASSWORD,
    LicenseOnlineError,
    activate_or_revalidate,
    create_and_push_license,
    is_admin_password,
    list_keys_summary,
    revalidate_saved,
)
from muclick_license import get_hwid, load_saved_license
from muclick_paths import APP_VERSION
from muclick_update import (
    UpdateCheckError,
    apply_update_and_exit,
    check_for_mandatory_update,
)


def _center(win, w=420, h=220):
    win.update_idletasks()
    sw = win.winfo_screenwidth()
    sh = win.winfo_screenheight()
    x = max(0, (sw - w) // 2)
    y = max(0, (sh - h) // 3)
    win.geometry(f"{w}x{h}+{x}+{y}")


def run_update_gate(root: tk.Tk) -> bool:
    """
    Kiểm tra GitHub release.
    True = tiếp tục (ok / bootstrap).
    False = user chọn thoát hoặc đang apply update (process sẽ exit).
    """
    result = {"ok": False}
    q: queue.Queue = queue.Queue()
    poll_job = {"id": None}

    dlg = tk.Toplevel(root)
    dlg.title(f"MuClick {APP_VERSION} — Cập nhật")
    dlg.resizable(False, False)
    # Root đang withdraw: không transient theo root ẩn (dễ làm dialog không hiện).
    dlg.attributes("-topmost", True)
    dlg.lift()
    dlg.focus_force()
    dlg.grab_set()
    _center(dlg, 460, 240)
    dlg.deiconify()

    status = tk.StringVar(value="Đang kiểm tra phiên bản trên GitHub...")
    detail = tk.StringVar(value="")
    progress = tk.DoubleVar(value=0.0)

    ttk.Label(dlg, textvariable=status, wraplength=420).pack(
        padx=16, pady=(16, 6), anchor="w"
    )
    ttk.Label(dlg, textvariable=detail, wraplength=420, foreground="#444").pack(
        padx=16, pady=(0, 8), anchor="w"
    )
    bar = ttk.Progressbar(dlg, maximum=100, variable=progress, mode="determinate")
    bar.pack(fill="x", padx=16, pady=(0, 10))

    btn_row = ttk.Frame(dlg)
    btn_row.pack(fill="x", padx=16, pady=(0, 12))

    btn_retry = ttk.Button(btn_row, text="Thử lại", width=12)
    btn_update = ttk.Button(btn_row, text="Cập nhật ngay", width=14)
    btn_exit = ttk.Button(btn_row, text="Thoát", width=10)
    btn_continue = ttk.Button(btn_row, text="Tiếp tục", width=12)

    def show_buttons(*buttons):
        for b in (btn_retry, btn_update, btn_exit, btn_continue):
            b.pack_forget()
        for b in buttons:
            b.pack(side="left", padx=(0, 8))

    def stop_poll():
        jid = poll_job.get("id")
        if jid is not None:
            try:
                dlg.after_cancel(jid)
            except Exception:
                pass
            poll_job["id"] = None

    def on_exit():
        result["ok"] = False
        stop_poll()
        dlg.destroy()

    btn_exit.configure(command=on_exit)

    state = {"release": None, "busy": False}

    def on_check_err(msg):
        state["busy"] = False
        status.set(
            "Không kiểm tra được phiên bản — bắt buộc có mạng để xác minh update."
        )
        detail.set(msg)
        show_buttons(btn_retry, btn_exit)

    def on_check_ok(info):
        state["busy"] = False
        st = info.get("status")
        if st == "ok":
            status.set("Đã ở phiên bản mới nhất.")
            detail.set(f"Local {info.get('local')}  |  Remote {info.get('remote')}")
            progress.set(100)
            result["ok"] = True
            dlg.after(250, dlg.destroy)
            return
        if st == "bootstrap":
            status.set("Chưa có Release trên GitHub — cho phép chạy bản đầu.")
            detail.set(f"Local {info.get('local')}")
            progress.set(100)
            result["ok"] = True
            dlg.after(400, dlg.destroy)
            return
        rel = info["release"]
        state["release"] = rel
        status.set("Bắt buộc cập nhật trước khi sử dụng.")
        detail.set(
            f"{info['local']}  →  {rel['version']} ({rel.get('tag')})\n"
            f"Asset: {rel.get('asset_name')}"
        )
        progress.set(0)
        show_buttons(btn_update, btn_exit)

    def on_update_err(msg):
        state["busy"] = False
        status.set("Cập nhật thất bại.")
        detail.set(msg)
        show_buttons(btn_retry, btn_update, btn_exit)

    def poll_queue():
        if not dlg.winfo_exists():
            return
        try:
            while True:
                kind, payload = q.get_nowait()
                if kind == "check_ok":
                    on_check_ok(payload)
                elif kind == "check_err":
                    on_check_err(payload)
                elif kind == "progress":
                    done, total = payload
                    pct = (done * 100.0 / total) if total else 0
                    progress.set(pct)
                    status.set(
                        f"Đang tải... {done // 1024} KB"
                        + (f" / {total // 1024} KB" if total else "")
                    )
                elif kind == "update_err":
                    on_update_err(payload)
        except queue.Empty:
            pass
        poll_job["id"] = dlg.after(50, poll_queue)

    def do_check():
        if state["busy"]:
            return
        state["busy"] = True
        status.set("Đang kiểm tra phiên bản trên GitHub...")
        detail.set(f"Bản hiện tại: {APP_VERSION}")
        progress.set(0)
        show_buttons(btn_exit)

        def worker():
            try:
                info = check_for_mandatory_update(APP_VERSION)
                q.put(("check_ok", info))
            except UpdateCheckError as e:
                q.put(("check_err", str(e)))
            except Exception as e:
                q.put(("check_err", f"Lỗi: {e}"))

        threading.Thread(target=worker, daemon=True).start()

    def do_update():
        rel = state.get("release")
        if not rel or state["busy"]:
            return
        state["busy"] = True
        status.set(f"Đang tải {rel['asset_name']}...")
        detail.set(rel["download_url"])
        show_buttons(btn_exit)

        def progress_cb(done, total):
            q.put(("progress", (done, total)))

        def worker():
            try:
                apply_update_and_exit(rel["download_url"], progress_cb=progress_cb)
            except SystemExit:
                raise
            except Exception as e:
                q.put(("update_err", str(e)))

        threading.Thread(target=worker, daemon=True).start()

    btn_retry.configure(command=do_check)
    btn_update.configure(command=do_update)
    btn_continue.configure(
        command=lambda: (result.__setitem__("ok", True), dlg.destroy())
    )

    dlg.protocol("WM_DELETE_WINDOW", on_exit)
    poll_job["id"] = dlg.after(50, poll_queue)
    dlg.after(80, do_check)
    dlg.wait_window()
    stop_poll()
    return bool(result["ok"])


def run_license_gate(root: tk.Tk) -> bool:
    """
    Kích hoạt / xác minh ONLINE (GitHub private + HWID).
    True nếu hợp lệ; False nếu user thoát.
    """
    result = {"ok": False, "info": None}
    q: queue.Queue = queue.Queue()
    poll_job = {"id": None}

    dlg = tk.Toplevel(root)
    dlg.title(f"MuClick {APP_VERSION} — Kích hoạt online")
    dlg.resizable(False, False)
    dlg.attributes("-topmost", True)
    dlg.lift()
    dlg.focus_force()
    dlg.grab_set()
    _center(dlg, 520, 320)
    dlg.deiconify()

    ttk.Label(
        dlg,
        text=(
            "Kích hoạt online — cần mạng.\n"
            "Mỗi key gắn 1 máy (HWID).\n"
            "Admin: nhập mật khẩu admin vào ô bên dưới để tạo & đẩy license lên Git."
        ),
        wraplength=480,
        justify="left",
    ).pack(padx=16, pady=(16, 6), anchor="w")

    hwid_short = get_hwid()[:16] + "…"
    status = tk.StringVar(value=f"HWID máy này: {hwid_short}")
    err_var = tk.StringVar(value="")
    key_var = tk.StringVar(value=(load_saved_license() or {}).get("key") or "")

    ttk.Label(dlg, textvariable=status, wraplength=480, foreground="#333").pack(
        padx=16, anchor="w"
    )

    ttk.Label(dlg, text="License key (hoặc mật khẩu admin)").pack(
        padx=16, pady=(10, 0), anchor="w"
    )
    entry = ttk.Entry(dlg, textvariable=key_var, width=60)
    entry.pack(padx=16, pady=(4, 6), fill="x")
    entry.focus_set()

    ttk.Label(dlg, textvariable=err_var, foreground="#a00", wraplength=480).pack(
        padx=16, anchor="w"
    )

    btn_row = ttk.Frame(dlg)
    btn_row.pack(fill="x", padx=16, pady=(14, 12))
    btn_activate = ttk.Button(btn_row, text="Kích hoạt / Xác minh", width=22)
    btn_retry = ttk.Button(btn_row, text="Thử lại", width=12)
    btn_exit = ttk.Button(btn_row, text="Thoát", width=10)
    btn_activate.pack(side="left", padx=(0, 8))
    btn_retry.pack(side="left", padx=(0, 8))
    btn_exit.pack(side="left")

    busy = {"v": False}

    def set_busy(v: bool):
        busy["v"] = v
        state = "disabled" if v else "normal"
        btn_activate.configure(state=state)
        btn_retry.configure(state=state)
        entry.configure(state=state)

    def stop_poll():
        jid = poll_job.get("id")
        if jid is not None:
            try:
                dlg.after_cancel(jid)
            except Exception:
                pass
            poll_job["id"] = None

    def on_exit():
        result["ok"] = False
        stop_poll()
        dlg.destroy()

    def finish_ok(info: dict):
        result["ok"] = True
        result["info"] = info
        exp = info.get("exp")
        exp_s = exp.isoformat() if hasattr(exp, "isoformat") else str(exp)
        messagebox.showinfo(
            "License OK",
            f"Hợp lệ đến {exp_s}\n"
            f"(còn {info.get('days_left')} ngày).\n"
            f"Key ID: {info.get('key_id') or '-'}",
            parent=dlg,
        )
        stop_poll()
        dlg.destroy()

    def on_fail(msg: str):
        set_busy(False)
        err_var.set(msg)
        status.set(f"HWID máy này: {hwid_short}")

    def poll_queue():
        if not dlg.winfo_exists():
            return
        try:
            while True:
                kind, payload = q.get_nowait()
                if kind == "ok":
                    finish_ok(payload)
                elif kind == "fail":
                    on_fail(payload)
        except queue.Empty:
            pass
        poll_job["id"] = dlg.after(50, poll_queue)

    def open_admin():
        # tạm nhả grab để admin dialog nhận focus
        try:
            dlg.grab_release()
        except Exception:
            pass
        run_admin_license_dialog(dlg)
        try:
            dlg.grab_set()
            dlg.lift()
        except Exception:
            pass
        key_var.set("")
        err_var.set("")
        status.set(f"HWID máy này: {hwid_short}")

    def run_online(prefer_saved: bool):
        if busy["v"]:
            return
        typed = (key_var.get() or "").strip()
        # Admin password → mở UI tạo license (không kích hoạt app)
        if (not prefer_saved) and is_admin_password(typed):
            open_admin()
            return

        set_busy(True)
        err_var.set("")
        status.set("Đang xác minh online với GitHub…")

        key_snapshot = typed

        def worker():
            try:
                if prefer_saved and load_saved_license():
                    info = revalidate_saved()
                else:
                    info = activate_or_revalidate(key=key_snapshot)
                q.put(("ok", info))
            except LicenseOnlineError as e:
                q.put(("fail", str(e)))
            except Exception as e:
                q.put(("fail", f"Lỗi: {e}"))

        threading.Thread(target=worker, daemon=True).start()

    btn_exit.configure(command=on_exit)
    btn_activate.configure(command=lambda: run_online(prefer_saved=False))
    btn_retry.configure(command=lambda: run_online(prefer_saved=True))
    dlg.bind("<Return>", lambda _e: run_online(prefer_saved=False))
    dlg.protocol("WM_DELETE_WINDOW", on_exit)

    poll_job["id"] = dlg.after(50, poll_queue)
    # Chỉ auto-revalidate nếu cache không phải admin password
    saved = load_saved_license()
    if saved and not is_admin_password(saved.get("key") or ""):
        dlg.after(120, lambda: run_online(prefer_saved=True))

    dlg.wait_window()
    stop_poll()
    if result["ok"]:
        root._license_info = result["info"]  # type: ignore[attr-defined]
    return bool(result["ok"])


def run_admin_license_dialog(parent: tk.Misc) -> None:
    """
    UI Admin: tạo key + đẩy lên GitHub repo muclick-license.
    Không mở quyền dùng app — chỉ quản lý key.
    """
    q: queue.Queue = queue.Queue()
    poll_job = {"id": None}

    win = tk.Toplevel(parent)
    win.title(f"MuClick {APP_VERSION} — Admin License")
    win.resizable(False, False)
    win.attributes("-topmost", True)
    win.lift()
    win.focus_force()
    win.grab_set()
    _center(win, 560, 460)
    win.deiconify()

    ttk.Label(
        win,
        text=(
            f"Admin OK. Repo: donkma93/muclick → licenses/keys.json\n"
            f"Mật khẩu admin: {ADMIN_PASSWORD} (chỉ dùng trên máy bạn).\n"
            f"Cảnh báo: repo đang public — key trong file có thể bị người khác đọc."
        ),
        wraplength=520,
        justify="left",
    ).pack(padx=14, pady=(12, 6), anchor="w")

    form = ttk.LabelFrame(win, text=" Tạo license mới ", padding=8)
    form.pack(fill="x", padx=14, pady=(4, 6))

    days_var = tk.IntVar(value=30)
    exp_var = tk.StringVar(value="")
    note_var = tk.StringVar(value="")
    use_exp = tk.BooleanVar(value=False)
    status = tk.StringVar(value="Điền thông tin rồi bấm Tạo & đẩy lên Git.")
    last_key = tk.StringVar(value="")

    ttk.Label(form, text="Số ngày còn hạn").grid(row=0, column=0, sticky="w")
    sp_days = ttk.Spinbox(form, from_=1, to=3650, textvariable=days_var, width=8)
    sp_days.grid(row=0, column=1, sticky="w", padx=(8, 12))

    ttk.Checkbutton(
        form, text="Dùng ngày hết hạn cụ thể (YYYY-MM-DD)", variable=use_exp
    ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))
    ttk.Entry(form, textvariable=exp_var, width=16).grid(
        row=1, column=2, sticky="w", pady=(6, 0)
    )

    ttk.Label(form, text="Ghi chú").grid(row=2, column=0, sticky="w", pady=(6, 0))
    ttk.Entry(form, textvariable=note_var, width=36).grid(
        row=2, column=1, columnspan=2, sticky="w", padx=(8, 0), pady=(6, 0)
    )

    list_fr = ttk.LabelFrame(win, text=" Key trên Git (tóm tắt) ", padding=8)
    list_fr.pack(fill="both", expand=True, padx=14, pady=(4, 6))
    lb = tk.Listbox(list_fr, height=8, width=72)
    lb.pack(fill="both", expand=True)

    ttk.Label(win, textvariable=status, wraplength=520).pack(
        padx=14, pady=(0, 4), anchor="w"
    )
    ttk.Label(win, textvariable=last_key, wraplength=520, foreground="#053").pack(
        padx=14, pady=(0, 6), anchor="w"
    )

    btns = ttk.Frame(win)
    btns.pack(fill="x", padx=14, pady=(0, 12))
    btn_create = ttk.Button(btns, text="Tạo & đẩy lên Git", width=20)
    btn_refresh = ttk.Button(btns, text="Làm mới danh sách", width=18)
    btn_copy = ttk.Button(btns, text="Copy key vừa tạo", width=16)
    btn_close = ttk.Button(btns, text="Đóng", width=10)
    btn_create.pack(side="left", padx=(0, 6))
    btn_refresh.pack(side="left", padx=(0, 6))
    btn_copy.pack(side="left", padx=(0, 6))
    btn_close.pack(side="left")

    busy = {"v": False}

    def set_busy(v: bool):
        busy["v"] = v
        st = "disabled" if v else "normal"
        for b in (btn_create, btn_refresh, btn_copy):
            b.configure(state=st)

    def stop_poll():
        jid = poll_job.get("id")
        if jid is not None:
            try:
                win.after_cancel(jid)
            except Exception:
                pass
            poll_job["id"] = None

    def fill_list(rows: list):
        lb.delete(0, tk.END)
        if not rows:
            lb.insert(tk.END, "(chưa có key trên repo)")
            return
        for r in rows:
            flag = "ON" if r.get("enabled", True) else "OFF"
            lb.insert(
                tk.END,
                f"{r.get('id')} | exp={r.get('exp')} | "
                f"bound={r.get('bound')}/{r.get('max_devices')} | "
                f"{flag} | {r.get('note')}",
            )

    def poll_queue():
        if not win.winfo_exists():
            return
        try:
            while True:
                kind, payload = q.get_nowait()
                if kind == "list_ok":
                    set_busy(False)
                    fill_list(payload)
                    status.set(f"Đã tải {len(payload)} key từ Git.")
                elif kind == "create_ok":
                    set_busy(False)
                    entry = payload
                    last_key.set(f"Key mới: {entry.get('key')}")
                    status.set(
                        f"Đã đẩy {entry.get('id')} (exp={entry.get('exp')}) lên Git."
                    )
                    messagebox.showinfo(
                        "Đã tạo license",
                        f"ID: {entry.get('id')}\n"
                        f"Key:\n{entry.get('key')}\n\n"
                        f"Hết hạn: {entry.get('exp')}\n"
                        "Copy key này gửi cho khách.",
                        parent=win,
                    )
                    # refresh list
                    do_refresh()
                elif kind == "err":
                    set_busy(False)
                    status.set(payload)
                    messagebox.showerror("Admin lỗi", payload, parent=win)
        except queue.Empty:
            pass
        poll_job["id"] = win.after(50, poll_queue)

    def do_refresh():
        if busy["v"]:
            return
        set_busy(True)
        status.set("Đang tải danh sách key từ Git…")

        def worker():
            try:
                rows = list_keys_summary()
                q.put(("list_ok", rows))
            except Exception as e:
                q.put(("err", str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def do_create():
        if busy["v"]:
            return
        set_busy(True)
        status.set("Đang tạo key và đẩy lên Git…")
        note = note_var.get().strip()
        if use_exp.get():
            days = None
            exp = exp_var.get().strip()
        else:
            days = int(days_var.get())
            exp = None

        def worker():
            try:
                entry = create_and_push_license(days=days, exp=exp, note=note)
                q.put(("create_ok", entry))
            except Exception as e:
                q.put(("err", str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def do_copy():
        key = last_key.get().replace("Key mới: ", "").strip()
        if not key:
            messagebox.showwarning("Chưa có key", "Hãy tạo key trước.", parent=win)
            return
        try:
            win.clipboard_clear()
            win.clipboard_append(key)
            status.set("Đã copy key vào clipboard.")
        except Exception as e:
            messagebox.showerror("Copy lỗi", str(e), parent=win)

    def on_close():
        stop_poll()
        win.destroy()

    btn_create.configure(command=do_create)
    btn_refresh.configure(command=do_refresh)
    btn_copy.configure(command=do_copy)
    btn_close.configure(command=on_close)
    win.protocol("WM_DELETE_WINDOW", on_close)

    poll_job["id"] = win.after(50, poll_queue)
    win.after(80, do_refresh)
    win.wait_window()


def run_startup_gates() -> tuple[bool, object | None]:
    """
    Tạo root ẩn, chạy update + license.
    Trả về (allowed, root) — nếu allowed=False thì root đã destroy.
    """
    root = tk.Tk()
    root.withdraw()
    try:
        if not run_update_gate(root):
            root.destroy()
            return False, None
        if not run_license_gate(root):
            root.destroy()
            return False, None
        return True, root
    except Exception:
        try:
            root.destroy()
        except Exception:
            pass
        raise

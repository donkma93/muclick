# -*- coding: utf-8 -*-
"""
Tạo license key random cho MuClick (admin).

Key phải được đẩy lên repo private muclick-license (licenses/keys.json)
bằng tools/push_license_key.py, Admin UI (mật khẩu donpv93), hoặc sửa tay trên GitHub.

Ví dụ:
  python tools/gen_license_key.py --exp 2026-12-31 --note khach-A
  python tools/gen_license_key.py --days 30 --push
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from muclick_license import generate_key  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="Generate MuClick online license key")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--days", type=int, help="Số ngày còn hạn kể từ hôm nay")
    g.add_argument("--exp", type=str, help="Ngày hết hạn YYYY-MM-DD")
    ap.add_argument("--note", type=str, default="", help="Ghi chú")
    ap.add_argument("--id", type=str, default="", help="ID key (vd K001)")
    ap.add_argument(
        "--push",
        action="store_true",
        help="Đẩy luôn lên GitHub repo muclick-license",
    )
    args = ap.parse_args()

    if args.days is not None:
        if args.days < 0:
            print("days phải >= 0", file=sys.stderr)
            sys.exit(1)
        exp = date.today() + timedelta(days=args.days)
    else:
        exp = date.fromisoformat(args.exp)

    key = generate_key()
    print(key)
    print(f"exp={exp.isoformat()} note={args.note!r}")

    if args.push:
        from muclick_github_license import append_key_to_repo  # noqa: E402

        entry = append_key_to_repo(
            key=key,
            exp=exp.isoformat(),
            note=args.note,
            key_id=args.id or None,
        )
        print(f"Pushed id={entry.get('id')} → donkma93/muclick-license licenses/keys.json")
    else:
        print(
            "Chưa push. Chạy thêm --push hoặc:\n"
            f'  python tools/push_license_key.py --key "{key}" --exp {exp.isoformat()} '
            f'--note "{args.note}"'
        )


if __name__ == "__main__":
    main()

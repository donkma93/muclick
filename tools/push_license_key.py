# -*- coding: utf-8 -*-
"""
Đẩy 1 license key lên repo private donkma93/muclick-license.

Yêu cầu: MUCLICK_GH_TOKEN hoặc muclick_secrets.GITHUB_LICENSE_TOKEN

  python tools/push_license_key.py --key MUCLK-... --exp 2026-12-31 --note khach-A
"""

from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from muclick_github_license import append_key_to_repo  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", required=True)
    ap.add_argument("--exp", required=True, help="YYYY-MM-DD")
    ap.add_argument("--note", default="")
    ap.add_argument("--id", default="")
    ap.add_argument("--max-devices", type=int, default=1)
    args = ap.parse_args()

    entry = append_key_to_repo(
        key=args.key,
        exp=args.exp,
        note=args.note,
        key_id=args.id or None,
        max_devices=args.max_devices,
    )
    print("OK", entry)


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""Exit 0 nếu có token license GitHub; 1 nếu thiếu."""
from __future__ import annotations

import os
import runpy
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

t = (os.environ.get("MUCLICK_GH_TOKEN") or "").strip()
if not t:
    path = os.path.join(ROOT, "muclick_secrets.py")
    try:
        d = runpy.run_path(path)
        t = str(d.get("GITHUB_LICENSE_TOKEN") or "").strip()
    except Exception:
        t = ""
sys.exit(0 if t else 1)

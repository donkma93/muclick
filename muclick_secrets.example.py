# -*- coding: utf-8 -*-
"""
Copy file này thành muclick_secrets.py và điền token.
muclick_secrets.py đã nằm trong .gitignore — KHÔNG commit.

Tạo Fine-grained PAT trên GitHub:
  - Resource owner: donkma93
  - Only select repositories: muclick
  - Permissions: Repository → Contents: Read and write  (bắt buộc Write)
  - Expiration: 90 ngày (khuyến nghị)

Repo keys: https://github.com/donkma93/muclick (file licenses/keys.json)
Env thay thế (ưu tiên hơn file): MUCLICK_GH_TOKEN

Admin trong app: nhập mật khẩu donpv93 vào ô License key để mở màn tạo key.
"""

GITHUB_LICENSE_TOKEN = ""
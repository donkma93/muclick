import sys
import urllib.request
import json
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from muclick_secrets import GITHUB_LICENSE_TOKEN

headers = {
    'Authorization': f'Bearer {GITHUB_LICENSE_TOKEN}',
    'Accept': 'application/vnd.github+json',
    'User-Agent': 'MuClick-Releaser'
}

data = json.dumps({
    'tag_name': 'v1.0.7',
    'name': 'MuClick v1.0.7 - Tự động cập nhật Zen từ game',
    'body': '### Tính năng mới trong v1.0.7:\n- Tự động nhận diện và trích xuất số Zen từ giao diện Hành trang (phím V) của game MEGAMU.\n- Tích hợp 2 nút bấm tại tab Tài khoản:\n  + **💰 Cập nhật Zen từ game (Tất cả cửa sổ)**: Duyệt tuần tự các cửa sổ game đang mở để đọc và cập nhật số Zen vào danh sách tài khoản tương ứng.\n  + **💰 Cập nhật Zen dòng chọn**: Đọc và cập nhật Zen cho đúng tài khoản đang chọn từ cửa sổ game tương ứng.\n- Cập nhật số Zen và lưu tự động vào accounts.json.',
    'draft': False,
    'prerelease': False
}).encode('utf-8')

req = urllib.request.Request('https://api.github.com/repos/donkma93/muclick/releases', data=data, headers=headers, method='POST')
try:
    with urllib.request.urlopen(req) as resp:
        rel = json.loads(resp.read().decode('utf-8'))
        upload_url = rel['upload_url'].split('{')[0]
        release_id = rel['id']
        print(f'Release created: id={release_id}')
except urllib.error.HTTPError as e:
    print(f'Release already exists or HTTP {e.code}, fetching existing release...')
    req2 = urllib.request.Request('https://api.github.com/repos/donkma93/muclick/releases/tags/v1.0.7', headers=headers)
    with urllib.request.urlopen(req2) as resp2:
        rel = json.loads(resp2.read().decode('utf-8'))
        upload_url = rel['upload_url'].split('{')[0]
        release_id = rel['id']

# Check if asset already exists in release
if 'assets' in rel:
    for a in rel['assets']:
        if a['name'] == 'MuClick.exe':
            print(f'Deleting existing asset id={a["id"]}...')
            del_req = urllib.request.Request(f'https://api.github.com/repos/donkma93/muclick/releases/assets/{a["id"]}', headers=headers, method='DELETE')
            urllib.request.urlopen(del_req)

exe_path = os.path.join('dist', 'MuClick.exe')
with open(exe_path, 'rb') as f:
    exe_bytes = f.read()

upload_headers = {
    'Authorization': f'Bearer {GITHUB_LICENSE_TOKEN}',
    'Content-Type': 'application/octet-stream',
    'User-Agent': 'MuClick-Releaser'
}
upload_target = f'{upload_url}?name=MuClick.exe'
print(f'Uploading MuClick.exe ({len(exe_bytes)} bytes)...')
req3 = urllib.request.Request(upload_target, data=exe_bytes, headers=upload_headers, method='POST')
with urllib.request.urlopen(req3) as resp3:
    asset = json.loads(resp3.read().decode('utf-8'))
    print('Asset uploaded successfully:', asset.get('browser_download_url'))

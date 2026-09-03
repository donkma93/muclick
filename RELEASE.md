# MuClick — Release + License Online

## Version / Build exe
1. Sửa `APP_VERSION` trong `muclick_paths.py`
2. Điền PAT vào `muclick_secrets.py` (copy từ `muclick_secrets.example.py`)
3. Chạy `build_exe.bat` → `dist\MuClick.exe`
4. Upload **`MuClick.exe`** lên Release repo **public** `donkma93/muclick` (tag `vX.Y.Z`)

## Repo license
- Hiện dùng: https://github.com/donkma93/muclick  
- File: `licenses/keys.json` (xem `licenses/keys.example.json`)
- **Cảnh báo:** repo public → file keys có thể bị người khác đọc. Nên chuyển repo private hoặc tách repo private riêng.

### Fine-grained PAT (bắt buộc có quyền GHI)
1. GitHub → Settings → Developer settings → Fine-grained tokens → Generate
2. Repository access: **Only select** → chọn `muclick`
3. Permissions → Repository → **Contents: Read and write**
4. (Nếu repo trống) tạo commit đầu trên GitHub (Add file / README) rồi mới PUT được
5. Đặt token vào `muclick_secrets.py` → `GITHUB_LICENSE_TOKEN = "..."`  
   hoặc env `MUCLICK_GH_TOKEN`
6. **Không commit** `muclick_secrets.py`

### Admin trong app
1. Mở app → tới màn **Kích hoạt online**
2. Ô License key nhập: `donpv93` → Enter / Kích hoạt
3. Màn Admin: chọn số ngày hoặc ngày hết hạn, ghi chú → **Tạo & đẩy lên Git**
4. Copy key `MUCLK-...` đưa cho khách

### Tạo & đẩy key (CLI)
```bat
python tools\gen_license_key.py --days 30 --note khach-A --push
```

### Seed keys.json lần đầu trên GitHub
Tạo file `licenses/keys.json`:
```json
{ "version": 1, "keys": [] }
```

## Luồng user
1. Mở app → check update từ `muclick` releases  
2. Kích hoạt online bằng key → app ghi HWID vào `keys.json`  
3. Máy khác dùng chung key → bị từ chối (1 máy/key)  
4. Mỗi lần mở app đều xác minh online lại  

## Local data
`%APPDATA%\MuClick\` — `license.json`, accounts, coords, autoclick.

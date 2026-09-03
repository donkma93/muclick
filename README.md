# MuClick

MEGAMU multi-window launcher + auto login + auto click.

## Tính năng
- Mở / sắp xếp nhiều cửa sổ MEGAMU
- Auto login theo slot
- Auto click theo số cửa sổ
- License online (GitHub `licenses/keys.json` + HWID, 1 máy/key)
- **Bắt buộc cập nhật** khi có GitHub Release mới hơn `APP_VERSION`

## Chạy (dev)
```bat
python megamu_launcher.py
```

## Build
```bat
build_exe.bat
```
Ra `dist\MuClick.exe`.

## Release
1. Bump `APP_VERSION` trong `muclick_paths.py`
2. Build exe
3. Push code + tag `vX.Y.Z`
4. Upload asset đúng tên **`MuClick.exe`** lên GitHub Release

Bản cũ hơn tag mới nhất sẽ bị chặn cho đến khi cập nhật.

## License admin
- Màn kích hoạt → nhập mật khẩu admin `donpv93` → tạo & đẩy key lên Git
- Cần `muclick_secrets.py` với `GITHUB_LICENSE_TOKEN` (không commit)

Chi tiết: [RELEASE.md](RELEASE.md)

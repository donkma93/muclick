@echo off
setlocal
cd /d "%~dp0"

echo === MuClick build ===

python tools\check_license_token.py
if errorlevel 1 (
  echo.
  echo [WARN] Chua co GitHub license token.
  echo Dien muclick_secrets.py hoac set MUCLICK_GH_TOKEN truoc khi phan phoi.
  echo Ban van co the build, nhung app se khong kich hoat online duoc.
  echo.
)

python -c "import PyInstaller" 2>nul
if errorlevel 1 (
  echo Dang cai PyInstaller...
  python -m pip install --upgrade pyinstaller
)

echo Building MuClick.exe ...
python -m PyInstaller --noconfirm --clean --onefile --windowed --name MuClick ^
  --hidden-import muclick_paths ^
  --hidden-import muclick_license ^
  --hidden-import muclick_update ^
  --hidden-import muclick_gates ^
  --hidden-import muclick_github_license ^
  --hidden-import muclick_secrets ^
  megamu_launcher.py

if errorlevel 1 (
  echo BUILD FAILED
  pause
  exit /b 1
)

echo.
echo OK: dist\MuClick.exe
echo Upload file nay len GitHub Release asset dung ten: MuClick.exe
echo Tag semver, vi du: v1.0.0  (trung APP_VERSION trong muclick_paths.py)
echo License keys nam tren repo: donkma93/muclick  (licenses/keys.json)
pause

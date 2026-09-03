@echo off
cd /d "%~dp0"
python "%~dp0megamu_launcher.py"
if errorlevel 1 pause

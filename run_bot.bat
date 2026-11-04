@echo off
chcp 65001 >nul
cd /d "%~dp0"
:loop
".venv\Scripts\python.exe" -X utf8 bot\main.py
echo Bot dung, thu lai sau 10 giay...
timeout /t 10 /nobreak >nul
goto loop

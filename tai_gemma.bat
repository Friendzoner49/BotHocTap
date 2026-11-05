@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Tai mo hinh gemma4:12b cho Ollama. Neu mang rot, cua so tu thu lai; tai tiep duoc tu cho dang do.
echo Neu bao "resolves to non-public 198.18": tat VPN, hoac cho ollama.com va *.r2.cloudflarestorage.com di thang (DIRECT) trong VPN, roi chay lai file nay.
echo.
:loop
ollama pull gemma4:12b
if %errorlevel%==0 goto done
echo Loi, thu lai sau 15 giay...
timeout /t 15 /nobreak >nul
goto loop
:done
echo.
echo Da tai xong gemma4:12b. Bot se dung no cho /conspect khi Gemini khong tra loi duoc.
pause

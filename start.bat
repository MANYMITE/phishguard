@echo off
rem PhishGuard launcher - always uses the same key so logins never mysteriously fail.
cd /d "%~dp0"
set PHISHGUARD_SECRET_KEY=demo123
set PHISHGUARD_HOST=0.0.0.0
set PORT=5000
echo ============================================
echo   PhishGuard  -  admin password: demo123
echo   Local:   http://127.0.0.1:5000
echo   Network: http://(your-ip):5000
echo   Stop:    Ctrl+C
echo ============================================
.venv\Scripts\python.exe run.py

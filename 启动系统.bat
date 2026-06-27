@echo off
chcp 936 >nul
title Huili Smart Guide - Start Server
echo ========================================
echo    Huili Smart Guide - Starting...
echo ========================================
echo.
echo Starting backend server...
echo.

cd /d "%~dp0backend"
start "Huili Server" "%~dp0.venv\Scripts\python.exe" app.py

echo Waiting for server to start...
timeout /t 8 /nobreak >nul

echo.
echo Opening pages in browser...
echo.

start "" "http://127.0.0.1:5000"
timeout /t 2 /nobreak >nul
start "" "http://127.0.0.1:5000/admin.html"

echo.
echo ========================================
echo    Server is running!
echo    Visitor:  http://127.0.0.1:5000
echo    Admin:    http://127.0.0.1:5000/admin.html
echo    Accounts: http://127.0.0.1:5000/accounts.html
echo ========================================
echo.
echo Press any key to stop the server...
pause >nul

taskkill /f /fi "WINDOWTITLE eq Huili Server*" >nul 2>&1
echo Server stopped.

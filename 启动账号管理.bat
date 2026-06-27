@echo off
chcp 936 >nul
title Huili Smart Guide - Account Manager
echo ========================================
echo    Huili Smart Guide - Account Manager
echo ========================================
echo.
echo Starting account management page...
echo.

set "HTML_FILE=%~dp0frontend\accounts.html"

if exist "%HTML_FILE%" (
    start "" "%HTML_FILE%"
    echo Account page opened in browser!
) else (
    echo ERROR: accounts.html not found
    echo Path: %HTML_FILE%
)

echo.
echo Note: Make sure backend is running (python app.py)
echo.
pause

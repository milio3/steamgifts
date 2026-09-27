@echo off
chcp 65001 >nul
title SteamGifts Bot
cd /d "%~dp0"
python cli.py
echo.
pause

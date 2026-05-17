@echo off
title AXIS OS — Setup
cd /d "%~dp0"
echo ============================================
echo   AXIS OS v1.0 — Встановлення залежностей
echo ============================================
echo.
echo [1/2] Оновлення pip...
python -m pip install --upgrade pip

echo.
echo [2/2] Встановлення пакетів...
pip install -r requirements.txt

echo.
echo ============================================
echo   Готово! Запустіть run.bat для старту.
echo ============================================
pause

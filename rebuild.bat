@echo off
title AXIS IDE - Rebuild
chcp 65001 >nul
echo Закриваю старі процеси...
taskkill /f /im AXIS_IDE.exe >nul 2>&1
taskkill /f /im QtWebEngineProcess.exe >nul 2>&1
timeout /t 3 /nobreak >nul
echo Збираю у нову папку dist_new...
rd /s /q "dist_new\AXIS_IDE" >nul 2>&1
pyinstaller axis_ide.spec --noconfirm --distpath dist_new
if errorlevel 1 (
    echo ПОМИЛКА ЗБІРКИ
    pause
    exit /b 1
)
echo Замінюю dist\AXIS_IDE...
rd /s /q "dist\AXIS_IDE" >nul 2>&1
if exist "dist\AXIS_IDE" (
    echo Стара папка заблокована - використовуй dist_new\AXIS_IDE\AXIS_IDE.exe
) else (
    xcopy /e /i /y "dist_new\AXIS_IDE" "dist\AXIS_IDE" >nul
    rd /s /q "dist_new\AXIS_IDE" >nul 2>&1
    echo [OK] dist\AXIS_IDE\AXIS_IDE.exe готово!
)
pause

@echo off
title AXIS OS - Full Build

echo.
echo  ================================
echo       AXIS OS - Full Build
echo   Panel + Sphere + IDE
echo  ================================
echo.

:: Check PyInstaller
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo [*] Installing PyInstaller...
    pip install pyinstaller
)

:: Clean everything
echo [*] Cleaning previous builds...
if exist "dist\AXIS_OS"      rmdir /s /q "dist\AXIS_OS"
if exist "dist\AXIS_Sphere"  rmdir /s /q "dist\AXIS_Sphere"
if exist "dist\AXIS_IDE"     rmdir /s /q "dist\AXIS_IDE"
if exist "build\AXIS_OS"     rmdir /s /q "build\AXIS_OS"
if exist "build\AXIS_Sphere" rmdir /s /q "build\AXIS_Sphere"
if exist "build\AXIS_IDE"    rmdir /s /q "build\AXIS_IDE"

:: ── 1. Build AXIS Panel ───────────────────────────────────────────────
echo.
echo [1/3] Building AXIS Panel...
pyinstaller axis_os.spec --noconfirm
if errorlevel 1 ( echo [!] AXIS Panel FAILED & pause & exit /b 1 )
echo [OK] AXIS Panel done.

:: ── 2. Build AXIS Sphere ──────────────────────────────────────────────
echo.
echo [2/3] Building AXIS Sphere...
pyinstaller axis_sphere.spec --noconfirm
if errorlevel 1 ( echo [!] AXIS Sphere FAILED & pause & exit /b 1 )
echo [OK] AXIS Sphere done.

:: ── 3. Build AXIS IDE ─────────────────────────────────────────────────
echo.
echo [3/3] Building AXIS IDE...
pyinstaller axis_ide.spec --noconfirm
if errorlevel 1 ( echo [!] AXIS IDE FAILED & pause & exit /b 1 )
echo [OK] AXIS IDE done.

:: ── Merge all into dist\AXIS_OS ───────────────────────────────────────
echo.
echo [*] Merging into dist\AXIS_OS...

:: Copy AXIS_Sphere.exe
copy /y "dist\AXIS_Sphere\AXIS_Sphere.exe" "dist\AXIS_OS\AXIS_Sphere.exe"
if errorlevel 1 ( echo [!] Could not copy AXIS_Sphere.exe & pause & exit /b 1 )

:: Copy AXIS_IDE.exe
copy /y "dist\AXIS_IDE\AXIS_IDE.exe" "dist\AXIS_OS\AXIS_IDE.exe"
if errorlevel 1 ( echo [!] Could not copy AXIS_IDE.exe & pause & exit /b 1 )

:: Merge _internal folders (sphere and IDE share most files with panel)
if exist "dist\AXIS_Sphere\_internal" (
    xcopy /e /i /y /q "dist\AXIS_Sphere\_internal" "dist\AXIS_OS\_internal"
)
if exist "dist\AXIS_IDE\_internal" (
    xcopy /e /i /y /q "dist\AXIS_IDE\_internal" "dist\AXIS_OS\_internal"
)

:: Copy assets and data
if exist "assets" xcopy /e /i /y /q "assets" "dist\AXIS_OS\assets"
if not exist "dist\AXIS_OS\data" mkdir "dist\AXIS_OS\data"
copy /y "version.txt"              "dist\AXIS_OS\version.txt"              >nul 2>&1
copy /y "data\icon_panel.ico"      "dist\AXIS_OS\data\icon_panel.ico"     >nul 2>&1
copy /y "data\icon_sphere.ico"     "dist\AXIS_OS\data\icon_sphere.ico"    >nul 2>&1
copy /y "data\icon_ide.ico"        "dist\AXIS_OS\data\icon_ide.ico"       >nul 2>&1

echo.
echo [*] Contents of dist\AXIS_OS:
dir /b "dist\AXIS_OS\*.exe"

echo.
echo [*] Done!
echo     dist\AXIS_OS\AXIS_OS.exe     - Panel
echo     dist\AXIS_OS\AXIS_Sphere.exe - Sphere
echo     dist\AXIS_OS\AXIS_IDE.exe    - IDE
echo.

:: ── Inno Setup ────────────────────────────────────────────────────────
where iscc >nul 2>&1
if not errorlevel 1 (
    echo [*] Creating installer...
    iscc setup.iss
    echo [*] Installer: dist\AXIS_OS_Setup_1.0.0.exe
) else (
    echo [i] Inno Setup not found - skipping
)

echo.
echo  ================================
echo         Build complete!
echo  ================================
pause

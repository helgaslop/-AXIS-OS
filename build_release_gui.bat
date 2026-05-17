@echo off
cd /d "%~dp0"
echo Збираю AXIS_Release.exe...
pyinstaller release_gui.spec --noconfirm --distpath . --workpath build\release_gui_build
echo.
echo Готово! AXIS_Release.exe у кореневій папці.
pause

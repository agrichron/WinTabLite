@echo off
rem 打包成单文件 exe（产物在 dist\ 目录）
cd /d "%~dp0"
set "PY=C:\Users\siwei\miniforge3\python.exe"
if not exist "%PY%" set "PY=python"

"%PY%" tools\make_icon.py || goto fail

"%PY%" -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name WinTabLite --icon assets\icon.ico ^
  --hidden-import autostart --hidden-import win32com --hidden-import win32com.client ^
  wintab_lite.py || goto fail

copy /y config.ini "dist\config.ini" >nul
echo.
echo 打包完成：dist\WinTabLite.exe
pause
exit /b 0

:fail
echo.
echo 打包失败，请查看上面的输出
pause
exit /b 1

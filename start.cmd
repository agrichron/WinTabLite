@echo off
rem 源码方式启动（需要已安装 Python + PyQt5）
cd /d "%~dp0"
set "PYW=C:\Users\siwei\miniforge3\pythonw.exe"
if exist "%PYW%" (
    start "" "%PYW%" "wintab_lite.py"
) else (
    start "" pythonw "wintab_lite.py"
)

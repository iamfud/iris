@echo off
REM Iris — Build packaged executable
REM Requires: Python + PyInstaller

cd /d "%~dp0"

echo Installing requirements...
pip install -r requirements.txt
if %errorlevel% neq 0 exit /b %errorlevel%

echo Building executable...
pyinstaller --onefile --noconsole ^
    --name "Iris" ^
    --hidden-import "comtypes" ^
    --hidden-import "pystray._win32" ^
    --hidden-import "serial" ^
    --hidden-import "serial.tools.list_ports" ^
    --hidden-import "requests" ^
    --hidden-import "psutil" ^
    "app\main.py"
if %errorlevel% neq 0 exit /b %errorlevel%

echo Done. Built: dist\Iris.exe

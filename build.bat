@echo off
REM Iris — Build packaged executable
REM Requires: Python + PyInstaller

echo Installing requirements...
pip install -r requirements.txt
if %errorlevel% neq 0 exit /b %errorlevel%

echo Bundling web frontend assets into embedded_assets.py...
python tools\bundle_assets.py
if %errorlevel% neq 0 exit /b %errorlevel%

echo Building executable...
pyinstaller --clean --onefile --noconsole ^
   --name "Iris" ^
   --icon "Iris.ico" ^
   --add-data "media;media" ^
   --add-data "app\settings_pages.json;app" ^
   --add-data "app\mdi-meta.json;app" ^
   --add-data "app\mdi-webfont.ttf;app" ^
   --add-data "Installer\deps\Interception\Interception\library\x64\interception.dll;app" ^
   --hidden-import "comtypes" ^
   --hidden-import "connector_base" ^
   --hidden-import "pystray._win32" ^
   --hidden-import "serial" ^
   --hidden-import "serial.tools.list_ports" ^
   --hidden-import "requests" ^
   --hidden-import "psutil" ^
   --hidden-import "websockets" ^
   --hidden-import "websockets.legacy.server" ^
   --hidden-import "websockets.legacy.client" ^
   --collect-all "webview" ^
   --hidden-import "qrcode" ^
   --hidden-import "qrcode.image.pil" ^
   --hidden-import "pycaw.api.mmdeviceapi" ^
   --hidden-import "pycaw.api.endpointvolume" ^
   --hidden-import "pycaw.constants" ^
   --hidden-import "pycaw.utils" ^
   --hidden-import "argon2" ^
   --hidden-import "argon2.exceptions" ^
   --hidden-import "winrt.windows.media.control" ^
   --hidden-import "winrt.windows.storage.streams" ^
   --hidden-import "winrt.windows.media.ocr" ^
   --hidden-import "winrt.windows.graphics.imaging" ^
   --hidden-import "winrt.windows.ui.notifications.management" ^
   --hidden-import "winrt.windows.ui.notifications" ^
   "app\main.py"

if %errorlevel% neq 0 exit /b %errorlevel%

echo Copying built-in plugins to dist\plugins...
if not exist "dist\plugins" mkdir "dist\plugins"
robocopy "app\plugins" "dist\plugins" /E /XD __pycache__ >nul
if exist "dist\plugins\__pycache__" rd /s /q "dist\plugins\__pycache__"

REM Remove portable marker if present
if exist "dist\portable.dat" del /f /q "dist\portable.dat"

echo.
echo ============================================================
echo PyInstaller build complete: dist\Iris.exe
echo ============================================================
echo.
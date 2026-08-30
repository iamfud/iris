@echo off
REM Iris — Build packaged executable
REM Requires: Python + PyInstaller

echo Installing requirements...
pip install -r requirements.txt
if %errorlevel% neq 0 exit /b %errorlevel%

echo Building executable...
pyinstaller --clean --onefile --noconsole ^
   --name "Iris" ^
   --icon "Iris.ico" ^
   --add-data "media;media" ^
   --add-data "HTML;HTML" ^
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

REM Check for Inno Setup Compiler (ISCC.exe)
set "ISCC_PATH="
where iscc.exe >nul 2>&1 && set "ISCC_PATH=iscc.exe"
if "%ISCC_PATH%"=="" if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC_PATH=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if "%ISCC_PATH%"=="" if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC_PATH=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if "%ISCC_PATH%"=="" if exist "%LocalAppData%\Programs\Inno Setup 6\ISCC.exe" set "ISCC_PATH=%LocalAppData%\Programs\Inno Setup 6\ISCC.exe"

if not "%ISCC_PATH%"=="" (
    echo Compiling Installer with Inno Setup...
    "%ISCC_PATH%" "Iris_Setup.iss"
    if errorlevel 1 (
        echo [WARNING] Inno Setup compilation failed.
    ) else (
        echo.
        echo ============================================================
        echo SUCCESS: Installer generated at Installer\Iris_Setup.exe
        echo ============================================================
    )
) else (
    echo.
    echo [INFO] Inno Setup compiler (ISCC.exe) not found on PATH.
    echo Open 'Iris_Setup.iss' in Inno Setup to compile 'Installer\Iris_Setup.exe'.
)

echo.
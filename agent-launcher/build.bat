@echo off
echo ========================================
echo  Boz Ripper Agent Launcher - Build
echo ========================================
echo.

REM Change to script directory
cd /d "%~dp0"

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    pause
    exit /b 1
)

REM Install requirements
echo Installing requirements...
pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install requirements
    pause
    exit /b 1
)

echo.
echo Building executable...
echo.

REM Build with PyInstaller
REM --onefile: Single executable
REM --windowed: No console window
REM --name: Output name
REM --add-data: Include any data files if needed

pyinstaller --onefile --windowed --name=BozRipperAgent launcher.py

if errorlevel 1 (
    echo.
    echo ERROR: Build failed!
    pause
    exit /b 1
)

echo.
echo ========================================
echo  Build complete!
echo ========================================
echo.
echo Executable location:
echo   %~dp0dist\BozRipperAgent.exe
echo.
echo You can copy this to your Desktop or Startup folder.
echo.

REM Open the dist folder
explorer dist

pause

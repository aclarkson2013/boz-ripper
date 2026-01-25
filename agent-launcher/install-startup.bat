@echo off
echo ========================================
echo  Add Boz Ripper to Windows Startup
echo ========================================
echo.

cd /d "%~dp0"

REM Check if exe exists
if not exist "dist\BozRipperAgent.exe" (
    echo ERROR: BozRipperAgent.exe not found!
    echo Please run build.bat first.
    echo.
    pause
    exit /b 1
)

REM Get the startup folder path
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"

REM Create shortcut using PowerShell
echo Creating shortcut in Startup folder...
powershell -Command "$WshShell = New-Object -ComObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%STARTUP%\BozRipperAgent.lnk'); $Shortcut.TargetPath = '%~dp0dist\BozRipperAgent.exe'; $Shortcut.WorkingDirectory = '%~dp0'; $Shortcut.Description = 'Boz Ripper Agent Launcher'; $Shortcut.Save()"

if errorlevel 1 (
    echo ERROR: Failed to create shortcut
    pause
    exit /b 1
)

echo.
echo ========================================
echo  Success!
echo ========================================
echo.
echo Boz Ripper Agent will now start automatically when Windows starts.
echo.
echo Shortcut created at:
echo   %STARTUP%\BozRipperAgent.lnk
echo.
pause

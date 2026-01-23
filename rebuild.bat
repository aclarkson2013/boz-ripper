@echo off
REM Quick rebuild script for Boz Ripper Docker containers (Windows)

echo =========================================
echo Boz Ripper - Docker Rebuild Script
echo =========================================
echo.

REM Check if .env exists
if not exist .env (
    echo WARNING: .env file not found!
    echo Creating .env from template...
    if exist .env.example (
        copy .env.example .env
        echo Created .env file
        echo.
        echo IMPORTANT: Edit .env and add your TheTVDB API key!
        echo    BOZ_THETVDB_API_KEY=your_key_here
        echo.
        pause
    ) else (
        echo ERROR: .env.example not found. Please create .env manually.
        exit /b 1
    )
)

echo 1. Stopping containers...
docker compose down

echo.
echo 2. Rebuilding server (this may take a minute)...
docker compose build --no-cache server

echo.
echo 3. Rebuilding dashboard...
docker compose build --no-cache dashboard

echo.
echo 4. Starting containers...
docker compose up -d

echo.
echo 5. Waiting for server to start...
timeout /t 5 /nobreak > nul

echo.
echo =========================================
echo Rebuild complete!
echo =========================================
echo.
echo Next steps:
echo   1. Watch logs: docker compose logs -f server
echo   2. Insert 'OFFICE' disc
echo   3. Look for detailed logs with ======== markers
echo   4. Check dashboard at http://localhost:5000
echo.

echo Checking server status...
docker compose ps server

echo.
echo To view logs: docker compose logs -f server
echo.
pause

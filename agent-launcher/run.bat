@echo off
REM Quick run script for testing (without building exe)
cd /d "%~dp0"

REM Install requirements if needed
pip install -r requirements.txt -q

REM Run the launcher
pythonw launcher.py

# Boz Ripper Agent Launcher

A Windows system tray application for managing the Boz Ripper Agent.

## Features

- **System Tray Icon**: Shows agent status with color-coded icon
  - Green = Running
  - Red = Stopped
  - Yellow = Updating
  - Blue = Starting

- **Right-Click Menu**:
  - Start/Stop/Restart Agent
  - Open Dashboard (web UI)
  - Check for Updates
  - View Logs
  - Exit

- **Auto-Update**: Checks for git updates on launch and installs them

- **Auto-Start**: Agent starts automatically when launcher opens

- **Crash Detection**: Notifies you if the agent crashes

## Quick Start

### Option 1: Run directly (for testing)
```
run.bat
```

### Option 2: Build executable
```
build.bat
```
Then run `dist/BozRipperAgent.exe`

### Option 3: Add to Windows Startup
1. First run `build.bat`
2. Then run `install-startup.bat`

## Files

- `launcher.py` - Main application code
- `requirements.txt` - Python dependencies
- `build.bat` - Builds standalone .exe
- `run.bat` - Runs without building
- `install-startup.bat` - Adds to Windows startup
- `agent.log` - Log file (created on first run)

## Requirements

- Python 3.8+
- Windows 10/11
- Git (for auto-update feature)

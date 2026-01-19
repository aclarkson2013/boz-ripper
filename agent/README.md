# Boz Ripper Agent

Windows agent for automated disc detection and ripping.

## Features

- **Disc Detection**: Automatically detects when DVDs/Blu-rays are inserted using Windows WMI
- **MakeMKV Integration**: Analyzes disc contents and rips titles to MKV format
- **Server Communication**: Reports detected discs to the Boz Ripper server
- **Optional Local Transcoding**: Can act as a transcoding worker using HandBrake

## Requirements

- Windows 10/11
- Python 3.11+
- [MakeMKV](https://www.makemkv.com/) (for disc ripping)
- [HandBrake CLI](https://handbrake.fr/) (optional, for local transcoding)

## Installation

```bash
# Create virtual environment
python -m venv venv
venv\Scripts\activate

# Install the agent
pip install -e .
```

## Configuration

1. Copy `config/config.example.yaml` to `config/config.yaml`
2. Edit the configuration file with your settings:
   - Set the server URL and API key
   - Configure MakeMKV and HandBrake paths if non-default
   - Enable/disable local transcoding

## Usage

```bash
# Run the agent
boz-agent run

# Run with custom config
boz-agent run --config /path/to/config.yaml

# Check system requirements
boz-agent check

# Show version
boz-agent version
```

## Project Structure

```
agent/
├── config/
│   └── config.example.yaml    # Example configuration
├── src/
│   └── boz_agent/
│       ├── __init__.py
│       ├── main.py            # CLI entry point
│       ├── core/
│       │   ├── __init__.py
│       │   └── config.py      # Configuration management
│       └── services/
│           ├── __init__.py
│           ├── disc_detector.py   # Windows disc detection
│           ├── makemkv.py         # MakeMKV interface
│           ├── server_client.py   # Server API client
│           └── worker.py          # Local transcoding worker
├── tests/
│   └── test_config.py
├── pyproject.toml
├── requirements.txt
└── README.md
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run linter
ruff check .

# Run type checker
mypy src/
```

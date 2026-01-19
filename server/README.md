# Boz Ripper Server

FastAPI server for orchestrating DVD/Blu-ray ripping jobs.

## Features

- **Agent Management**: Register and monitor ripping agents
- **Job Queue**: Manage rip and transcode jobs with priorities
- **NAS Organization**: Automatically organize completed files to NAS storage
- **REST API**: Full API for agents and external integrations

## Quick Start

### Using Docker Compose (Recommended)

```bash
# From the project root
docker-compose up -d

# View logs
docker-compose logs -f server

# Stop
docker-compose down
```

### Local Development

```bash
cd server

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

# Install dependencies
pip install -e ".[dev]"

# Copy environment file
cp .env.example .env

# Run the server
python -m boz_server.main
```

## API Endpoints

### Health & Info

- `GET /` - Server info
- `GET /health` - Health check with stats

### Agents

- `POST /api/agents/register` - Register an agent
- `POST /api/agents/{id}/unregister` - Unregister an agent
- `POST /api/agents/{id}/heartbeat` - Send heartbeat
- `GET /api/agents` - List all agents
- `GET /api/agents/{id}` - Get agent details
- `GET /api/agents/{id}/jobs` - Get agent's jobs

### Discs

- `POST /api/discs/detected` - Report detected disc
- `POST /api/discs/ejected` - Report ejected disc
- `GET /api/discs` - List all discs
- `GET /api/discs/{id}` - Get disc details
- `POST /api/discs/{id}/rip` - Start ripping a disc

### Jobs

- `POST /api/jobs` - Create a job
- `GET /api/jobs` - List all jobs
- `GET /api/jobs/stats` - Get queue statistics
- `GET /api/jobs/pending` - Get pending jobs
- `GET /api/jobs/{id}` - Get job details
- `PATCH /api/jobs/{id}` - Update job status
- `POST /api/jobs/{id}/assign` - Assign job to agent
- `POST /api/jobs/{id}/cancel` - Cancel a job

## Configuration

Configuration via environment variables (prefix: `BOZ_`):

| Variable | Default | Description |
|----------|---------|-------------|
| `BOZ_DEBUG` | `false` | Enable debug mode |
| `BOZ_PORT` | `8000` | Server port |
| `BOZ_API_KEY` | `` | API key for auth (optional) |
| `BOZ_NAS_ENABLED` | `false` | Enable NAS organization |
| `BOZ_NAS_HOST` | `` | NAS hostname/IP |
| `BOZ_NAS_MOVIE_PATH` | `Movies` | Movie folder on NAS |
| `BOZ_NAS_TV_PATH` | `TV Shows` | TV folder on NAS |

## Project Structure

```
server/
├── src/boz_server/
│   ├── __init__.py
│   ├── main.py              # FastAPI application
│   ├── api/
│   │   ├── __init__.py
│   │   ├── deps.py          # Dependencies
│   │   ├── agents.py        # Agent endpoints
│   │   ├── discs.py         # Disc endpoints
│   │   └── jobs.py          # Job endpoints
│   ├── core/
│   │   ├── __init__.py
│   │   └── config.py        # Configuration
│   ├── models/
│   │   ├── __init__.py
│   │   ├── agent.py         # Agent models
│   │   ├── disc.py          # Disc models
│   │   └── job.py           # Job models
│   └── services/
│       ├── __init__.py
│       ├── agent_manager.py # Agent management
│       ├── job_queue.py     # Job queue
│       └── nas_organizer.py # NAS file org
├── tests/
├── Dockerfile
├── pyproject.toml
├── requirements.txt
└── README.md
```

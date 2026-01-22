# Boz Ripper Dashboard

Web UI for monitoring and managing the Boz Ripper system.

## Features

- **Dashboard**: Overview of active jobs, workers, and detected discs
- **Jobs**: View all jobs with filtering, progress tracking, and job details
- **Workers**: Monitor registered workers and their capabilities
- **Discs**: View detected discs, select titles, and start ripping

## Setup

1. Install dependencies:
   ```bash
   cd dashboard
   pip install -r requirements.txt
   ```

2. Configure the API URL (optional):
   ```bash
   # Default: http://localhost:8000
   set BOZ_API_URL=http://your-server:8000
   ```

3. Run the dashboard:
   ```bash
   python app.py
   ```

4. Open http://localhost:5000 in your browser

## Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `BOZ_API_URL` | `http://localhost:8000` | Boz Ripper API server URL |
| `DASHBOARD_PORT` | `5000` | Dashboard web server port |
| `FLASK_DEBUG` | `1` | Enable debug mode (0/1) |
| `FLASK_SECRET_KEY` | (dev key) | Secret key for sessions |

## Running with Docker

The dashboard can be added to the docker-compose.yml:

```yaml
dashboard:
  build: ./dashboard
  ports:
    - "5000:5000"
  environment:
    - BOZ_API_URL=http://server:8000
  depends_on:
    - server
```

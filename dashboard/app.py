"""Flask Web UI Dashboard for Boz Ripper."""

import os
from datetime import datetime
from functools import wraps

import httpx
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "boz-ripper-dashboard-dev-key")

# API configuration
API_BASE_URL = os.environ.get("BOZ_API_URL", "http://localhost:8000")
API_TIMEOUT = 10.0


def api_request(method: str, endpoint: str, **kwargs) -> dict | list | None:
    """Make a request to the Boz Ripper API."""
    url = f"{API_BASE_URL}{endpoint}"
    try:
        with httpx.Client(timeout=API_TIMEOUT) as client:
            response = client.request(method, url, **kwargs)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as e:
        app.logger.error(f"API error: {e.response.status_code} - {e.response.text}")
        return None
    except httpx.RequestError as e:
        app.logger.error(f"API request failed: {e}")
        return None


def format_duration(seconds: int | None) -> str:
    """Format seconds as human-readable duration."""
    if seconds is None:
        return "-"
    hours, remainder = divmod(int(seconds), 3600)
    minutes, secs = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}h {minutes}m"
    elif minutes > 0:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def format_size(bytes_val: int | None) -> str:
    """Format bytes as human-readable size."""
    if bytes_val is None:
        return "-"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(bytes_val) < 1024.0:
            return f"{bytes_val:.1f} {unit}"
        bytes_val /= 1024.0
    return f"{bytes_val:.1f} PB"


def format_datetime(dt_str: str | None) -> str:
    """Format ISO datetime string for display."""
    if not dt_str:
        return "-"
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, AttributeError):
        return dt_str


def time_ago(dt_str: str | None) -> str:
    """Convert datetime to 'X ago' format."""
    if not dt_str:
        return "-"
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        if dt.tzinfo:
            dt = dt.replace(tzinfo=None)
        delta = datetime.utcnow() - dt

        seconds = delta.total_seconds()
        if seconds < 60:
            return "just now"
        elif seconds < 3600:
            mins = int(seconds / 60)
            return f"{mins}m ago"
        elif seconds < 86400:
            hours = int(seconds / 3600)
            return f"{hours}h ago"
        else:
            days = int(seconds / 86400)
            return f"{days}d ago"
    except (ValueError, AttributeError):
        return "-"


# Register template filters
app.jinja_env.filters["duration"] = format_duration
app.jinja_env.filters["size"] = format_size
app.jinja_env.filters["datetime"] = format_datetime
app.jinja_env.filters["timeago"] = time_ago


# -----------------------------------------------------------------------------
# Page Routes
# -----------------------------------------------------------------------------


@app.route("/")
def index():
    """Main dashboard page."""
    return render_template("index.html")


@app.route("/jobs")
def jobs_page():
    """Jobs listing page."""
    return render_template("jobs.html")


@app.route("/agents")
def agents_page():
    """Agents/Workers page."""
    return render_template("agents.html")


@app.route("/discs")
def discs_page():
    """Disc management page."""
    return render_template("discs.html")


# -----------------------------------------------------------------------------
# API Proxy Routes (for AJAX calls from dashboard)
# -----------------------------------------------------------------------------


@app.route("/api/dashboard")
def api_dashboard():
    """Get all dashboard data in one call."""
    health = api_request("GET", "/health") or {}
    agents = api_request("GET", "/api/agents") or []
    workers = api_request("GET", "/api/workers") or []
    jobs = api_request("GET", "/api/jobs") or []
    discs = api_request("GET", "/api/discs") or []
    stats = api_request("GET", "/api/jobs/stats") or {}

    # Categorize jobs
    active_jobs = [j for j in jobs if j.get("status") in ("running", "assigned")]
    pending_jobs = [j for j in jobs if j.get("status") in ("pending", "queued")]
    completed_jobs = [j for j in jobs if j.get("status") == "completed"]
    failed_jobs = [j for j in jobs if j.get("status") == "failed"]

    # Sort by date
    completed_jobs.sort(key=lambda x: x.get("completed_at", ""), reverse=True)
    failed_jobs.sort(key=lambda x: x.get("completed_at", ""), reverse=True)

    return jsonify({
        "connected": bool(health),
        "server": health,
        "agents": agents,
        "workers": workers,
        "discs": discs,
        "stats": stats,
        "jobs": {
            "active": active_jobs[:10],
            "pending": pending_jobs[:10],
            "completed": completed_jobs[:20],
            "failed": failed_jobs[:10],
        },
        "counts": {
            "agents_online": len([a for a in agents if a.get("status") == "online"]),
            "agents_busy": len([a for a in agents if a.get("status") == "busy"]),
            "agents_total": len(agents),
            "workers_available": len([w for w in workers if w.get("status") == "available"]),
            "workers_busy": len([w for w in workers if w.get("status") == "busy"]),
            "workers_total": len(workers),
            "jobs_active": len(active_jobs),
            "jobs_pending": len(pending_jobs),
            "jobs_completed": len(completed_jobs),
            "jobs_failed": len(failed_jobs),
            "discs_detected": len([d for d in discs if d.get("status") == "detected"]),
        },
    })


@app.route("/api/agents")
def api_agents():
    """Proxy to agents API."""
    agents = api_request("GET", "/api/agents")
    return jsonify(agents or [])


@app.route("/api/workers")
def api_workers():
    """Proxy to workers API."""
    workers = api_request("GET", "/api/workers")
    return jsonify(workers or [])


@app.route("/api/workers/<worker_id>")
def api_worker_detail(worker_id: str):
    """Get single worker details."""
    worker = api_request("GET", f"/api/workers/{worker_id}")
    return jsonify(worker or {})


@app.route("/api/workers/stats")
def api_worker_stats():
    """Get worker statistics."""
    stats = api_request("GET", "/api/workers/stats")
    return jsonify(stats or {})


@app.route("/api/agents/<agent_id>")
def api_agent_detail(agent_id: str):
    """Get single agent details."""
    agent = api_request("GET", f"/api/agents/{agent_id}")
    return jsonify(agent or {})


@app.route("/api/jobs")
def api_jobs():
    """Proxy to jobs API."""
    status = request.args.get("status")
    endpoint = "/api/jobs"
    if status:
        endpoint += f"?status={status}"
    jobs = api_request("GET", endpoint)
    return jsonify(jobs or [])


@app.route("/api/jobs/<job_id>")
def api_job_detail(job_id: str):
    """Get single job details."""
    job = api_request("GET", f"/api/jobs/{job_id}")
    return jsonify(job or {})


@app.route("/api/jobs/<job_id>/cancel", methods=["POST"])
def api_cancel_job(job_id: str):
    """Cancel a job."""
    result = api_request("POST", f"/api/jobs/{job_id}/cancel")
    return jsonify(result or {"error": "Failed to cancel job"})


@app.route("/api/jobs/awaiting-approval")
def api_jobs_awaiting_approval():
    """Get jobs awaiting user approval."""
    jobs = api_request("GET", "/api/jobs/awaiting-approval")
    return jsonify(jobs or [])


@app.route("/api/jobs/<job_id>/approve", methods=["POST"])
def api_approve_job(job_id: str):
    """Approve a transcode job with worker and preset selection."""
    data = request.get_json() or {}
    result = api_request("POST", f"/api/jobs/{job_id}/approve", json=data)
    if result and result.get("status") == "ok":
        return jsonify(result)
    return jsonify(result or {"error": "Failed to approve job"}), 400


@app.route("/api/jobs/presets")
def api_job_presets():
    """Get available transcoding presets."""
    presets = api_request("GET", "/api/jobs/presets")
    return jsonify(presets or {"presets": []})


@app.route("/api/discs")
def api_discs():
    """Proxy to discs API."""
    discs = api_request("GET", "/api/discs")
    return jsonify(discs or [])


@app.route("/api/discs/<disc_id>")
def api_disc_detail(disc_id: str):
    """Get single disc details."""
    disc = api_request("GET", f"/api/discs/{disc_id}")
    return jsonify(disc or {})


@app.route("/api/discs/<disc_id>/rip", methods=["POST"])
def api_rip_disc(disc_id: str):
    """Start ripping a disc."""
    data = request.get_json() or {}
    result = api_request("POST", f"/api/discs/{disc_id}/rip", json=data)
    return jsonify(result or {"error": "Failed to start rip"})


@app.route("/api/health")
def api_health():
    """Proxy to health API."""
    health = api_request("GET", "/health")
    return jsonify(health or {"status": "disconnected"})


# -----------------------------------------------------------------------------
# Error Handlers
# -----------------------------------------------------------------------------


@app.errorhandler(404)
def not_found(e):
    """Handle 404 errors."""
    return render_template("error.html", error="Page not found", code=404), 404


@app.errorhandler(500)
def server_error(e):
    """Handle 500 errors."""
    return render_template("error.html", error="Internal server error", code=500), 500


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------


if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"
    port = int(os.environ.get("DASHBOARD_PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=debug)

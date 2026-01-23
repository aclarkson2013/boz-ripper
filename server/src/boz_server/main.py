"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from boz_server import __version__
from boz_server.api import agents_router, discs_router, files_router, jobs_router
from boz_server.api.workers import router as workers_router
from boz_server.api.deps import init_services
from boz_server.core.config import settings
from boz_server.services.agent_manager import AgentManager
from boz_server.services.job_queue import JobQueue
from boz_server.services.nas_organizer import NASOrganizer
from boz_server.services.worker_manager import WorkerManager

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Service instances
agent_manager = AgentManager()
job_queue = JobQueue()
nas_organizer = NASOrganizer()
worker_manager = WorkerManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    logger.info(f"Starting Boz Ripper Server v{__version__}")

    init_services(agent_manager, job_queue, nas_organizer, worker_manager)
    await agent_manager.start()
    await nas_organizer.start()
    await worker_manager.start()

    logger.info(f"Server ready on {settings.host}:{settings.port}")

    yield

    # Shutdown
    logger.info("Shutting down...")
    await agent_manager.stop()
    await nas_organizer.stop()
    await worker_manager.stop()


app = FastAPI(
    title="Boz Ripper Server",
    description="DVD/Blu-ray ripping orchestration server",
    version=__version__,
    lifespan=lifespan,
)

# CORS middleware for web UI (if added later)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(agents_router)
app.include_router(discs_router)
app.include_router(files_router)
app.include_router(jobs_router)
app.include_router(workers_router)


@app.get("/")
async def root() -> dict:
    """Root endpoint with server info."""
    return {
        "name": "Boz Ripper Server",
        "version": __version__,
        "status": "running",
    }


@app.get("/health")
async def health() -> dict:
    """Health check endpoint."""
    return {
        "status": "healthy",
        "version": __version__,
        "agents": len(agent_manager.get_all()),
        "workers": worker_manager.get_stats(),
        "queue": job_queue.get_queue_stats(),
        "nas": nas_organizer.get_status(),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "boz_server.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )

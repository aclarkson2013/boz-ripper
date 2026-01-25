"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from boz_server import __version__
from boz_server.api import agents_router, discs_router, files_router, jobs_router
from boz_server.api.workers import router as workers_router
from boz_server.api.thumbnails import router as thumbnails_router
from boz_server.api.vlc import router as vlc_router
from boz_server.api.deps import init_services
from boz_server.core.config import settings
from boz_server.database import init_db
from boz_server.services.agent_manager_db import AgentManager
from boz_server.services.discord_client import DiscordClient
from boz_server.services.job_queue_db import JobQueue
from boz_server.services.nas_organizer import NASOrganizer
from boz_server.services.plex_client import PlexClient
from boz_server.services.preview_generator_db import PreviewGenerator
from boz_server.services.thetvdb_client import TheTVDBClient
from boz_server.services.omdb_client import OMDbClient
from boz_server.services.thumbnail_storage import ThumbnailStorage
from boz_server.services.worker_manager_db import WorkerManager

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Service instances
agent_manager = AgentManager()
job_queue = JobQueue()
worker_manager = WorkerManager()  # Will set job_queue and discord_client after they're created

# Initialize Plex client (S19: Library scan after file organization)
plex_client = PlexClient() if settings.plex_enabled else None
if plex_client:
    logger.info("Plex integration enabled")
else:
    logger.info("Plex integration disabled")

# Initialize Discord client (S20: Webhook notifications)
discord_client = DiscordClient() if settings.discord_enabled else None
if discord_client:
    logger.info("Discord notifications enabled")
else:
    logger.info("Discord notifications disabled")

# Initialize NAS organizer with Plex and Discord clients
nas_organizer = NASOrganizer(plex_client=plex_client, discord_client=discord_client)

# S13: Wire up worker manager for failover support
worker_manager.set_job_queue(job_queue)
if discord_client:
    worker_manager.set_discord_client(discord_client)

# Initialize TheTVDB client if API key is configured
thetvdb_client = None
if settings.thetvdb_api_key:
    logger.info("TheTVDB API key configured, initializing client")
    thetvdb_client = TheTVDBClient(settings.thetvdb_api_key)
else:
    logger.warning("TheTVDB API key not configured, TV show metadata lookup will be disabled")

# Initialize OMDb client if API key is configured
omdb_client = None
if settings.omdb_api_key:
    logger.info("OMDb API key configured, initializing client")
    omdb_client = OMDbClient(settings.omdb_api_key)
else:
    logger.warning("OMDb API key not configured, movie metadata lookup will be disabled")

# Initialize thumbnail storage
thumbnail_storage = ThumbnailStorage(storage_path=f"{settings.temp_dir}/thumbnails")
logger.info("Thumbnail storage initialized")

# Initialize preview generator
preview_generator = PreviewGenerator(
    thetvdb_client=thetvdb_client,
    omdb_client=omdb_client,
    output_dir=settings.output_dir,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    logger.info(f"Starting Boz Ripper Server v{__version__}")

    # Initialize database
    logger.info("Initializing database...")
    await init_db()
    logger.info("Database initialized")

    init_services(
        agent_manager,
        job_queue,
        nas_organizer,
        worker_manager,
        preview_generator,
        thetvdb_client,
        thumbnail_storage,
        plex_client,
        discord_client,
    )
    await agent_manager.start()
    await nas_organizer.start()
    await worker_manager.start()
    if plex_client:
        await plex_client.start()
    if discord_client:
        await discord_client.start()

    logger.info(f"Server ready on {settings.host}:{settings.port}")

    yield

    # Shutdown
    logger.info("Shutting down...")
    await agent_manager.stop()
    await nas_organizer.stop()
    await worker_manager.stop()
    if plex_client:
        await plex_client.stop()
    if discord_client:
        await discord_client.stop()
    if thetvdb_client:
        await thetvdb_client.close()
    if omdb_client:
        await omdb_client.close()


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
app.include_router(thumbnails_router)
app.include_router(vlc_router)


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
        "agents": len(await agent_manager.get_all()),
        "workers": await worker_manager.get_stats(),
        "queue": await job_queue.get_queue_stats(),
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

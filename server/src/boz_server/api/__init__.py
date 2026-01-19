"""API routers."""

from .agents import router as agents_router
from .discs import router as discs_router
from .files import router as files_router
from .jobs import router as jobs_router

__all__ = ["agents_router", "discs_router", "files_router", "jobs_router"]

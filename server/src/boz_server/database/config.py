"""Database configuration."""

import os
from pathlib import Path


def get_database_url() -> str:
    """
    Get the database URL from environment or default.

    Returns:
        Database URL string
    """
    # Check for environment variable first
    if db_url := os.getenv("BOZ_DATABASE_URL"):
        return db_url

    # Default to SQLite in /data/database/
    db_dir = Path("/data/database")
    db_dir.mkdir(parents=True, exist_ok=True)
    db_path = db_dir / "boz_ripper.db"

    return f"sqlite+aiosqlite:///{db_path}"


def get_database_echo() -> bool:
    """
    Check if database query logging is enabled.

    Returns:
        True if SQL queries should be logged
    """
    return os.getenv("BOZ_DATABASE_ECHO", "false").lower() == "true"

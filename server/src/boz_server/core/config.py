"""Server configuration."""

from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Server configuration loaded from environment."""

    model_config = SettingsConfigDict(
        env_prefix="BOZ_",
        env_file=".env",
    )

    # Server settings
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    # API settings
    api_key: Optional[str] = None  # If set, require for agent auth

    # Storage paths
    temp_dir: str = "/data/temp"
    output_dir: str = "/data/output"

    # NAS settings
    nas_enabled: bool = False
    nas_host: str = ""
    nas_share: str = ""
    nas_username: str = ""
    nas_password: str = ""
    nas_movie_path: str = "Movies"
    nas_tv_path: str = "TV Shows"

    # Job settings
    max_concurrent_rips: int = 2
    max_concurrent_transcodes: int = 4
    default_transcode_preset: str = "Fast 1080p30"

    # Agent settings
    agent_timeout_seconds: int = 120  # Mark offline after this
    heartbeat_interval: int = 30

    # Worker settings
    worker_timeout_seconds: int = 90  # Mark worker offline after this
    worker_assignment_strategy: str = "priority"  # priority, round_robin, load_balance
    worker_auto_failover: bool = True  # Auto-reassign jobs if worker goes offline

    # TheTVDB settings
    thetvdb_api_key: Optional[str] = None  # TheTVDB v4 API key

    # Preview/extras filtering settings
    extras_min_duration_seconds: int = 600  # 10 minutes - titles shorter are likely extras
    extras_duration_variance: float = 0.4  # 40% - titles with >40% duration variance from median are likely extras
    auto_approve_previews: bool = False  # Auto-approve previews (bypass manual approval)

    # Database settings
    database_url: Optional[str] = None  # SQLite database URL (default: sqlite+aiosqlite:////data/database/boz_ripper.db)
    database_echo: bool = False  # Enable SQL query logging for debugging


settings = Settings()

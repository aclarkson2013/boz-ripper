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
    worker_assignment_strategy: str = "priority"  # priority, round_robin, load_balance, fastest_first
    worker_auto_failover: bool = True  # Auto-reassign jobs if worker goes offline

    # TheTVDB settings
    thetvdb_api_key: Optional[str] = None  # TheTVDB v4 API key

    # OMDb settings (for movie metadata)
    omdb_api_key: Optional[str] = None  # OMDb API key for movie lookup

    # Preview/extras filtering settings
    extras_min_duration_seconds: int = 600  # 10 minutes - titles shorter are likely extras
    extras_duration_variance: float = 0.4  # 40% - titles with >40% duration variance from median are likely extras
    auto_approve_previews: bool = False  # Auto-approve previews (bypass manual approval)

    # Database settings
    database_url: Optional[str] = None  # SQLite database URL (default: sqlite+aiosqlite:////data/database/boz_ripper.db)
    database_echo: bool = False  # Enable SQL query logging for debugging

    # Plex integration settings
    plex_enabled: bool = False  # Enable Plex library scan after file organization
    plex_url: str = "http://localhost:32400"  # Plex server URL
    plex_token: Optional[str] = None  # Plex authentication token
    plex_movie_library_id: Optional[str] = None  # Plex library section ID for Movies
    plex_tv_library_id: Optional[str] = None  # Plex library section ID for TV Shows
    plex_scan_delay_seconds: int = 2  # Delay before triggering scan (allows file system to sync)

    # Discord notification settings (S20)
    discord_enabled: bool = False  # Enable Discord webhook notifications
    discord_webhook_url: Optional[str] = None  # Discord webhook URL
    discord_notify_on_complete: bool = True  # Notify when transcode completes
    discord_notify_on_failure: bool = True  # Notify when job fails
    discord_notify_on_organized: bool = True  # Notify when file organized to NAS


settings = Settings()

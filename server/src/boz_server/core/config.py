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


settings = Settings()

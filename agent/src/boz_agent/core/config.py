"""Configuration management using Pydantic Settings."""

from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentConfig(BaseModel):
    """Agent identification settings."""

    id: Optional[str] = None
    name: str = "Boz Agent"


class ServerConfig(BaseModel):
    """Server connection settings."""

    url: str = "http://localhost:8000"
    api_key: str = ""
    timeout: int = 30
    retries: int = 3


class DiscDetectionConfig(BaseModel):
    """Disc detection settings."""

    enabled: bool = True
    poll_interval: int = 5
    drives: list[str] = Field(default_factory=list)


class MakeMKVConfig(BaseModel):
    """MakeMKV configuration."""

    executable: str = r"C:\Program Files (x86)\MakeMKV\makemkvcon64.exe"
    temp_dir: str = r"C:\BozRipper\temp"
    min_title_length: int = 120
    profile: Optional[str] = None


class ThumbnailConfig(BaseModel):
    """Thumbnail extraction configuration."""

    enabled: bool = True
    ffmpeg_path: str = "ffmpeg"  # Assumes ffmpeg is in PATH
    # Timestamps to extract (in seconds from start)
    timestamps: list[int] = Field(default_factory=lambda: [30, 120, 300])  # 0:30, 2:00, 5:00
    extract_midpoint: bool = True  # Also extract at 50% of duration
    quality: int = 2  # JPEG quality (2-31, lower is better)
    width: int = 320  # Thumbnail width (height auto-scaled)
    timeout: int = 30  # Timeout per thumbnail extraction


class WorkerConfig(BaseModel):
    """Local worker/transcoding settings."""

    enabled: bool = False
    worker_id: Optional[str] = None  # Auto-generated if not set
    priority: int = 1  # 1-99, lower = higher priority
    max_concurrent_jobs: int = 2

    # GPU settings
    nvenc: bool = False  # Auto-detect if not set
    nvenc_device: int = 0
    qsv: bool = False
    hevc: bool = True
    av1: bool = False

    output_dir: str = r"C:\BozRipper\output"


class HandBrakeConfig(BaseModel):
    """HandBrake configuration."""

    executable: str = r"C:\Program Files\HandBrake\HandBrakeCLI.exe"
    preset: str = "Fast 1080p30"
    presets_dir: Optional[str] = None


class LoggingConfig(BaseModel):
    """Logging configuration."""

    level: str = "INFO"
    file: Optional[str] = None
    max_size: int = 10
    backup_count: int = 5


class Settings(BaseSettings):
    """Main settings container."""

    model_config = SettingsConfigDict(
        env_prefix="BOZ_",
        env_nested_delimiter="__",
    )

    agent: AgentConfig = Field(default_factory=AgentConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    disc_detection: DiscDetectionConfig = Field(default_factory=DiscDetectionConfig)
    makemkv: MakeMKVConfig = Field(default_factory=MakeMKVConfig)
    thumbnails: ThumbnailConfig = Field(default_factory=ThumbnailConfig)
    worker: WorkerConfig = Field(default_factory=WorkerConfig)
    handbrake: HandBrakeConfig = Field(default_factory=HandBrakeConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    @classmethod
    def from_yaml(cls, path: Path) -> "Settings":
        """Load settings from a YAML file."""
        import yaml

        with open(path) as f:
            data = yaml.safe_load(f)

        return cls(**data) if data else cls()

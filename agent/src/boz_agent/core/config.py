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


class WorkerConfig(BaseModel):
    """Local worker/transcoding settings."""

    enabled: bool = False
    max_jobs: int = 1
    gpu_type: str = "none"
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

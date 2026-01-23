"""Main entry point for Boz Ripper Agent."""

import asyncio
import signal
import sys
from pathlib import Path
from typing import Optional

import structlog
import typer
from rich.console import Console

from boz_agent import __version__
from boz_agent.core.config import Settings
from boz_agent.services.disc_detector import DiscDetector
from boz_agent.services.job_runner import JobRunner
from boz_agent.services.makemkv import MakeMKVService
from boz_agent.services.server_client import ServerClient

app = typer.Typer(
    name="boz-agent",
    help="Boz Ripper Agent - Automated disc detection and ripping",
)
console = Console()
logger = structlog.get_logger()


class Agent:
    """Main agent orchestrator."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.running = False
        self._worker_id: Optional[str] = None

        # Initialize services
        self.server_client = ServerClient(settings.server)
        self.makemkv = MakeMKVService(settings.makemkv)
        self.disc_detector = DiscDetector(
            settings.disc_detection,
            on_disc_inserted=self.handle_disc_inserted,
            on_disc_ejected=self.handle_disc_ejected,
        )
        self.job_runner = JobRunner(
            settings=settings,
            server_client=self.server_client,
            makemkv=self.makemkv,
        )

    async def start(self) -> None:
        """Start the agent."""
        self.running = True
        logger.info(
            "agent_starting",
            agent_name=self.settings.agent.name,
            version=__version__,
            worker_enabled=self.settings.worker.enabled,
        )

        # Register with server as agent
        await self.server_client.register(self.settings.agent)

        # Register as worker if enabled
        if self.settings.worker.enabled:
            await self._register_worker()

        # Start disc detection
        if self.settings.disc_detection.enabled:
            await self.disc_detector.start()

        # Start job runner
        await self.job_runner.start()

        logger.info("agent_started")

    async def _register_worker(self) -> None:
        """Register this agent as a transcoding worker."""
        worker_id = await self.server_client.register_worker(
            worker_config=self.settings.worker,
            agent_name=self.settings.agent.name,
        )

        if worker_id:
            self._worker_id = worker_id
        else:
            self._worker_id = None
            logger.warning("worker_registration_failed")

    async def stop(self) -> None:
        """Stop the agent gracefully."""
        logger.info("agent_stopping")
        self.running = False

        # Stop worker (cancels heartbeat)
        await self.server_client.stop_worker()

        await self.job_runner.stop()
        await self.disc_detector.stop()
        await self.server_client.unregister()

        logger.info("agent_stopped")

    async def handle_disc_inserted(self, drive: str, disc_info: dict) -> None:
        """Handle a disc insertion event."""
        logger.info("disc_inserted", drive=drive, disc_info=disc_info)

        # Analyze disc with MakeMKV
        analysis = await self.makemkv.analyze_disc(drive)

        # Report to server
        await self.server_client.report_disc(drive, analysis)

    async def handle_disc_ejected(self, drive: str) -> None:
        """Handle a disc ejection event."""
        logger.info("disc_ejected", drive=drive)
        await self.server_client.report_disc_ejected(drive)


def load_settings(config_path: Optional[Path]) -> Settings:
    """Load settings from file or defaults."""
    if config_path and config_path.exists():
        logger.info("loading_config", path=str(config_path))
        return Settings.from_yaml(config_path)

    # Try default locations
    default_paths = [
        Path("config/config.yaml"),
        Path("config.yaml"),
        Path.home() / ".boz-agent" / "config.yaml",
    ]

    for path in default_paths:
        if path.exists():
            logger.info("loading_config", path=str(path))
            return Settings.from_yaml(path)

    logger.info("using_default_config")
    return Settings()


async def run_agent(settings: Settings) -> None:
    """Run the agent main loop."""
    agent = Agent(settings)

    # Set up signal handlers for graceful shutdown
    loop = asyncio.get_event_loop()

    def signal_handler():
        asyncio.create_task(agent.stop())

    if sys.platform != "win32":
        loop.add_signal_handler(signal.SIGINT, signal_handler)
        loop.add_signal_handler(signal.SIGTERM, signal_handler)

    try:
        await agent.start()

        # Keep running until stopped
        while agent.running:
            await asyncio.sleep(1)

    except KeyboardInterrupt:
        pass
    finally:
        await agent.stop()


@app.command()
def run(
    config: Optional[Path] = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to configuration file",
    ),
) -> None:
    """Run the Boz Ripper agent."""
    settings = load_settings(config)
    asyncio.run(run_agent(settings))


@app.command()
def version() -> None:
    """Show version information."""
    console.print(f"Boz Ripper Agent v{__version__}")


@app.command()
def check() -> None:
    """Check system requirements and configuration."""
    console.print("[bold]Boz Ripper Agent - System Check[/bold]\n")

    settings = load_settings(None)

    # Check MakeMKV
    makemkv_path = Path(settings.makemkv.executable)
    if makemkv_path.exists():
        console.print(f"[green][OK][/green] MakeMKV found: {makemkv_path}")
    else:
        console.print(f"[red][X][/red] MakeMKV not found: {makemkv_path}")

    # Check HandBrake
    handbrake_path = Path(settings.handbrake.executable)
    if handbrake_path.exists():
        console.print(f"[green][OK][/green] HandBrake found: {handbrake_path}")
    else:
        console.print(f"[yellow][!][/yellow] HandBrake not found: {handbrake_path}")
        console.print("  (Only needed if local transcoding is enabled)")

    # Check temp directory
    temp_dir = Path(settings.makemkv.temp_dir)
    if temp_dir.exists():
        console.print(f"[green][OK][/green] Temp directory exists: {temp_dir}")
    else:
        console.print(f"[yellow][!][/yellow] Temp directory missing: {temp_dir}")
        console.print("  (Will be created on first rip)")


if __name__ == "__main__":
    app()

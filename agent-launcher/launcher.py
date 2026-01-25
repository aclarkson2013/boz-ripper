"""Boz Ripper Agent - Windows System Tray Launcher.

A system tray application for managing the Boz Ripper Agent.
"""

import os
import sys
import subprocess
import threading
import time
import webbrowser
from pathlib import Path
from datetime import datetime

import psutil
import pystray
from PIL import Image, ImageDraw
from pystray import MenuItem as Item

# Try to import git, but handle gracefully if not available
try:
    import git
    GIT_AVAILABLE = True
except ImportError:
    GIT_AVAILABLE = False

# Configuration
DASHBOARD_URL = "http://10.0.0.60:5000"
AGENT_DIR = Path(__file__).parent.parent / "agent"
REPO_DIR = Path(__file__).parent.parent
LOG_FILE = Path(__file__).parent / "agent.log"
CHECK_INTERVAL = 5  # seconds between health checks


class AgentStatus:
    """Agent status enumeration."""
    STOPPED = "stopped"
    RUNNING = "running"
    UPDATING = "updating"
    STARTING = "starting"


class BozRipperLauncher:
    """System tray launcher for Boz Ripper Agent."""

    def __init__(self):
        self.status = AgentStatus.STOPPED
        self.agent_process = None
        self.icon = None
        self.monitor_thread = None
        self.running = True
        self.log_file = None

        # Ensure log file exists
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    def create_icon_image(self, color: str) -> Image.Image:
        """Create a simple colored circle icon."""
        size = 64
        image = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)

        # Color mapping
        colors = {
            "green": (34, 197, 94),    # Running
            "red": (239, 68, 68),       # Stopped
            "yellow": (234, 179, 8),    # Updating
            "blue": (59, 130, 246),     # Starting
        }
        fill_color = colors.get(color, colors["red"])

        # Draw filled circle with border
        padding = 4
        draw.ellipse(
            [padding, padding, size - padding, size - padding],
            fill=fill_color,
            outline=(255, 255, 255),
            width=2
        )

        # Draw "B" letter in center
        try:
            from PIL import ImageFont
            # Try to use a system font
            font = ImageFont.truetype("arial.ttf", 32)
        except:
            font = ImageFont.load_default()

        # Center the text
        text = "B"
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        x = (size - text_width) // 2
        y = (size - text_height) // 2 - 4
        draw.text((x, y), text, fill=(255, 255, 255), font=font)

        return image

    def update_icon(self):
        """Update the tray icon based on current status."""
        if not self.icon:
            return

        color_map = {
            AgentStatus.RUNNING: "green",
            AgentStatus.STOPPED: "red",
            AgentStatus.UPDATING: "yellow",
            AgentStatus.STARTING: "blue",
        }
        color = color_map.get(self.status, "red")
        self.icon.icon = self.create_icon_image(color)
        self.icon.title = f"Boz Ripper Agent - {self.status.capitalize()}"

    def notify(self, title: str, message: str):
        """Show a Windows notification."""
        if self.icon:
            try:
                self.icon.notify(message, title)
            except Exception as e:
                self.log(f"Notification error: {e}")

    def log(self, message: str):
        """Log a message to the log file."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"[{timestamp}] {message}\n"

        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(log_line)
        except Exception:
            pass

        print(log_line, end="")

    def is_agent_running(self) -> bool:
        """Check if the agent process is still running."""
        if self.agent_process is None:
            return False

        # Check if process is still alive
        poll = self.agent_process.poll()
        if poll is not None:
            return False

        # Double-check with psutil
        try:
            proc = psutil.Process(self.agent_process.pid)
            return proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return False

    def start_agent(self, icon=None, item=None):
        """Start the Boz Ripper Agent."""
        if self.is_agent_running():
            self.notify("Agent Already Running", "The agent is already running.")
            return

        self.status = AgentStatus.STARTING
        self.update_icon()
        self.log("Starting agent...")

        try:
            # Ensure agent directory exists
            if not AGENT_DIR.exists():
                self.notify("Error", f"Agent directory not found: {AGENT_DIR}")
                self.status = AgentStatus.STOPPED
                self.update_icon()
                return

            # Open log file for agent output
            self.log_file = open(LOG_FILE, "a", encoding="utf-8")

            # Set up environment with PYTHONPATH pointing to agent/src
            env = os.environ.copy()
            agent_src = AGENT_DIR / "src"
            env["PYTHONPATH"] = str(agent_src)

            # Start the agent process
            self.agent_process = subprocess.Popen(
                [sys.executable, "-m", "boz_agent", "run"],
                cwd=str(AGENT_DIR),
                env=env,
                stdout=self.log_file,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )

            # Wait a moment and check if it started successfully
            time.sleep(2)

            if self.is_agent_running():
                self.status = AgentStatus.RUNNING
                self.log(f"Agent started with PID {self.agent_process.pid}")
                self.notify("Agent Started", "Boz Ripper Agent is now running.")
            else:
                self.status = AgentStatus.STOPPED
                self.log("Agent failed to start")
                self.notify("Start Failed", "Agent failed to start. Check logs for details.")

        except Exception as e:
            self.status = AgentStatus.STOPPED
            self.log(f"Error starting agent: {e}")
            self.notify("Error", f"Failed to start agent: {e}")

        self.update_icon()

    def stop_agent(self, icon=None, item=None):
        """Stop the Boz Ripper Agent."""
        if not self.is_agent_running():
            self.notify("Agent Not Running", "The agent is not currently running.")
            self.status = AgentStatus.STOPPED
            self.update_icon()
            return

        self.log("Stopping agent...")

        try:
            # Try graceful termination first
            process = psutil.Process(self.agent_process.pid)

            # Terminate child processes first
            children = process.children(recursive=True)
            for child in children:
                try:
                    child.terminate()
                except psutil.NoSuchProcess:
                    pass

            # Terminate main process
            process.terminate()

            # Wait for graceful shutdown
            try:
                process.wait(timeout=10)
            except psutil.TimeoutExpired:
                # Force kill if still running
                self.log("Agent not responding, forcing kill...")
                process.kill()
                for child in children:
                    try:
                        child.kill()
                    except psutil.NoSuchProcess:
                        pass

            self.agent_process = None
            self.status = AgentStatus.STOPPED
            self.log("Agent stopped")
            self.notify("Agent Stopped", "Boz Ripper Agent has been stopped.")

        except Exception as e:
            self.log(f"Error stopping agent: {e}")
            self.notify("Error", f"Failed to stop agent: {e}")

        # Close log file
        if self.log_file:
            try:
                self.log_file.close()
            except:
                pass
            self.log_file = None

        self.update_icon()

    def restart_agent(self, icon=None, item=None):
        """Restart the Boz Ripper Agent."""
        self.log("Restarting agent...")
        was_running = self.is_agent_running()

        if was_running:
            self.stop_agent()
            time.sleep(2)

        self.start_agent()

    def check_for_updates(self, icon=None, item=None):
        """Check for updates and apply if available."""
        if not GIT_AVAILABLE:
            self.notify("Git Not Available", "GitPython is not installed. Cannot check for updates.")
            return

        self.log("Checking for updates...")
        previous_status = self.status
        was_running = self.is_agent_running()

        self.status = AgentStatus.UPDATING
        self.update_icon()

        try:
            repo = git.Repo(REPO_DIR)

            # Fetch latest changes
            origin = repo.remotes.origin
            origin.fetch()

            # Check if we're behind
            local_commit = repo.head.commit
            remote_commit = origin.refs.main.commit

            if local_commit == remote_commit:
                self.log("Already up to date")
                self.notify("No Updates", "Boz Ripper is already up to date.")
                self.status = previous_status
                self.update_icon()
                return

            # Pull updates
            self.log("Updates found, pulling...")
            origin.pull()

            # Install requirements
            self.log("Installing updated requirements...")
            requirements_file = AGENT_DIR / "requirements.txt"
            if requirements_file.exists():
                subprocess.run(
                    [sys.executable, "-m", "pip", "install", "-r", str(requirements_file)],
                    cwd=str(AGENT_DIR),
                    capture_output=True,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                )

            self.log("Update complete")
            self.notify("Updated", "Boz Ripper has been updated successfully!")

            # Restart agent if it was running
            if was_running:
                self.log("Restarting agent after update...")
                time.sleep(1)
                self.start_agent()
            else:
                self.status = AgentStatus.STOPPED
                self.update_icon()

        except Exception as e:
            self.log(f"Update error: {e}")
            self.notify("Update Failed", f"Failed to update: {e}")
            self.status = previous_status
            self.update_icon()

    def open_dashboard(self, icon=None, item=None):
        """Open the dashboard in the default browser."""
        self.log(f"Opening dashboard: {DASHBOARD_URL}")
        webbrowser.open(DASHBOARD_URL)

    def view_logs(self, icon=None, item=None):
        """Open the log file in the default text editor."""
        if LOG_FILE.exists():
            self.log("Opening log file...")
            os.startfile(str(LOG_FILE))
        else:
            self.notify("No Logs", "Log file does not exist yet.")

    def exit_app(self, icon=None, item=None):
        """Exit the launcher application."""
        self.log("Exiting launcher...")
        self.running = False

        # Stop agent if running
        if self.is_agent_running():
            self.stop_agent()

        # Stop the icon
        if self.icon:
            self.icon.stop()

    def monitor_agent(self):
        """Background thread to monitor agent health."""
        last_status = None

        while self.running:
            try:
                current_running = self.is_agent_running()

                # Detect status changes
                if self.status == AgentStatus.RUNNING and not current_running:
                    # Agent crashed
                    self.status = AgentStatus.STOPPED
                    self.update_icon()
                    self.log("Agent crashed or stopped unexpectedly!")
                    self.notify("Agent Crashed", "The agent has stopped unexpectedly. Check logs for details.")
                    self.agent_process = None

                elif self.status == AgentStatus.STOPPED and current_running:
                    # Agent started externally
                    self.status = AgentStatus.RUNNING
                    self.update_icon()

                # Update icon if status changed
                if self.status != last_status:
                    self.update_icon()
                    last_status = self.status

            except Exception as e:
                self.log(f"Monitor error: {e}")

            time.sleep(CHECK_INTERVAL)

    def create_menu(self):
        """Create the system tray menu."""
        def get_status_text(item):
            status_emoji = {
                AgentStatus.RUNNING: "Running",
                AgentStatus.STOPPED: "Stopped",
                AgentStatus.UPDATING: "Updating...",
                AgentStatus.STARTING: "Starting...",
            }
            return f"Status: {status_emoji.get(self.status, 'Unknown')}"

        return pystray.Menu(
            Item(get_status_text, None, enabled=False),
            pystray.Menu.SEPARATOR,
            Item("Start Agent", self.start_agent, enabled=lambda item: not self.is_agent_running()),
            Item("Stop Agent", self.stop_agent, enabled=lambda item: self.is_agent_running()),
            Item("Restart Agent", self.restart_agent),
            pystray.Menu.SEPARATOR,
            Item("Open Dashboard", self.open_dashboard),
            Item("Check for Updates", self.check_for_updates),
            Item("View Logs", self.view_logs),
            pystray.Menu.SEPARATOR,
            Item("Exit", self.exit_app),
        )

    def run(self):
        """Run the system tray application."""
        self.log("=" * 50)
        self.log("Boz Ripper Agent Launcher starting...")
        self.log(f"Agent directory: {AGENT_DIR}")
        self.log(f"Repository directory: {REPO_DIR}")

        # Check for updates on startup
        if GIT_AVAILABLE:
            threading.Thread(target=self.check_for_updates, daemon=True).start()

        # Start the monitor thread
        self.monitor_thread = threading.Thread(target=self.monitor_agent, daemon=True)
        self.monitor_thread.start()

        # Create and run the system tray icon
        self.icon = pystray.Icon(
            "BozRipperAgent",
            self.create_icon_image("red"),
            "Boz Ripper Agent - Stopped",
            self.create_menu(),
        )

        self.log("Launcher ready")
        self.notify("Launcher Started", "Boz Ripper Agent Launcher is running.")

        # Auto-start agent on launch
        threading.Thread(target=self._delayed_start, daemon=True).start()

        # Run the icon (blocking)
        self.icon.run()

    def _delayed_start(self):
        """Start agent after a short delay (allows update to complete first)."""
        time.sleep(5)  # Wait for update check
        if not self.is_agent_running() and self.status != AgentStatus.UPDATING:
            self.start_agent()


def main():
    """Main entry point."""
    launcher = BozRipperLauncher()
    try:
        launcher.run()
    except KeyboardInterrupt:
        launcher.exit_app()
    except Exception as e:
        print(f"Fatal error: {e}")
        launcher.exit_app()


if __name__ == "__main__":
    main()

"""Boz Ripper Agent - Windows System Tray Launcher.

A system tray application for managing the Boz Ripper Agent.
Single instance only - prevents multiple launchers and agents.
"""

import os
import sys
import subprocess
import threading
import time
import webbrowser
import tempfile
import ctypes
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
CHECK_INTERVAL = 5  # seconds between health checks
LOCK_FILE_NAME = "boz_ripper_launcher.lock"
AGENT_PROCESS_NAME = "boz_agent"

# Detect if running as PyInstaller exe or as script
if getattr(sys, 'frozen', False):
    # Running as compiled exe - exe is in agent-launcher/dist/
    LAUNCHER_DIR = Path(sys.executable).parent
    # Go up from dist/ to agent-launcher/, then up to boz-ripper/
    REPO_DIR = LAUNCHER_DIR.parent.parent
else:
    # Running as script
    LAUNCHER_DIR = Path(__file__).parent
    REPO_DIR = LAUNCHER_DIR.parent

AGENT_DIR = REPO_DIR / "agent"
LOG_FILE = LAUNCHER_DIR / "agent.log"
LOCK_FILE = Path(tempfile.gettempdir()) / LOCK_FILE_NAME


class SingleInstanceChecker:
    """Ensures only one instance of the launcher runs at a time."""

    def __init__(self):
        self.lock_file = None
        self.locked = False

    def try_acquire(self) -> bool:
        """Try to acquire the single instance lock. Returns True if successful."""
        try:
            # Check if lock file exists and if the process is still running
            if LOCK_FILE.exists():
                try:
                    with open(LOCK_FILE, "r") as f:
                        old_pid = int(f.read().strip())

                    # Check if the old process is still running
                    if psutil.pid_exists(old_pid):
                        try:
                            proc = psutil.Process(old_pid)
                            # Check if it's actually our launcher
                            if "python" in proc.name().lower() or "bozripperagent" in proc.name().lower():
                                return False  # Another instance is running
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass  # Process doesn't exist or can't access, OK to proceed
                except (ValueError, IOError):
                    pass  # Invalid lock file, OK to overwrite

            # Create/update lock file with our PID
            with open(LOCK_FILE, "w") as f:
                f.write(str(os.getpid()))

            self.locked = True
            return True

        except Exception:
            return False

    def release(self):
        """Release the lock."""
        if self.locked:
            try:
                LOCK_FILE.unlink(missing_ok=True)
            except Exception:
                pass
            self.locked = False


def find_existing_agent_processes():
    """Find any existing boz_agent Python processes."""
    agents = []
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = proc.info.get('cmdline') or []
            cmdline_str = ' '.join(cmdline).lower()

            # Check if this is a boz_agent process
            if 'boz_agent' in cmdline_str and 'python' in proc.info.get('name', '').lower():
                agents.append(proc.info['pid'])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return agents


def kill_existing_agents():
    """Kill any existing boz_agent processes."""
    agents = find_existing_agent_processes()
    for pid in agents:
        try:
            proc = psutil.Process(pid)
            proc.terminate()
            proc.wait(timeout=5)
        except (psutil.NoSuchProcess, psutil.TimeoutExpired):
            try:
                proc.kill()
            except psutil.NoSuchProcess:
                pass
        except Exception:
            pass
    return len(agents)


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
        self.log_file_handle = None
        self.agent_pid = None  # Track the agent PID we started

        # Ensure log directory exists
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
        # First check our tracked process
        if self.agent_process is not None:
            poll = self.agent_process.poll()
            if poll is None:
                # Process is still running
                try:
                    proc = psutil.Process(self.agent_process.pid)
                    if proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE:
                        return True
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

        # Also check by PID if we have one
        if self.agent_pid:
            try:
                proc = psutil.Process(self.agent_pid)
                if proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE:
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        return False

    def start_agent(self, icon=None, item=None):
        """Start the Boz Ripper Agent."""
        # Check if already running (our process)
        if self.is_agent_running():
            self.notify("Agent Already Running", "The agent is already running.")
            return

        # Check for any other agent processes
        existing = find_existing_agent_processes()
        if existing:
            self.log(f"Found {len(existing)} existing agent process(es), killing them...")
            kill_existing_agents()
            time.sleep(1)

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

            # Close any existing log file handle
            if self.log_file_handle:
                try:
                    self.log_file_handle.close()
                except:
                    pass

            # Open log file for agent output
            self.log_file_handle = open(LOG_FILE, "a", encoding="utf-8")

            # Set up environment with PYTHONPATH pointing to agent/src
            env = os.environ.copy()
            agent_src = AGENT_DIR / "src"
            env["PYTHONPATH"] = str(agent_src)

            # Start the agent process
            self.agent_process = subprocess.Popen(
                [sys.executable, "-m", "boz_agent", "run"],
                cwd=str(AGENT_DIR),
                env=env,
                stdout=self.log_file_handle,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )

            self.agent_pid = self.agent_process.pid

            # Wait a moment and check if it started successfully
            time.sleep(2)

            if self.is_agent_running():
                self.status = AgentStatus.RUNNING
                self.log(f"Agent started with PID {self.agent_pid}")
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
            # Also kill any orphaned agents
            existing = find_existing_agent_processes()
            if existing:
                self.log(f"Killing {len(existing)} orphaned agent process(es)...")
                kill_existing_agents()
            else:
                self.notify("Agent Not Running", "The agent is not currently running.")
            self.status = AgentStatus.STOPPED
            self.update_icon()
            return

        self.log("Stopping agent...")

        try:
            pid_to_kill = self.agent_pid or (self.agent_process.pid if self.agent_process else None)

            if pid_to_kill:
                process = psutil.Process(pid_to_kill)

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
            self.agent_pid = None
            self.status = AgentStatus.STOPPED
            self.log("Agent stopped")
            self.notify("Agent Stopped", "Boz Ripper Agent has been stopped.")

        except psutil.NoSuchProcess:
            self.log("Agent process already terminated")
            self.agent_process = None
            self.agent_pid = None
            self.status = AgentStatus.STOPPED
        except Exception as e:
            self.log(f"Error stopping agent: {e}")
            self.notify("Error", f"Failed to stop agent: {e}")

        # Close log file handle
        if self.log_file_handle:
            try:
                self.log_file_handle.close()
            except:
                pass
            self.log_file_handle = None

        self.update_icon()

    def restart_agent(self, icon=None, item=None):
        """Restart the Boz Ripper Agent."""
        self.log("Restarting agent...")

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
                self.restart_agent()
            else:
                self.status = AgentStatus.STOPPED
                self.update_icon()

        except Exception as e:
            self.log(f"Update error: {e}")
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
                    self.agent_pid = None

                elif self.status == AgentStatus.STOPPED and current_running:
                    # Agent started externally (shouldn't happen with single instance)
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

        # Kill any orphaned agents from previous runs
        existing = find_existing_agent_processes()
        if existing:
            self.log(f"Cleaning up {len(existing)} orphaned agent process(es)...")
            kill_existing_agents()

        # Check for updates on startup (in background, don't notify if up to date)
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

        # Auto-start agent on launch (after a delay for update check)
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
    # Check for single instance
    instance_checker = SingleInstanceChecker()

    if not instance_checker.try_acquire():
        # Another instance is already running
        # Show a message box on Windows
        if sys.platform == "win32":
            ctypes.windll.user32.MessageBoxW(
                0,
                "Boz Ripper Agent Launcher is already running.\n\nCheck your system tray for the icon.",
                "Already Running",
                0x40  # MB_ICONINFORMATION
            )
        else:
            print("Boz Ripper Agent Launcher is already running.")
        sys.exit(0)

    try:
        launcher = BozRipperLauncher()
        launcher.run()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Fatal error: {e}")
    finally:
        instance_checker.release()


if __name__ == "__main__":
    main()

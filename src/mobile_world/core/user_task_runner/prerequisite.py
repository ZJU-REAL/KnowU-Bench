"""Environment prerequisite checks and cleanup utilities."""

import os
import shutil
import subprocess
import sys
import time

import requests
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

_ADB_KEYBOARD_APK_URL = "https://github.com/senzhk/ADBKeyBoard/raw/master/ADBKeyboard.apk"
_ADB_KEYBOARD_PACKAGE = "com.android.adbkeyboard"
_ADB_KEYBOARD_IME = "com.android.adbkeyboard/.AdbIME"
_ADB_KEYBOARD_APK_PATH = "/tmp/ADBKeyboard.apk"

_adb_keyboard_installed_by_us = False
_server_process = None

_console = Console()


def _check_adb_exists() -> bool:
    """Check if adb command is available."""
    return shutil.which("adb") is not None


def _check_adb_keyboard_installed(device: str = "emulator-5554") -> bool:
    """Check if ADB Keyboard is installed on the device."""
    try:
        result = subprocess.run(
            ["adb", "-s", device, "shell", "pm", "list", "packages", _ADB_KEYBOARD_PACKAGE],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return _ADB_KEYBOARD_PACKAGE in result.stdout
    except Exception:
        return False


def _activate_adb_keyboard(device: str = "emulator-5554") -> bool:
    """Activate ADB Keyboard by enabling and setting it as the default IME."""
    try:
        subprocess.run(
            ["adb", "-s", device, "shell", "ime", "enable", _ADB_KEYBOARD_IME],
            capture_output=True,
            timeout=10,
        )
        subprocess.run(
            ["adb", "-s", device, "shell", "ime", "set", _ADB_KEYBOARD_IME],
            capture_output=True,
            timeout=10,
        )
        return True
    except Exception:
        return False


def _install_adb_keyboard(device: str = "emulator-5554") -> bool:
    """Download and install ADB Keyboard on the device."""
    global _adb_keyboard_installed_by_us

    _console.print("[cyan]Downloading ADB Keyboard APK...[/cyan]")
    try:
        response = requests.get(_ADB_KEYBOARD_APK_URL, timeout=30)
        response.raise_for_status()
        with open(_ADB_KEYBOARD_APK_PATH, "wb") as f:
            f.write(response.content)
    except Exception as e:
        _console.print(f"[red]Failed to download ADB Keyboard: {e}[/red]")
        return False

    _console.print("[cyan]Installing ADB Keyboard...[/cyan]")
    try:
        result = subprocess.run(
            ["adb", "-s", device, "install", _ADB_KEYBOARD_APK_PATH],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            _console.print(f"[red]Failed to install APK: {result.stderr}[/red]")
            return False

        subprocess.run(
            ["adb", "-s", device, "shell", "ime", "enable", _ADB_KEYBOARD_IME],
            capture_output=True,
            timeout=10,
        )
        subprocess.run(
            ["adb", "-s", device, "shell", "ime", "set", _ADB_KEYBOARD_IME],
            capture_output=True,
            timeout=10,
        )

        _adb_keyboard_installed_by_us = True
        _console.print("[green]ADB Keyboard installed and enabled successfully.[/green]")
        return True
    except Exception as e:
        _console.print(f"[red]Failed to install ADB Keyboard: {e}[/red]")
        return False


def _start_server_background(port: int = 6800, suite_family: str = "mobile_world") -> str | None:
    """Start the MobileWorld server in the background."""
    global _server_process

    _console.print(f"[cyan]Starting MobileWorld server on port {port}...[/cyan]")

    try:
        _server_process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "mobile_world.core.server:app",
                "--host",
                "0.0.0.0",
                "--port",
                str(port),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        server_url = f"http://localhost:{port}"
        for _ in range(30):
            poll_result = _server_process.poll()
            if poll_result is not None:
                _, stderr = _server_process.communicate(timeout=1)
                error_msg = stderr.decode() if stderr else "Unknown error"
                if "address already in use" in error_msg.lower():
                    _console.print(f"[red]Port {port} is already in use.[/red]")
                else:
                    _console.print(f"[red]Server failed to start: {error_msg.strip()}[/red]")
                _server_process = None
                return None

            time.sleep(1)
            try:
                requests.get(f"{server_url}/health", timeout=2)
                _console.print(f"[green]Server started at {server_url}[/green]")
                return server_url
            except Exception:
                continue

        _console.print("[red]Server failed to start within timeout.[/red]")
        if _server_process:
            _server_process.terminate()
            _server_process = None
        return None

    except Exception as e:
        _console.print(f"[red]Failed to start server: {e}[/red]")
        return None


def _deactivate_adb_keyboard(device: str = "emulator-5554") -> bool:
    """Deactivate ADB Keyboard by switching to default IME."""
    try:
        subprocess.run(
            ["adb", "-s", device, "shell", "ime", "reset"],
            capture_output=True,
            timeout=10,
        )
        return True
    except Exception:
        return False


def _uninstall_adb_keyboard(device: str = "emulator-5554") -> bool:
    """Uninstall ADB Keyboard from the device."""
    try:
        result = subprocess.run(
            ["adb", "-s", device, "uninstall", _ADB_KEYBOARD_PACKAGE],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode == 0
    except Exception:
        return False


def env_validation(aw_url: str | None, device: str = "emulator-5554") -> str:
    """Validate environment prerequisites and return the server URL.

    Args:
        aw_url: The Android World server URL (if None, will start server)
        device: The ADB device ID

    Returns:
        str: The server URL to use

    Raises:
        SystemExit: If any prerequisite check fails
    """
    _console.print(
        Panel(
            "[bold]Checking environment prerequisites...[/bold]",
            title="[bold cyan]🔍 Environment Validation",
            border_style="cyan",
        )
    )

    if not _check_adb_exists():
        _console.print(
            Panel(
                "[bold red]ADB (Android Debug Bridge) not found![/bold red]\n\n"
                "[yellow]Please install ADB:[/yellow]\n\n"
                "1. Download the official ADB package:\n"
                "   [link=https://developer.android.com/tools/releases/platform-tools]"
                "https://developer.android.com/tools/releases/platform-tools[/link]\n\n"
                "2. Extract and configure PATH:\n\n"
                "[bold]MacOS:[/bold]\n"
                "   [cyan]export PATH=${{PATH}}:~/Downloads/platform-tools[/cyan]\n\n"
                "[bold]Windows:[/bold]\n"
                "   Add platform-tools directory to system PATH\n"
                "   Reference: [link=https://blog.csdn.net/x2584179909/article/details/108319973]"
                "https://blog.csdn.net/x2584179909/article/details/108319973[/link]",
                title="[bold red]❌ ADB Not Found",
                border_style="red",
            )
        )
        sys.exit(1)

    _console.print("[green]✓ ADB found[/green]")

    server_url = aw_url
    if server_url is None:
        server_url = _start_server_background()
        if server_url is None:
            _console.print(
                Panel(
                    "[bold red]Failed to start MobileWorld server![/bold red]\n\n"
                    "[yellow]You can start the server manually:[/yellow]\n\n"
                    "   [cyan]mobile-world server --port 6800[/cyan]\n\n"
                    "Or run inside Docker container:\n\n"
                    "   [cyan]mobile-world env launch[/cyan]",
                    title="[bold red]❌ Server Start Failed",
                    border_style="red",
                )
            )
            sys.exit(1)
    else:
        _console.print(f"[green]✓ Using provided server URL: {server_url}[/green]")

    if not _check_adb_keyboard_installed(device):
        _console.print("[yellow]⚠ ADB Keyboard not found, installing...[/yellow]")
        if not _install_adb_keyboard(device):
            _console.print(
                Panel(
                    "[bold red]Failed to install ADB Keyboard![/bold red]\n\n"
                    "[yellow]Please install manually:[/yellow]\n\n"
                    "1. Download APK:\n"
                    "   [link=https://github.com/senzhk/ADBKeyBoard/blob/master/ADBKeyboard.apk]"
                    "https://github.com/senzhk/ADBKeyBoard/blob/master/ADBKeyboard.apk[/link]\n\n"
                    "2. Install and enable:\n"
                    f"   [cyan]adb -s {device} install ADBKeyboard.apk[/cyan]\n"
                    f"   [cyan]adb -s {device} shell ime enable {_ADB_KEYBOARD_IME}[/cyan]\n"
                    f"   [cyan]adb -s {device} shell ime set {_ADB_KEYBOARD_IME}[/cyan]",
                    title="[bold red]❌ ADB Keyboard Installation Failed",
                    border_style="red",
                )
            )
            sys.exit(1)
    else:
        _console.print("[green]✓ ADB Keyboard installed[/green]")
        _activate_adb_keyboard(device)
        _console.print("[green]✓ ADB Keyboard activated[/green]")

    _console.print(
        Panel(
            "[bold green]All prerequisites satisfied![/bold green]",
            title="[bold green]✓ Environment Ready",
            border_style="green",
        )
    )

    return server_url


def env_cleanup(device: str = "emulator-5554"):
    """Clean up environment resources."""
    global _adb_keyboard_installed_by_us, _server_process

    if _adb_keyboard_installed_by_us:
        _console.print("[cyan]Deactivating ADB Keyboard...[/cyan]")
        if _deactivate_adb_keyboard(device):
            _console.print("[green]ADB Keyboard deactivated.[/green]")
        else:
            _console.print("[yellow]Failed to deactivate ADB Keyboard.[/yellow]")

        _console.print()
        should_uninstall = Prompt.ask(
            "[bold yellow]Do you want to uninstall ADB Keyboard?[/bold yellow]",
            choices=["y", "n"],
            default="n",
        )

        if should_uninstall.lower() == "y":
            _console.print("[cyan]Uninstalling ADB Keyboard...[/cyan]")
            if _uninstall_adb_keyboard(device):
                _console.print("[green]ADB Keyboard uninstalled.[/green]")
            else:
                _console.print("[yellow]Failed to uninstall ADB Keyboard.[/yellow]")

        _adb_keyboard_installed_by_us = False

    if os.path.exists(_ADB_KEYBOARD_APK_PATH):
        try:
            os.remove(_ADB_KEYBOARD_APK_PATH)
        except Exception:
            pass

    if _server_process is not None:
        _console.print("[cyan]Stopping MobileWorld server...[/cyan]")
        try:
            _server_process.terminate()
            _server_process.wait(timeout=5)
            _console.print("[green]Server stopped.[/green]")
        except Exception:
            _server_process.kill()
        _server_process = None

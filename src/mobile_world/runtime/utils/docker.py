"""Docker utility helpers for MobileWorld CLI.

This module centralizes common Docker operations (run, ps, inspect, exec, rm)
and a consistent command runner with improved error messaging.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Iterable
from typing import Any

from loguru import logger


def run_command(
    cmd: list[str],
    capture: bool = True,
    allowed_exit_codes: set[int] | None = None,
) -> subprocess.CompletedProcess:
    """Run a shell command, logging failures and exiting on error.

    For Docker commands, provide a clearer message when permission errors occur.

    Args:
        cmd: Command to run as list of strings
        capture: Whether to capture stdout/stderr
        allowed_exit_codes: Set of exit codes to treat as success (in addition to 0)
    """
    try:
        if capture:
            result = subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
            )
        else:
            result = subprocess.run(cmd, check=True)
        return result
    except subprocess.CalledProcessError as e:
        # Check if this exit code is allowed
        if allowed_exit_codes and e.returncode in allowed_exit_codes:
            logger.debug(
                "Command returned allowed exit code {}: {}",
                e.returncode,
                " ".join(cmd),
            )
            # Return a successful CompletedProcess with the actual exit code
            return subprocess.CompletedProcess(
                args=e.cmd,
                returncode=e.returncode,
                stdout=e.stdout,
                stderr=e.stderr,
            )

        stderr_text = e.stderr or ""
        logger.error("Command failed: {}", " ".join(cmd))
        logger.error("Exit code: {}", e.returncode)
        if stderr_text:
            logger.error("Error output: {}", stderr_text)
            if "permission denied" in stderr_text.lower() and "docker" in stderr_text.lower():
                _log_docker_permission_help()
        sys.exit(1)


def _log_docker_permission_help() -> None:
    logger.error("{}", "=" * 80)
    logger.error("Docker Permission Error Detected")
    logger.error("{}", "=" * 80)
    logger.error("Your user doesn't have permission to access the Docker daemon.")
    logger.error("To fix this issue, try one of the following:")
    logger.error("  1. Add your user to the docker group:")
    logger.error("     $ sudo usermod -aG docker $USER")
    logger.error("     $ newgrp docker")
    logger.error("  2. Run the command with sudo:")
    logger.error("     $ sudo mobile-world env list")
    logger.error("  3. Check Docker daemon is running:")
    logger.error("     $ sudo systemctl status docker")


def docker_ps(include_all: bool = False) -> list[dict[str, Any]]:
    """Return a list of containers from `docker ps` as dicts."""
    cmd = ["docker", "ps", "--format", "{{json .}}"]
    if include_all:
        cmd.insert(2, "-a")
    result = run_command(cmd)
    containers: list[dict[str, Any]] = []
    for line in (result.stdout or "").strip().split("\n"):
        if not line:
            continue
        try:
            containers.append(json.loads(line))
        except json.JSONDecodeError:
            logger.debug("Skipping unparsable docker ps line: {}", line)
    return containers


def list_containers_by_image_substring(
    image_substring: str, *, include_all: bool = False
) -> list[dict[str, Any]]:
    """Filter `docker ps` by image substring (case-insensitive)."""
    substring = (image_substring or "").lower()
    return [
        c for c in docker_ps(include_all=include_all) if substring in (c.get("Image", "").lower())
    ]


def docker_inspect(container_name: str) -> dict[str, Any] | None:
    """Return `docker inspect` result for a container or None if missing."""
    result = run_command(["docker", "inspect", container_name])
    try:
        data = json.loads(result.stdout or "[]")
        return data[0] if data else None
    except json.JSONDecodeError:
        logger.error("Failed to parse docker inspect output for {}", container_name)
        return None


def docker_rm(container_name: str, *, force: bool = True) -> None:
    """Remove a container by name."""
    cmd = ["docker", "rm"]
    if force:
        cmd.append("-f")
    cmd.append(container_name)
    run_command(cmd)


def build_run_command(
    *,
    name: str,
    image: str,
    port_mappings: Iterable[tuple[int, int]] | None = None,  # (host, container)
    env_vars: dict[str, str] | None = None,
    volumes: Iterable[tuple[str, str]] | None = None,  # (host, container)
    detach: bool = True,
    privileged: bool = True,
    remove: bool = True,
) -> list[str]:
    """Construct a `docker run` command list with common flags."""
    cmd: list[str] = [
        "docker",
        "run",
    ]
    if remove:
        cmd.append("--rm")
    if privileged:
        cmd.append("--privileged")
    cmd.extend(["--name", name])

    for host_port, container_port in port_mappings or []:
        cmd.extend(["-p", f"{host_port}:{container_port}"])

    for host_path, container_path in volumes or []:
        cmd.extend(["-v", f"{host_path}:{container_path}"])

    for key, value in (env_vars or {}).items():
        cmd.extend(["-e", f"{key}={value}"])

    if detach:
        cmd.append("-d")

    cmd.append(image)
    return cmd


def docker_exec_bash(
    container_name: str,
    bash_command: str,
    *,
    detach: bool = False,
    allowed_exit_codes: set[int] | None = None,
) -> None:
    """Execute a bash command in a container. Detach if requested.

    Args:
        container_name: Name of the container to exec into
        bash_command: Bash command to execute
        detach: Run in detached mode
        allowed_exit_codes: Set of exit codes to treat as success (in addition to 0)
    """
    base = ["docker", "exec"]
    if detach:
        base.append("-d")
    base.extend(
        [
            container_name,
            "/bin/bash",
            "-c",
            bash_command,
        ]
    )
    run_command(base, allowed_exit_codes=allowed_exit_codes)


def docker_exec_replace(container_name: str, command: str, *, interactive: bool = True) -> None:
    """Replace current process with `docker exec` into a container."""
    cmd = ["docker", "exec"]
    if interactive:
        cmd.append("-it")
    cmd.extend([container_name, "/bin/bash", "-c", command])
    # Replace current process to properly handle terminal I/O
    os.execvp("docker", cmd)


def discover_backends(
    image_filter: str = "knowu_bench", prefix: str = "knowu_bench_env"
) -> tuple[list[str], list[str]]:
    """Discover backend URLs from running containers.

    Args:
        image_filter: Image name substring to filter containers (default: mobile_world)

    Returns:
        list[str]: List of backend URLs in format http://localhost:PORT
    """
    containers = list_containers_by_image_substring(image_filter, include_all=False)

    if not containers:
        logger.warning("No running containers found with image filter: {}", image_filter)
        return [], []

    backend_urls = []
    container_names = []
    for container in containers:
        container_name = container.get("Names", "")
        if not container_name or not container_name.startswith(prefix):
            continue

        container_info = docker_inspect(container_name)
        if not container_info:
            continue

        ports = container_info.get("NetworkSettings", {}).get("Ports", {})
        for container_port, host_bindings in ports.items():
            if "6800/tcp" in container_port and host_bindings:
                host_port = host_bindings[0].get("HostPort", "")
                if host_port:
                    backend_url = f"http://localhost:{host_port}"
                    backend_urls.append(backend_url)
                    logger.info(
                        "Discovered backend: {} (container: {})", backend_url, container_name
                    )
                    break
        container_names.append(container_name)
    return backend_urls, container_names


def restart_emulator_with_avd(avd_name: str) -> str:
    """Restart emulator with the specified AVD using existing script.

    This function calls the existing /app/docker/start_emulator.sh script

    Args:
        avd_name: Name of the AVD to start

    Returns:
        Device ID of the started emulator
    """

    logger.info(f"Restarting emulator with AVD: {avd_name}")

    try:
        # Set environment variable for the script
        env = os.environ.copy()
        env["AVD_NAME"] = avd_name

        # Call the existing emulator management script
        script_path = "/app/docker/start_emulator.sh"
        logger.info(f"Calling {script_path} with AVD_NAME={avd_name}")

        result = subprocess.run(
            ["/bin/bash", script_path],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=600,
        )

        if result.returncode != 0:
            logger.error(f"Emulator script failed with code {result.returncode}")
            raise RuntimeError(f"Failed to start emulator (exit code: {result.returncode})")

        logger.info("Emulator script completed successfully")

        # Get the device ID of the running emulator
        device_result = subprocess.run(
            ["adb", "devices"], capture_output=True, text=True, check=True
        )

        device_id = None
        for line in device_result.stdout.split("\n")[1:]:
            if line.strip() and "device" in line:
                dev_id = line.split()[0]
                if dev_id.startswith("emulator-"):
                    device_id = dev_id
                    break

        if not device_id:
            raise RuntimeError("No emulator device found after script execution")

        logger.info(f"Emulator started successfully: {device_id}")
        return device_id

    except Exception as e:
        logger.error(f"Failed to restart emulator: {e}")
        raise


__all__ = [
    "run_command",
    "docker_ps",
    "list_containers_by_image_substring",
    "docker_inspect",
    "docker_rm",
    "build_run_command",
    "docker_exec_bash",
    "docker_exec_replace",
    "discover_backends",
    "restart_emulator_with_avd",
]

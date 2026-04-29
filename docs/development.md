# Development Guide

This guide covers development workflows for MobileWorld, including debugging and testing within Docker containers.

## Dev Mode

Dev mode allows you to develop and debug code within a container environment while using your local source files.

### Launching Containers in Dev Mode

Use the `--dev` flag when launching containers to mount your local `src` directory:

```bash
mobile-world env run --dev
```

This will:
- Mount your local `src/` directory to `/app/service/src` in the container (Otherwise you can use `--mount-src` without `dev` mode)
- Allow you to edit code locally and have changes reflected immediately in the container
- Enable live development without rebuilding the Docker image
- Automatically enable VNC for visual debugging (accessible via VNC port)

**Note:** Dev mode only supports launching a single container. If you need multiple containers, launch them separately without dev mode.

### Restarting the Server

When you make code changes in dev mode, you need to restart the server for changes to take effect:

```bash
mobile-world env restart <container_name>
```

**Example:**
```bash
mobile-world env restart knowu_bench_env_0
```

This command:
1. Finds the server process (launched via `uv run mobile-world server`)
2. Kills the existing server process
3. Restarts the server with the updated code

### Attaching to Container

To open a bash shell inside a running container:

```bash
mobile-world env exec <container_name>
```

**Example:**
```bash
mobile-world env exec knowu_bench_env_0
```

You can also run custom commands:
```bash
mobile-world env exec <container_name> --command "ls -la /app/service"
```

## Development Workflow

### Typical Development Cycle

1. **Launch container in dev mode:**
   ```bash
   _dev_env
   ```

2. **Edit code locally** in your IDE/editor

3. **Restart the server** to apply changes:
   ```bash
   mobile-world env restart my_dev_env_0
   ```

4. **Test your changes** by making API calls or running tasks

5. **Attach to container** for debugging if needed:
   ```bash
   mobile-world env exec my_dev_env_0
   ```

6. **Inside the container**, you can:
   - Check logs: `tail -f /app/service/logs/server.log`, `tail -f /app/service/logs/server.log`, `tail -f /app/service/logs/server.log`
   - Inspect processes: `ps aux | grep mobile-world`
   - Debug with Python REPL: `uv run python`
   - Run tests: `cd /app/service && uv run pytest`

### Listing Active Containers

```bash
# List running containers
mobile-world env list

# List all containers (including stopped)
mobile-world env list --all

# Get JSON output
mobile-world env list --json
```

### Container Information

Get detailed information about a specific container:

```bash
mobile-world env info <container_name>
```

### Cleaning Up

Remove containers when done:

```bash
# Remove specific containers
mobile-world env rm my_dev_env_0 my_dev_env_1

# Remove all knowu_bench containers
mobile-world env rm --all
```

## Server Architecture

The MobileWorld server is launched in the container via the entrypoint script:

```bash
uv run mobile-world server --port 6800 &
```

Key endpoints:
- **Backend API**: `http://localhost:6800`
- **Device Viewer**: `http://localhost:7860`
- **VNC**: `http://localhost:5800` (when `ENABLE_VNC=true`)

The server provides:
- FastAPI backend for device control
- Health check endpoint at `/health`
- WebSocket support for real-time updates

## Port Allocation

Containers use three ports per instance:
- **Backend port**: Base port (e.g., 6800)
- **Viewer port**: Base + 1060 (e.g., 7860)
- **VNC port**: Base - 1000 (e.g., 5800)

When launching multiple containers, they are spaced 100 ports apart:
- Container 0: 6800, 7860, 5800
- Container 1: 6900, 7960, 5900
- Container 2: 7000, 8060, 6000

## Troubleshooting

### Changes Not Reflected

If code changes aren't appearing:
1. Verify dev mode is enabled: `mobile-world env info <container_name>`
2. Check volume mounts are correct
3. Restart the server: `mobile-world env restart <container_name>`
4. Check for Python module caching issues

### Container Won't Start

1. Check if ports are available
2. Verify Docker daemon is running: `docker ps`
3. Check logs: `docker logs <container_name>`
4. Ensure Docker image exists: `docker images | grep knowu-bench`

### Permission Errors

If you get Docker permission errors:
```bash
# Add your user to docker group
sudo usermod -aG docker $USER
newgrp docker
```

### Server Not Responding

1. Check if server is running: `mobile-world env exec <container_name> --command "ps aux | grep mobile-world"`
2. Check health endpoint: `curl http://localhost:6800/health`
3. Restart the server: `mobile-world env restart <container_name>`
4. Check container logs: `docker logs <container_name>`

## Advanced Usage

### Enable VNC Without Dev Modemobile-world env run --dev --name-prefix my

You can enable VNC support on regular (non-dev) containers:
```bash
mobile-world env run --vnc --count 2
```

**Note:** VNC is automatically enabled when using `--dev` mode.

### Custom Image

Use a different Docker image:
```bash
mobile-world env run --dev --image my_custom_image:latest
```

### Custom Port Range

Specify a different starting port:
```bash
mobile-world env run --dev --start-port 8000
```

### Custom Name Prefix

Use a custom prefix for container names:
```bash
mobile-world env run --dev --name-prefix experiment_
```

This creates containers named: `experiment_0`, `experiment_1`, etc.


### Run Task Manually

Start and attach the containers in `dev` mode and execute the below command:

```
uv run python src/knowu_bench/tasks/test_task.py --task xxx --question "xxxx"
```

The `--task` flag specifies the task name, while `--question` is an optional argument that provides a clarification question for agent-user interaction tasks.  
This command initializes the task environment, after which you can interact with the GUI via VNC to complete the task manually.

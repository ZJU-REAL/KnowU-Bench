"""Public APIs for MobileWorld core functionality.

This module exposes programmatic APIs for:
- Task, agent, app, and MCP tool information retrieval
- Docker container (environment) management
- Server management

Example usage:

    # Get task information
    from mobile_world.core.api import list_tasks, get_task_info

    tasks = list_tasks(suite_family="mobile_world")
    task = get_task_info("MyTask")

    # Manage containers
    from mobile_world.core.api import launch_containers, list_containers

    results = launch_containers(count=2)
    containers = list_containers()

    # Start server programmatically
    from mobile_world.core.api import start_server
    import asyncio

    asyncio.run(start_server(host="0.0.0.0", port=6800))
"""

# Info APIs
# Environment (Docker) APIs
from mobile_world.core.api.env import (
    DEFAULT_IMAGE,
    DEFAULT_NAME_PREFIX,
    ContainerConfig,
    ContainerInfo,
    LaunchResult,
    build_container_config,
    find_available_ports,
    find_next_container_index,
    get_container_info,
    is_port_available,
    launch_container,
    launch_containers,
    list_containers,
    remove_container,
    remove_containers,
    resolve_container_name,
    restart_server_in_container,
    wait_for_container_ready,
)
from mobile_world.core.api.info import (
    AgentInfo,
    AppInfo,
    MCPToolInfo,
    TaskInfo,
    TaskStatistics,
    get_agent_info,
    get_app_info,
    get_mcp_tool_info,
    get_task_info,
    get_task_registry,
    get_task_statistics,
    list_agents,
    list_apps,
    list_mcp_tools,
    list_tasks,
)

# Server APIs
from mobile_world.core.api.server import (
    create_server_config,
    get_server_app,
    start_server,
)

__all__ = [
    # Info - Data classes
    "TaskInfo",
    "AgentInfo",
    "AppInfo",
    "MCPToolInfo",
    "TaskStatistics",
    # Info - Functions
    "get_task_registry",
    "get_task_info",
    "list_tasks",
    "get_task_statistics",
    "list_agents",
    "get_agent_info",
    "list_apps",
    "get_app_info",
    "list_mcp_tools",
    "get_mcp_tool_info",
    # Env - Constants
    "DEFAULT_IMAGE",
    "DEFAULT_NAME_PREFIX",
    # Env - Data classes
    "ContainerInfo",
    "ContainerConfig",
    "LaunchResult",
    # Env - Functions
    "is_port_available",
    "find_available_ports",
    "find_next_container_index",
    "wait_for_container_ready",
    "build_container_config",
    "launch_container",
    "launch_containers",
    "list_containers",
    "get_container_info",
    "remove_container",
    "remove_containers",
    "restart_server_in_container",
    "resolve_container_name",
    # Server - Functions
    "start_server",
    "create_server_config",
    "get_server_app",
]

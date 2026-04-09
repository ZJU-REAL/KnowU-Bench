"""MobileWorld core module.

This module exposes the public APIs for programmatic use.

Example:
    # Get task information
    from mobile_world.core import list_tasks, get_task_info

    tasks = list_tasks()
    task = get_task_info("MyTask")

    # Manage containers
    from mobile_world.core import launch_containers, list_containers

    results = launch_containers(count=2)
    containers = list_containers()
"""

# Re-export public APIs from the api submodule
from mobile_world.core.api import (
    # Info APIs
    AgentInfo,
    AppInfo,
    # Env APIs
    ContainerConfig,
    ContainerInfo,
    LaunchResult,
    MCPToolInfo,
    TaskInfo,
    TaskStatistics,
    build_container_config,
    # Server APIs
    create_server_config,
    find_available_ports,
    find_next_container_index,
    get_agent_info,
    get_app_info,
    get_container_info,
    get_mcp_tool_info,
    get_server_app,
    get_task_info,
    get_task_registry,
    get_task_statistics,
    is_port_available,
    launch_container,
    launch_containers,
    list_agents,
    list_apps,
    list_containers,
    list_mcp_tools,
    list_tasks,
    remove_container,
    remove_containers,
    resolve_container_name,
    restart_server_in_container,
    start_server,
    wait_for_container_ready,
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

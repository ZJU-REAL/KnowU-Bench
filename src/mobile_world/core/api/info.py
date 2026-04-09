"""Information retrieval APIs for MobileWorld.

This module provides programmatic access to task, agent, app, and MCP tool information.
"""

from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from mobile_world.agents.registry import AGENT_CONFIGS
from mobile_world.runtime.mcp_server import init_mcp_clients
from mobile_world.tasks.registry import TaskRegistry


@dataclass
class TaskInfo:
    """Information about a task."""

    name: str
    goal: str | None = None
    tags: list[str] = field(default_factory=list)
    app_names: list[str] = field(default_factory=list)

    @property
    def is_cross_app(self) -> bool:
        """Check if this is a cross-app task."""
        return len(self.app_names) > 1

    @property
    def is_single_app(self) -> bool:
        """Check if this is a single-app task."""
        return len(self.app_names) == 1


@dataclass
class AgentInfo:
    """Information about an agent."""

    agent_type: str
    class_name: str
    needs_api_key: bool = False


@dataclass
class AppInfo:
    """Information about an app and its associated tasks."""

    name: str
    tasks: list[str] = field(default_factory=list)
    single_app_task_count: int = 0
    cross_app_task_count: int = 0


@dataclass
class MCPToolInfo:
    """Information about an MCP tool."""

    name: str
    description: str | None = None
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskStatistics:
    """Statistics about tasks."""

    total_tasks: int = 0
    single_app_tasks: int = 0
    cross_app_tasks: int = 0
    tasks_without_apps: int = 0
    tag_counts: dict[str, int] = field(default_factory=dict)


def get_task_registry(suite_family: str = "mobile_world"):
    """Get the appropriate task registry based on suite_family.

    Args:
        suite_family: "mobile_world"

    Returns:
        Task registry instance
    """
    return TaskRegistry()


def get_task_info(
    task_name: str,
    suite_family: str = "mobile_world",
    task_registry=None,
) -> TaskInfo:
    """Get detailed information about a specific task.

    Args:
        task_name: Name of the task
        suite_family: Suite family to use
        task_registry: Optional pre-initialized task registry

    Returns:
        TaskInfo object with task details

    Raises:
        KeyError: If task not found
    """
    if task_registry is None:
        task_registry = get_task_registry(suite_family)

    task = task_registry.get_task(task_name)

    return TaskInfo(
        name=task.name,
        goal=task.goal if task.goal else None,
        tags=sorted(task.task_tags) if hasattr(task, "task_tags") and task.task_tags else [],
        app_names=list(task.app_names) if hasattr(task, "app_names") and task.app_names else [],
    )


def list_tasks(
    suite_family: str = "mobile_world",
    name_filter: str | None = None,
    task_registry=None,
) -> list[TaskInfo]:
    """List all tasks with optional filtering.

    Args:
        suite_family: Suite family to use
        name_filter: Filter tasks by name (case-insensitive substring match)
        task_registry: Optional pre-initialized task registry

    Returns:
        List of TaskInfo objects
    """
    if task_registry is None:
        task_registry = get_task_registry(suite_family)

    all_task_names = task_registry.list_tasks()

    if name_filter:
        filter_lower = name_filter.lower()
        task_names = [t for t in all_task_names if filter_lower in t.lower()]
    else:
        task_names = all_task_names

    tasks = []
    for task_name in task_names:
        try:
            task_info = get_task_info(task_name, task_registry=task_registry)
            tasks.append(task_info)
        except Exception as e:
            logger.warning(f"Error getting info for task {task_name}: {e}")
            tasks.append(TaskInfo(name=task_name))

    # Sort by first app name, then by task name
    tasks.sort(key=lambda t: (list(t.app_names)[0].lower() if t.app_names else "", t.name.lower()))

    return tasks


def get_task_statistics(
    suite_family: str = "mobile_world",
    name_filter: str | None = None,
    task_registry=None,
) -> TaskStatistics:
    """Get statistics about tasks.

    Args:
        suite_family: Suite family to use
        name_filter: Filter tasks by name (case-insensitive substring match)
        task_registry: Optional pre-initialized task registry

    Returns:
        TaskStatistics object
    """
    tasks = list_tasks(
        suite_family=suite_family, name_filter=name_filter, task_registry=task_registry
    )

    stats = TaskStatistics(total_tasks=len(tasks))
    tag_counts: dict[str, int] = {}

    for task in tasks:
        if task.is_single_app:
            stats.single_app_tasks += 1
        elif task.is_cross_app:
            stats.cross_app_tasks += 1
        else:
            stats.tasks_without_apps += 1

        for tag in task.tags:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1

    stats.tag_counts = tag_counts
    return stats


def list_agents(name_filter: str | None = None) -> list[AgentInfo]:
    """List all available agents.

    Args:
        name_filter: Filter agents by type (case-insensitive substring match)

    Returns:
        List of AgentInfo objects
    """
    if name_filter:
        filter_lower = name_filter.lower()
        agent_types = [k for k in AGENT_CONFIGS.keys() if filter_lower in k.lower()]
    else:
        agent_types = list(AGENT_CONFIGS.keys())

    agents = []
    for agent_type in sorted(agent_types):
        config = AGENT_CONFIGS[agent_type]
        agents.append(
            AgentInfo(
                agent_type=agent_type,
                class_name=config["class"].__name__,
                needs_api_key=config.get("needs_api_key", False),
            )
        )

    return agents


def get_agent_info(agent_type: str) -> AgentInfo:
    """Get information about a specific agent.

    Args:
        agent_type: Type of the agent

    Returns:
        AgentInfo object

    Raises:
        KeyError: If agent type not found
    """
    if agent_type not in AGENT_CONFIGS:
        raise KeyError(f"Agent type '{agent_type}' not found")

    config = AGENT_CONFIGS[agent_type]
    return AgentInfo(
        agent_type=agent_type,
        class_name=config["class"].__name__,
        needs_api_key=config.get("needs_api_key", False),
    )


def list_apps(
    suite_family: str = "mobile_world",
    name_filter: str | None = None,
    task_registry=None,
) -> list[AppInfo]:
    """List all apps with their task counts.

    Args:
        suite_family: Suite family to use
        name_filter: Filter apps by name (case-insensitive substring match)
        task_registry: Optional pre-initialized task registry

    Returns:
        List of AppInfo objects
    """
    if task_registry is None:
        task_registry = get_task_registry(suite_family)

    # Collect all apps and their tasks
    app_to_tasks: dict[str, list[str]] = {}
    all_tasks = task_registry.list_tasks()

    for task_name in all_tasks:
        task = task_registry.get_task(task_name)
        if hasattr(task, "app_names") and task.app_names:
            for app in task.app_names:
                if app not in app_to_tasks:
                    app_to_tasks[app] = []
                app_to_tasks[app].append(task_name)

    # Apply filter
    app_names = list(app_to_tasks.keys())
    if name_filter:
        filter_lower = name_filter.lower()
        app_names = [a for a in app_names if filter_lower in a.lower()]

    apps = []
    for app_name in sorted(app_names):
        task_names = app_to_tasks[app_name]
        single_app_count = 0
        cross_app_count = 0

        for task_name in task_names:
            task = task_registry.get_task(task_name)
            if hasattr(task, "app_names") and task.app_names:
                if len(task.app_names) == 1:
                    single_app_count += 1
                else:
                    cross_app_count += 1

        apps.append(
            AppInfo(
                name=app_name,
                tasks=task_names,
                single_app_task_count=single_app_count,
                cross_app_task_count=cross_app_count,
            )
        )

    return apps


def get_app_info(
    app_name: str,
    suite_family: str = "mobile_world",
    task_registry=None,
) -> AppInfo:
    """Get information about a specific app.

    Args:
        app_name: Name of the app
        suite_family: Suite family to use
        task_registry: Optional pre-initialized task registry

    Returns:
        AppInfo object

    Raises:
        KeyError: If app not found
    """
    apps = list_apps(suite_family=suite_family, task_registry=task_registry)
    for app in apps:
        if app.name == app_name:
            return app
    raise KeyError(f"App '{app_name}' not found")


async def list_mcp_tools(name_filter: str | None = None) -> list[MCPToolInfo]:
    """List all available MCP tools.

    Args:
        name_filter: Filter tools by name (case-insensitive substring match)

    Returns:
        List of MCPToolInfo objects
    """
    all_tools = []

    mcp_client = init_mcp_clients()

    try:
        tools = await mcp_client.list_tools()
        for tool_dict in tools:
            tool_info = MCPToolInfo(
                name=tool_dict.get("name", "Unknown"),
                description=tool_dict.get("description") or None,
                parameters=tool_dict.get("inputSchema", {}),
            )
            all_tools.append(tool_info)
    except Exception as e:
        logger.warning(f"Failed to list tools from MCP client: {e}")

    if name_filter:
        filter_lower = name_filter.lower()
        all_tools = [t for t in all_tools if filter_lower in t.name.lower()]

    return sorted(all_tools, key=lambda t: t.name)


async def get_mcp_tool_info(tool_name: str) -> MCPToolInfo:
    """Get information about a specific MCP tool.

    Args:
        tool_name: Name of the MCP tool

    Returns:
        MCPToolInfo object

    Raises:
        KeyError: If tool not found
    """
    tools = await list_mcp_tools()
    for tool in tools:
        if tool.name == tool_name:
            return tool
    raise KeyError(f"MCP tool '{tool_name}' not found")

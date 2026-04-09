"""Info subcommand for MobileWorld CLI."""

import argparse
from pathlib import Path

import pandas as pd
from loguru import logger
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from mobile_world.core.api.info import (
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


def configure_parser(subparsers: argparse._SubParsersAction) -> None:
    """Configure the info subcommand parser with subcommands."""
    info_parser = subparsers.add_parser(
        "info",
        help="Display information about available tasks and agents",
    )

    # Create subparsers for info subcommands
    info_subparsers = info_parser.add_subparsers(dest="info_command", help="Info commands")

    # Task subcommand
    task_parser = info_subparsers.add_parser("task", help="Display task information")
    task_parser.add_argument(
        "--name",
        type=str,
        default=None,
        help="Show detailed information about a specific task",
    )
    task_parser.add_argument(
        "--filter",
        type=str,
        default=None,
        help="Filter tasks by name (case-insensitive substring match)",
    )
    task_parser.add_argument(
        "--suite-family",
        "--suite_family",
        dest="suite_family",
        choices=["mobile_world"],
        default="mobile_world",
        help="Suite family to show tasks from (default: mobile_world)",
    )
    task_parser.add_argument(
        "--export-excel",
        "--export_excel",
        dest="export_excel",
        type=str,
        default=None,
        help="Export task information to Excel file (specify output file path)",
    )
    task_parser.add_argument(
        "--no-pager",
        dest="no_pager",
        action="store_true",
        help="Disable system pager for output",
    )

    # Agent subcommand
    agent_parser = info_subparsers.add_parser("agent", help="Display agent information")
    agent_parser.add_argument(
        "--filter",
        type=str,
        default=None,
        help="Filter agents by type (case-insensitive substring match)",
    )

    # App subcommand
    app_parser = info_subparsers.add_parser("app", help="Display app information")
    app_parser.add_argument(
        "--name",
        type=str,
        default=None,
        help="Show detailed information about a specific app",
    )
    app_parser.add_argument(
        "--filter",
        type=str,
        default=None,
        help="Filter apps by name (case-insensitive substring match)",
    )
    app_parser.add_argument(
        "--suite-family",
        "--suite_family",
        dest="suite_family",
        choices=["mobile_world"],
        default="mobile_world",
        help="Suite family to show apps from (default: mobile_world)",
    )

    # MCP subcommand
    mcp_parser = info_subparsers.add_parser("mcp", help="Display MCP tools information")
    mcp_parser.add_argument(
        "--name",
        type=str,
        default=None,
        help="Show detailed information about a specific MCP tool",
    )
    mcp_parser.add_argument(
        "--filter",
        type=str,
        default=None,
        help="Filter MCP tools by name or tag (case-insensitive substring match)",
    )


def export_tasks_to_excel(
    suite_family: str,
    output_path: str,
    name_filter: str | None = None,
) -> None:
    """Export task information to Excel file.

    Args:
        suite_family: Suite family to use
        output_path: Path to output Excel file
        name_filter: Filter tasks by name substring
    """
    tasks = list_tasks(suite_family=suite_family, name_filter=name_filter)

    if not tasks:
        raise ValueError("No tasks found to export")

    # Collect task data
    task_data = []
    for task in tasks:
        first_app = list(task.app_names)[0] if task.app_names else ""
        task_type = (
            "Cross-app" if task.is_cross_app else "Single-app" if task.is_single_app else "No app"
        )

        task_data.append(
            {
                "Task Name": task.name,
                "Goal": task.goal or "N/A",
                "Tags": ", ".join(task.tags) if task.tags else "-",
                "Apps": ", ".join(task.app_names) if task.app_names else "-",
                "First App": first_app,
                "Number of Apps": len(task.app_names),
                "Task Type": task_type,
            }
        )

    # Create DataFrame
    df = pd.DataFrame(task_data)
    df = df.sort_values(by=["First App", "Task Name"])
    df_output = df.drop(columns=["First App"])

    # Ensure output directory exists
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Export to Excel
    with pd.ExcelWriter(output_file, engine="openpyxl") as writer:
        df_output.to_excel(writer, sheet_name="Tasks", index=False)

        # Statistics sheet
        stats = get_task_statistics(suite_family=suite_family, name_filter=name_filter)
        stats_data = {
            "Metric": [
                "Total Tasks",
                "Single-app Tasks",
                "Cross-app Tasks",
                "Tasks without Apps",
            ],
            "Count": [
                stats.total_tasks,
                stats.single_app_tasks,
                stats.cross_app_tasks,
                stats.tasks_without_apps,
            ],
        }
        stats_df = pd.DataFrame(stats_data)
        stats_df.to_excel(writer, sheet_name="Statistics", index=False)

        # Tag statistics sheet
        if stats.tag_counts:
            tag_stats = pd.DataFrame(
                [
                    {"Tag": tag, "Count": count}
                    for tag, count in sorted(stats.tag_counts.items(), key=lambda x: (-x[1], x[0]))
                ]
            )
            tag_stats.to_excel(writer, sheet_name="Tag Statistics", index=False)

        # Auto-adjust column widths
        for sheet_name in writer.sheets:
            worksheet = writer.sheets[sheet_name]
            for column in worksheet.columns:
                max_length = 0
                column_letter = column[0].column_letter
                for cell in column:
                    try:
                        if cell.value:
                            max_length = max(max_length, len(str(cell.value)))
                    except Exception:
                        pass
                adjusted_width = min(max_length + 2, 100)
                worksheet.column_dimensions[column_letter].width = adjusted_width

    logger.info(f"Exported {len(tasks)} tasks to {output_file}")


def display_tasks_info(
    console: Console,
    suite_family: str,
    task_name: str | None = None,
    name_filter: str | None = None,
    use_pager: bool = False,
) -> None:
    """Display information about available tasks."""
    task_registry = get_task_registry(suite_family)

    if task_name:
        try:
            task = get_task_info(task_name, suite_family=suite_family, task_registry=task_registry)

            task_info_table = Table(show_header=False, box=None, padding=(0, 2))
            task_info_table.add_column("Property", style="cyan bold")
            task_info_table.add_column("Value", style="white")

            task_info_table.add_row("Name", task.name)
            task_info_table.add_row("Goal", task.goal or "N/A")
            task_info_table.add_row("Tags", ", ".join(task.tags) if task.tags else "None")
            task_info_table.add_row("Apps", ", ".join(task.app_names) if task.app_names else "None")

            console.print(
                Panel(
                    task_info_table,
                    title=f"[bold green]Task: {task_name}[/bold green]",
                    border_style="green",
                )
            )
        except KeyError:
            console.print(f"[bold red]Error:[/bold red] Task '{task_name}' not found")
            all_tasks = list_tasks(suite_family=suite_family, task_registry=task_registry)
            console.print(f"Available tasks: {', '.join(t.name for t in all_tasks)}")
    else:
        tasks = list_tasks(
            suite_family=suite_family, name_filter=name_filter, task_registry=task_registry
        )

        if not tasks:
            if name_filter:
                console.print(f"[yellow]No tasks found matching filter '{name_filter}'[/yellow]")
            else:
                console.print("[yellow]No tasks found in registry[/yellow]")
            return

        table = Table(title="[bold cyan]Available Tasks[/bold cyan]", show_lines=True)
        table.add_column("Task Name", style="cyan", no_wrap=True)
        table.add_column("Goal", style="white", max_width=60)
        table.add_column("Tags", style="yellow")
        table.add_column("Apps", style="green")

        for task in tasks:
            table.add_row(
                task.name,
                task.goal or "N/A",
                ", ".join(task.tags) if task.tags else "-",
                ", ".join(task.app_names) if task.app_names else "-",
            )

        stats = get_task_statistics(
            suite_family=suite_family, name_filter=name_filter, task_registry=task_registry
        )
        all_tasks = list_tasks(suite_family=suite_family, task_registry=task_registry)

        def print_output() -> None:
            console.print(table)
            console.print(f"\n[bold]Total tasks:[/bold] {stats.total_tasks}")
            console.print(f"  • Single-app tasks: {stats.single_app_tasks}")
            console.print(f"  • Cross-app tasks: {stats.cross_app_tasks}")
            console.print(f"  • English tasks (lang-en): {stats.tag_counts.get('lang-en', 0)}")
            console.print(f"  • Chinese tasks (lang-cn): {stats.tag_counts.get('lang-cn', 0)}")

            if stats.tag_counts:
                console.print("\n[bold]Tasks by tag:[/bold]")
                for tag, count in sorted(stats.tag_counts.items(), key=lambda x: (-x[1], x[0])):
                    console.print(f"  • {tag}: {count}")

            if name_filter:
                console.print(
                    f"\n[dim]Filtered by: '{name_filter}' ({len(tasks)}/{len(all_tasks)})[/dim]"
                )
            console.print("[dim]Use 'info task --name <name>' to see detailed information[/dim]")

        if use_pager:
            with console.pager(styles=True):
                print_output()
        else:
            print_output()


def display_agents_info(console: Console, name_filter: str | None = None) -> None:
    """Display information about available agents."""
    agents = list_agents(name_filter=name_filter)

    if not agents:
        if name_filter:
            console.print(f"[yellow]No agents found matching filter '{name_filter}'[/yellow]")
        else:
            console.print("[yellow]No agents found in registry[/yellow]")
        return

    table = Table(title="[bold cyan]Available Agents[/bold cyan]", show_lines=True)
    table.add_column("Agent Type", style="cyan", no_wrap=True)
    table.add_column("Class Name", style="white")
    table.add_column("API Key Required", style="yellow", justify="center")

    for agent in agents:
        needs_api_key = "✓" if agent.needs_api_key else "✗"
        table.add_row(agent.agent_type, agent.class_name, needs_api_key)

    console.print(table)
    console.print(f"\n[bold]Total agents:[/bold] {len(agents)}")

    all_agents = list_agents()
    if name_filter:
        console.print(f"[dim]Filtered by: '{name_filter}' ({len(agents)}/{len(all_agents)})[/dim]")

    usage_panel = Panel(
        "[bold]Usage:[/bold]\n"
        "• Use agent type with --agent flag in run command\n"
        "• Agents marked with ✓ require API key via --api-key flag\n"
        "• You can also load custom agents from Python files",
        title="[bold green]Agent Usage[/bold green]",
        border_style="green",
    )
    console.print("\n", usage_panel)


async def display_mcp_info(
    console: Console,
    tool_name: str | None = None,
    name_filter: str | None = None,
) -> None:
    """Display information about available MCP tools."""
    with console.status("[bold cyan]Loading MCP tools...", spinner="dots"):
        if tool_name:
            try:
                tool = await get_mcp_tool_info(tool_name)

                tool_info_table = Table(show_header=False, box=None, padding=(0, 2))
                tool_info_table.add_column("Property", style="cyan bold")
                tool_info_table.add_column("Value", style="white")

                tool_info_table.add_row("Name", tool.name)
                tool_info_table.add_row("Description", tool.description or "N/A")

                if tool.parameters and "properties" in tool.parameters:
                    params = tool.parameters["properties"]
                    required = tool.parameters.get("required", [])

                    param_lines = []
                    for param_name, param_info in params.items():
                        param_type = param_info.get("type", "unknown")
                        param_desc = param_info.get("description", "")
                        is_required = " (required)" if param_name in required else " (optional)"
                        param_lines.append(f"  • {param_name}: {param_type}{is_required}")
                        if param_desc:
                            param_lines.append(f"    {param_desc}")

                    tool_info_table.add_row(
                        "Parameters", "\n".join(param_lines) if param_lines else "None"
                    )
                else:
                    tool_info_table.add_row("Parameters", "None")

                console.print(
                    Panel(
                        tool_info_table,
                        title=f"[bold green]MCP Tool: {tool_name}[/bold green]",
                        border_style="green",
                    )
                )
            except KeyError:
                tools = await list_mcp_tools()
                console.print(f"[bold red]Error:[/bold red] MCP tool '{tool_name}' not found")
                console.print(f"Available tools: {', '.join(t.name for t in tools)}")
        else:
            tools = await list_mcp_tools(name_filter=name_filter)

            if not tools:
                if name_filter:
                    console.print(
                        f"[yellow]No MCP tools found matching filter '{name_filter}'[/yellow]"
                    )
                else:
                    console.print("[yellow]No MCP tools found[/yellow]")
                return

            table = Table(title="[bold cyan]Available MCP Tools[/bold cyan]", show_lines=True)
            table.add_column("Tool Name", style="cyan", no_wrap=True)
            table.add_column("Description", style="white", max_width=50)
            table.add_column("Parameters", style="green", max_width=40)

            for tool in tools:
                param_list = []
                if tool.parameters and "properties" in tool.parameters:
                    params = tool.parameters["properties"]
                    required = tool.parameters.get("required", [])
                    for param_name, param_info in params.items():
                        param_type = param_info.get("type", "unknown")
                        is_required = "*" if param_name in required else ""
                        param_list.append(f"{param_name}: {param_type}{is_required}")

                params_str = ", ".join(param_list) if param_list else "None"
                table.add_row(tool.name, tool.description or "N/A", params_str)

            console.print(table)
            console.print(f"\n[bold]Total MCP tools:[/bold] {len(tools)}")

            all_tools = await list_mcp_tools()
            if name_filter:
                console.print(
                    f"\n[dim]Filtered by: '{name_filter}' ({len(tools)}/{len(all_tools)})[/dim]"
                )
            console.print("[dim]Use 'info mcp --name <name>' to see detailed information[/dim]")


def display_apps_info(
    console: Console,
    suite_family: str,
    app_name: str | None = None,
    name_filter: str | None = None,
) -> None:
    """Display information about available apps."""
    task_registry = get_task_registry(suite_family)

    if app_name:
        try:
            app = get_app_info(app_name, suite_family=suite_family, task_registry=task_registry)

            app_info_table = Table(show_header=False, box=None, padding=(0, 2))
            app_info_table.add_column("Property", style="cyan bold")
            app_info_table.add_column("Value", style="white")

            app_info_table.add_row("App Name", app.name)
            app_info_table.add_row("Total Tasks", str(len(app.tasks)))
            app_info_table.add_row("Single-app tasks", str(app.single_app_task_count))
            app_info_table.add_row("Cross-app tasks", str(app.cross_app_task_count))

            console.print(
                Panel(
                    app_info_table,
                    title=f"[bold green]App: {app_name}[/bold green]",
                    border_style="green",
                )
            )

            if app.tasks:
                task_list = Table(
                    title=f"[bold cyan]Tasks for {app_name}[/bold cyan]", show_lines=True
                )
                task_list.add_column("Task Name", style="cyan", no_wrap=True)
                task_list.add_column("Goal", style="white", max_width=60)
                task_list.add_column("All Apps", style="yellow")

                for task_name in sorted(app.tasks):
                    task = get_task_info(task_name, task_registry=task_registry)
                    task_list.add_row(
                        task_name,
                        task.goal or "N/A",
                        ", ".join(task.app_names) if task.app_names else "-",
                    )

                console.print("\n")
                console.print(task_list)
        except KeyError:
            apps = list_apps(suite_family=suite_family, task_registry=task_registry)
            console.print(f"[bold red]Error:[/bold red] App '{app_name}' not found")
            console.print(f"Available apps: {', '.join(a.name for a in apps)}")
    else:
        apps = list_apps(
            suite_family=suite_family, name_filter=name_filter, task_registry=task_registry
        )

        if not apps:
            if name_filter:
                console.print(f"[yellow]No apps found matching filter '{name_filter}'[/yellow]")
            else:
                console.print("[yellow]No apps found in registry[/yellow]")
            return

        table = Table(title="[bold cyan]Available Apps[/bold cyan]", show_lines=True)
        table.add_column("App Name", style="cyan", no_wrap=True)
        table.add_column("Total Tasks", style="white", justify="center")
        table.add_column("Single-app Tasks", style="green", justify="center")
        table.add_column("Cross-app Tasks", style="yellow", justify="center")

        for app in apps:
            table.add_row(
                app.name,
                str(len(app.tasks)),
                str(app.single_app_task_count),
                str(app.cross_app_task_count),
            )

        console.print(table)
        console.print(f"\n[bold]Total apps:[/bold] {len(apps)}")

        all_apps = list_apps(suite_family=suite_family, task_registry=task_registry)
        if name_filter:
            console.print(f"[dim]Filtered by: '{name_filter}' ({len(apps)}/{len(all_apps)})[/dim]")
        console.print("[dim]Use 'info app --name <name>' to see detailed information[/dim]")


async def execute(args: argparse.Namespace) -> None:
    """Execute the info command."""
    logger.remove()
    console = Console()

    suite_family = args.suite_family if hasattr(args, "suite_family") else "mobile_world"

    if args.info_command == "task":
        if hasattr(args, "export_excel") and args.export_excel:
            try:
                export_tasks_to_excel(
                    suite_family,
                    args.export_excel,
                    name_filter=args.filter if hasattr(args, "filter") else None,
                )
                console.print(
                    f"[bold green]✓[/bold green] Successfully exported tasks to [cyan]{args.export_excel}[/cyan]"
                )
            except Exception as e:
                console.print(f"[bold red]Error:[/bold red] Failed to export to Excel: {e}")
                logger.exception("Error exporting to Excel")
                raise
        else:
            header_text = f"MobileWorld Tasks - Suite: {suite_family}"
            header = Text(header_text, style="bold magenta")
            console.print(Panel(header, border_style="magenta"))
            console.print()

            display_tasks_info(
                console,
                suite_family,
                task_name=args.name if hasattr(args, "name") else None,
                name_filter=args.filter if hasattr(args, "filter") else None,
                use_pager=not (args.no_pager if hasattr(args, "no_pager") else False),
            )

    elif args.info_command == "agent":
        header = Text("MobileWorld Agents", style="bold magenta")
        console.print(Panel(header, border_style="magenta"))
        console.print()

        display_agents_info(console, name_filter=args.filter if hasattr(args, "filter") else None)

    elif args.info_command == "app":
        header_text = f"MobileWorld Apps - Suite: {suite_family}"
        header = Text(header_text, style="bold magenta")
        console.print(Panel(header, border_style="magenta"))
        console.print()

        display_apps_info(
            console,
            suite_family,
            app_name=args.name if hasattr(args, "name") else None,
            name_filter=args.filter if hasattr(args, "filter") else None,
        )

    elif args.info_command == "mcp":
        header = Text("MobileWorld MCP Tools", style="bold magenta")
        console.print(Panel(header, border_style="magenta"))
        console.print()

        await display_mcp_info(
            console,
            tool_name=args.name if hasattr(args, "name") else None,
            name_filter=args.filter if hasattr(args, "filter") else None,
        )

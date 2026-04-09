"""Test subcommand for MobileWorld CLI - Run a single ad-hoc task for testing."""

import argparse
import os
import subprocess

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from ..user_task_runner import run_user_task
from .eval import _add_common_arguments


def configure_parser(subparsers: argparse._SubParsersAction) -> None:
    """Configure the test subcommand parser."""
    test_parser = subparsers.add_parser(
        "test",
        help="Run a single ad-hoc task for testing (no initialization/validation)",
    )

    _add_common_arguments(test_parser)

    test_parser.add_argument(
        "goal",
        type=str,
        help="The goal/task description to execute",
    )
    test_parser.add_argument(
        "--log_verbose",
        help="Whether to log verbose messages",
        action="store_true",
        default=False,
    )


async def execute(args: argparse.Namespace) -> None:
    """Execute the test command."""
    log_file_root = args.log_file_root or args.output or "./traj_logs"

    if args.device is None:
        devices = subprocess.check_output(["adb", "devices"]).decode("utf-8").splitlines()
        devices = [device.split("\t")[0] for device in devices if "\t" in device]
        if len(devices) == 0:
            raise ValueError("No Android devices found")
        if len(devices) > 1:
            raise ValueError("Multiple Android devices found, please specify the device ID")
        args.device = devices[0]

    console = Console()
    # Parse single aw_host URL for test task
    aw_url = args.aw_host.split(",")[0] if args.aw_host else None

    result = run_user_task(
        goal=args.goal,
        agent_type=args.agent_type,
        model_name=args.model_name,
        llm_base_url=args.llm_base_url,
        log_file_root=log_file_root,
        max_step=args.max_round or -1,
        aw_url=aw_url,
        api_key=args.api_key or os.getenv("API_KEY"),
        device=args.device or "emulator-5554",
        step_wait_time=args.step_wait_time or 1.0,
        suite_family=args.suite_family or "mobile_world",
        env_name_prefix=args.env_name_prefix,
        env_image=args.env_image,
        enable_mcp=args.enable_mcp,
        executor_llm_base_url=args.executor_llm_base_url,
        executor_model_name=args.executor_model_name,
        executor_agent_class=args.executor_agent_class,
        log_verbose=args.log_verbose,
    )

    if result.get("success"):
        summary_text = Text()
        summary_text.append("Test Task Completed!\n\n", style="bold green")
        summary_text.append(f"Goal: {result['goal']}\n", style="cyan")
        summary_text.append(f"Steps: {result['steps']}\n", style="magenta")

        panel = Panel(
            summary_text,
            title="[bold blue]📱 Test Task Result",
            border_style="blue",
            padding=(1, 2),
        )
        console.print(panel)
    else:
        error_text = Text()
        error_text.append("Test Task Failed!\n\n", style="bold red")
        error_text.append(f"Goal: {result.get('goal', 'N/A')}\n", style="cyan")
        error_text.append(f"Error: {result.get('error', 'Unknown error')}\n", style="red")

        panel = Panel(
            error_text,
            title="[bold red]❌ Test Task Error",
            border_style="red",
            padding=(1, 2),
        )
        console.print(panel)

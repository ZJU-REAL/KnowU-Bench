"""
Command-line interface for MobileWorld framework.
"""

import argparse
import asyncio
import sys

from . import subcommands


def create_parser() -> argparse.ArgumentParser:
    """Create command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog="mobile-world",
        description="Mobile GUI automation and testing framework",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Configure all subcommand parsers
    subcommands.configure_server_parser(subparsers)
    subcommands.configure_eval_parser(subparsers)  # Also registers 'run' as an alias
    subcommands.configure_test_parser(subparsers)
    subcommands.configure_device_parser(subparsers)  # Also registers 'viewer' as an alias
    subcommands.configure_logs_parser(subparsers)
    subcommands.configure_env_parser(subparsers)
    subcommands.configure_info_parser(subparsers)

    return parser


async def async_main() -> None:
    """Main CLI entry point."""
    parser = create_parser()
    args = parser.parse_args()

    if args.command == "server":
        await subcommands.execute_server(args)
    elif args.command in ("eval", "run"):
        await subcommands.execute_eval(args)
    elif args.command == "test":
        await subcommands.execute_test(args)
    elif args.command in ("device", "viewer"):
        await subcommands.execute_device(args)
    elif args.command == "logs":
        await subcommands.execute_logs(args)
    elif args.command == "env":
        await subcommands.execute_env(args)
    elif args.command == "info":
        await subcommands.execute_info(args)
    else:
        parser.print_help()
        sys.exit(1)


def main():
    asyncio.run(async_main())

"""Server subcommand for MobileWorld CLI."""

import argparse

from mobile_world.core.api.server import start_server


def configure_parser(subparsers: argparse._SubParsersAction) -> None:
    """Configure the server subcommand parser."""
    server_parser = subparsers.add_parser("server", help="Start the server")
    server_parser.add_argument("--host", default="0.0.0.0", help="Server host")
    server_parser.add_argument("--port", type=int, default=6800, help="Server port")
    server_parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    server_parser.add_argument(
        "--suite-family",
        "--suite_family",
        dest="suite_family",
        choices=["mobile_world"],
        default="mobile_world",
        help="Initial task suite family to use (default: mobile_world). Can be changed dynamically via /suite_family/switch endpoint.",
    )
    server_parser.add_argument(
        "--enable-mcp",
        action="store_true",
        help="Enable MCP server with SSE transport at /mcp/sse endpoint",
    )


async def execute(args: argparse.Namespace) -> None:
    """Execute the server command."""
    await start_server(
        host=args.host,
        port=args.port,
        debug=args.debug,
        suite_family=args.suite_family,
        enable_mcp=args.enable_mcp,
    )

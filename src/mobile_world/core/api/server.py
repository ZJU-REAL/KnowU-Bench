"""Server management APIs for MobileWorld.

This module provides programmatic access to start and manage the MobileWorld server.
"""

import logging

import uvicorn
from loguru import logger

from mobile_world.core.server import app as server_app
from mobile_world.core.server import initialize_suite_family


class HealthCheckFilter(logging.Filter):
    """Filter to suppress /health endpoint logs."""

    def filter(self, record: logging.LogRecord) -> bool:
        return record.getMessage().find("/health") == -1


async def start_server(
    host: str = "0.0.0.0",
    port: int = 6800,
    debug: bool = False,
    suite_family: str = "mobile_world",
    enable_mcp: bool = False,
    suppress_health_logs: bool = True,
) -> None:
    """Start the MobileWorld server.

    Args:
        host: Server host address
        port: Server port number
        debug: Enable debug mode
        suite_family: Initial suite family to use
        enable_mcp: Enable MCP server (currently disabled in implementation)
        suppress_health_logs: Suppress /health endpoint logs
    """
    initialize_suite_family(suite_family)

    if suppress_health_logs:
        logging.getLogger("uvicorn.access").addFilter(HealthCheckFilter())

    config = uvicorn.Config(
        server_app,
        host=host,
        port=port,
        log_level="debug" if debug else "info",
    )
    server = uvicorn.Server(config)

    logger.info(f"Starting server on {host}:{port} with suite_family={suite_family}")
    if enable_mcp:
        logger.info(f"MCP server available at http://{host}:{port}/mcp-server/mcp")

    await server.serve()


def create_server_config(
    host: str = "0.0.0.0",
    port: int = 6800,
    debug: bool = False,
    suite_family: str = "mobile_world",
) -> uvicorn.Config:
    """Create a uvicorn server configuration without starting it.

    This is useful for programmatic control over the server lifecycle.

    Args:
        host: Server host address
        port: Server port number
        debug: Enable debug mode
        suite_family: Initial suite family to use

    Returns:
        uvicorn.Config object
    """
    initialize_suite_family(suite_family)

    return uvicorn.Config(
        server_app,
        host=host,
        port=port,
        log_level="debug" if debug else "info",
    )


def get_server_app():
    """Get the FastAPI application instance.

    Returns:
        FastAPI application
    """
    return server_app

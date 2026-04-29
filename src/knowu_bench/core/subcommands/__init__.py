"""Subcommands for the MobileWorld CLI."""

from .device import configure_parser as configure_device_parser
from .device import execute as execute_device
from .env import configure_parser as configure_env_parser
from .env import execute as execute_env
from .eval import configure_parser as configure_eval_parser
from .eval import execute as execute_eval
from .info import configure_parser as configure_info_parser
from .info import execute as execute_info
from .logs import configure_parser as configure_logs_parser
from .logs import execute as execute_logs
from .server import configure_parser as configure_server_parser
from .server import execute as execute_server
from .test import configure_parser as configure_test_parser
from .test import execute as execute_test

__all__ = [
    "configure_server_parser",
    "execute_server",
    "configure_eval_parser",
    "execute_eval",
    "configure_test_parser",
    "execute_test",
    "configure_device_parser",
    "execute_device",
    "configure_logs_parser",
    "execute_logs",
    "configure_env_parser",
    "execute_env",
    "configure_info_parser",
    "execute_info",
]

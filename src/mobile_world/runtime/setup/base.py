import shlex
from typing import Any
from loguru import logger
from mobile_world.runtime.controller import AndroidController
from mobile_world.runtime.utils.helpers import execute_adb

class BaseSetup:
    """Base class for all system app setup handlers"""

    def __init__(self, controller: AndroidController):
        self.controller = controller

    def setup(self, config: Any) -> bool:
        """Main entry point for setup logic, to be implemented by subclasses"""
        raise NotImplementedError

    def _trigger_media_scan(self, file_path: str):
        """
        Helper method to trigger MediaScanner for a specific file.
        """
        try:
            safe_path = shlex.quote(f"file://{file_path}")
            scan_cmd = (
                f'adb -s {self.controller.device} shell am broadcast '
                f'-a android.intent.action.MEDIA_SCANNER_SCAN_FILE '
                f'-d {safe_path}'
            )
            execute_adb(scan_cmd, output=False)
            logger.debug(f"Triggered media scan for: {file_path}")
        except Exception as e:
            logger.warning(f"Failed to trigger media scan for {file_path}: {e}")

    def _escape_arg_for_android(self, key: str, value: str) -> str:
        """
        Constructs an Android Shell safe argument string.
        """
        if value is None:
            value = ""
            
        # 1. Android Shell level escaping
        safe_val = value.replace('\\', '\\\\') \
                        .replace('"', '\\"') \
                        .replace('`', '\\`') \
                        .replace('$', '\\$')
        
        # 2. Construct Android argument: "key:type:SafeValue"
        android_arg = f'"{key}:{safe_val}"'
        
        # 3. Host Shell level escaping
        host_arg = shlex.quote(android_arg)
        
        return host_arg
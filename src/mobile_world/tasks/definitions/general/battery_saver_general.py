"""General task: enable battery saver mode when battery is low."""

import time

from loguru import logger

from mobile_world.runtime.controller import AndroidController
from mobile_world.runtime.utils.helpers import execute_adb
from mobile_world.tasks.base import BaseTask


class BatterySaverGeneralTask(BaseTask):
    """Turn on battery saver mode with explicit instruction."""

    task_tags = {"general", "easy"}
    snapshot_tag = "init_state"
    app_names = {"Settings"}

    TRIGGER_LEVEL = 15

    goal = "当前手机电池电量只剩 15%，请帮我打开省电模式（Battery Saver）。"

    def initialize_task_hook(self, controller: AndroidController) -> bool:
        execute_adb("shell settings put system time_12_24 24")
        cmds = [
            "shell settings put global low_power 0",
            "shell dumpsys battery unplug",
            f"shell dumpsys battery set level {self.TRIGGER_LEVEL}",
        ]
        for cmd in cmds:
            execute_adb(cmd)
        logger.info(f"Battery level set to {self.TRIGGER_LEVEL}% and unplugged.")
        time.sleep(2)
        return True

    def is_successful(self, controller: AndroidController) -> tuple[float, str]:
        self._check_is_initialized()
        is_power_saver = "1" in execute_adb("shell settings get global low_power").output.strip()
        if is_power_saver:
            return 1.0, "Success: Battery saver mode is ON."
        return 0.0, "Failure: Battery saver mode is still OFF."

    def tear_down(self, controller: AndroidController) -> bool:
        super().tear_down(controller)
        execute_adb("shell settings delete system time_12_24")
        execute_adb("shell dumpsys battery reset")
        execute_adb("shell settings put global low_power 0")
        return True

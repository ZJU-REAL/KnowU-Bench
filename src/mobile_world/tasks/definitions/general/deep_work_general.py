"""General task: enable Do Not Disturb / silent mode for deep work."""

import time

from mobile_world.runtime.controller import AndroidController
from mobile_world.runtime.utils.helpers import execute_adb
from mobile_world.tasks.base import BaseTask


class DeepWorkGeneralTask(BaseTask):
    """Enable DND or silent mode with explicit instruction."""

    task_tags = {"general", "easy"}
    snapshot_tag = "init_state"
    app_names = {"Settings"}

    TARGET_TIMESTAMP = "021009002026.00"

    goal = "我准备开始专注工作了，请帮我打开勿扰模式（Do Not Disturb）或将手机调为静音模式。"

    def initialize_task_hook(self, controller: AndroidController) -> bool:
        execute_adb("shell settings put global zen_mode 0")
        execute_adb("shell cmd audio set-ringer-mode normal")
        execute_adb("shell settings put global auto_time 0")
        execute_adb("shell settings put system time_12_24 24")
        if not execute_adb(f"shell su 0 date {self.TARGET_TIMESTAMP}").success:
            execute_adb(f"shell date {self.TARGET_TIMESTAMP}")
        time.sleep(3)
        return True

    def is_successful(self, controller: AndroidController) -> tuple[float, str]:
        self._check_is_initialized()
        zen_val = int(execute_adb("shell settings get global zen_mode").output.strip() or 0)
        ringer_val_str = execute_adb("shell settings get global mode_ringer").output.strip()
        ringer_val = int(ringer_val_str) if ringer_val_str.isdigit() else 2
        ringer_names = {0: "SILENT", 1: "VIBRATE", 2: "NORMAL"}
        ringer_name = ringer_names.get(ringer_val, f"UNKNOWN({ringer_val})")
        is_dnd_on = (zen_val != 0) or (ringer_val in (0, 1))
        status_desc = f"Zen: {zen_val}, Ringer: {ringer_name}"
        if is_dnd_on:
            return 1.0, f"Success: DND/Silent mode is ON. [{status_desc}]"
        return 0.0, f"Failure: DND/Silent mode is still OFF. [{status_desc}]"

    def tear_down(self, controller: AndroidController) -> bool:
        super().tear_down(controller)
        execute_adb("shell settings put global auto_time 1")
        execute_adb("shell settings delete system time_12_24")
        execute_adb("shell settings put global zen_mode 0")
        execute_adb("shell cmd audio set-ringer-mode normal")
        return True

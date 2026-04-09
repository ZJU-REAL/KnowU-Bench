"""General task: disable the morning alarm before the weekend."""

import time

from loguru import logger

from mobile_world.runtime.controller import AndroidController
from mobile_world.runtime.utils.helpers import execute_adb
from mobile_world.tasks.base import BaseTask

DB_PATH = "/data/user_de/0/com.google.android.deskclock/databases/alarms.db"
PKG_NAME = "com.google.android.deskclock"


class WeekendSleeperGeneralTask(BaseTask):
    """Disable the 07:30 alarm for the weekend."""

    task_tags = {"general", "easy"}
    snapshot_tag = "init_state"
    app_names = {"Clock"}

    ALARM_TIME = (7, 30)
    TARGET_TIMESTAMP = "052223002026.00"

    goal = (
        "明天是周六，我想睡个懒觉。"
        "请帮我把早上 7:30 的闹钟关掉。"
    )

    def _run_sql(self, sql: str) -> str:
        res = execute_adb(f'shell "sqlite3 {DB_PATH} \\"{sql}\\""', root_required=True)
        return res.output.strip() if res.success else ""

    def _inject_alarm(self):
        h, m = self.ALARM_TIME
        self._run_sql(f"DELETE FROM alarm_templates WHERE hour={h} AND minutes={m};")
        sql = (
            f"INSERT INTO alarm_templates (hour, minutes, enabled, daysofweek, vibrate, label, ringtone, delete_after_use) "
            f"VALUES ({h}, {m}, 1, 127, 1, 'Work', '', 0);"
        )
        self._run_sql(sql)
        logger.info(f"Injected active alarm at {h:02d}:{m:02d}")

    def initialize_task_hook(self, controller: AndroidController) -> bool:
        execute_adb("shell settings put global auto_time 0")
        execute_adb("shell settings put system time_12_24 24")
        execute_adb(f"shell su 0 date {self.TARGET_TIMESTAMP}")
        self._inject_alarm()
        execute_adb(f"shell am force-stop {PKG_NAME}")
        execute_adb(f"shell am start -n {PKG_NAME}/.DeskClock")
        time.sleep(5)
        execute_adb("shell input keyevent HOME")
        return True

    def is_successful(self, controller: AndroidController) -> tuple[float, str]:
        self._check_is_initialized()
        h, m = self.ALARM_TIME
        val = self._run_sql(f"SELECT enabled FROM alarm_templates WHERE hour={h} AND minutes={m};")
        is_alarm_on = val == "1"
        if not is_alarm_on:
            return 1.0, "Success: 07:30 alarm has been disabled."
        return 0.0, "Failure: 07:30 alarm is still ON."

    def tear_down(self, controller: AndroidController) -> bool:
        super().tear_down(controller)
        execute_adb(f"shell am force-stop {PKG_NAME}")
        time.sleep(1)
        execute_adb("shell settings put global auto_time 1")
        execute_adb("shell settings delete system time_12_24")
        h, m = self.ALARM_TIME
        self._run_sql(f"DELETE FROM alarm_templates WHERE hour={h} AND minutes={m};")
        return True

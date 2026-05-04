"""General task: set a specific weekend alarm with explicit time."""

from typing import Any

from loguru import logger

from knowu_bench.runtime.controller import AndroidController
from knowu_bench.runtime.utils.helpers import execute_adb, execute_root_sql
from knowu_bench.tasks.base import BaseTask
from datetime import datetime

WEEKEND_MASK = 96  # Saturday(32) + Sunday(64)


class SetAlarmGeneralTask(BaseTask):
    """Set a weekend alarm at a specific time with a specific ringtone."""

    task_tags = {"general", "easy"}
    snapshot_tag = "init_state"
    app_names = {"Clock"}
    goal = (
        "请在 Clock 应用中设置一个周末（周六和周日）的起床闹钟，"
        "时间为早上 8:30，铃声选择 'Bright Morning'。"
    )

    def initialize_task_hook(self, controller: AndroidController) -> bool:
        execute_adb("shell settings put global auto_time 0")
        ts = datetime.now().strftime("%m%d%H%M%Y.%S")
        res = execute_adb(f"shell su root date {ts}")
        if not res.success:
            execute_adb(f"shell date {ts}")
        return True

    @staticmethod
    def _safe_int(value: Any, default: int = 0) -> int:
        try:
            if value is None or value == "":
                return default
            return int(value)
        except Exception:
            return default

    def _get_all_alarms_via_adb(self) -> list[dict[str, Any]]:
        db_path = "/data/user_de/0/com.google.android.deskclock/databases/alarms.db"
        sql_query = (
            "SELECT _id, hour, minutes, enabled, daysofweek, vibrate, ringtone, label, blackout_end "
            "FROM alarm_templates ORDER BY _id DESC;"
        )
        result = execute_root_sql(db_path, sql_query)
        if not result:
            return []

        alarms: list[dict[str, Any]] = []
        for line in result.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split("|")
            if len(parts) < 8:
                continue
            if len(parts) >= 9:
                alarms.append({
                    "id": self._safe_int(parts[0]),
                    "hour": self._safe_int(parts[1]),
                    "minutes": self._safe_int(parts[2]),
                    "enabled": bool(self._safe_int(parts[3])),
                    "daysofweek": self._safe_int(parts[4]),
                    "ringtone": parts[6],
                })
            else:
                alarms.append({
                    "id": -1,
                    "hour": self._safe_int(parts[0]),
                    "minutes": self._safe_int(parts[1]),
                    "enabled": bool(self._safe_int(parts[2])),
                    "daysofweek": self._safe_int(parts[3]),
                    "ringtone": parts[5] if len(parts) > 5 else "",
                })
        return alarms

    def is_successful(self, controller: AndroidController) -> float | tuple[float, str]:
        self._check_is_initialized()

        alarms = self._get_all_alarms_via_adb()
        if not alarms:
            return 0.0, "Failure: No alarm data found."

        score = 0.0
        checks = []

        weekend_alarm = None
        for alarm in alarms:
            if alarm.get("enabled") and (alarm.get("daysofweek", 0) & WEEKEND_MASK) == WEEKEND_MASK:
                weekend_alarm = alarm
                break

        if weekend_alarm is None:
            return 0.0, "Failure: No enabled weekend alarm found."

        score += 0.5
        checks.append("weekend_alarm=FOUND")

        hour = weekend_alarm.get("hour", -1)
        minutes = weekend_alarm.get("minutes", -1)
        if hour == 8 and minutes == 30:
            score += 0.5
            checks.append("time=8:30(OK)")
        elif hour == 8:
            score += 0.3
            checks.append(f"time=8:{minutes:02d}(CLOSE)")
        else:
            checks.append(f"time={hour}:{minutes:02d}(WRONG)")

        reason = f"Alarm check. {', '.join(checks)}. Score: {score:.1f}"
        logger.info(f"[Eval] {reason}")
        return score, reason

    def tear_down(self, controller: AndroidController) -> bool:
        super().tear_down(controller)
        return True

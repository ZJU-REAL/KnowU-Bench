from loguru import logger
from knowu_bench.runtime.utils.helpers import execute_adb
from .base import BaseSetup

class ClockSetup(BaseSetup):
    """Handles data injection for Clock app via SQLite"""

    DB_PATH = "/data/user_de/0/com.google.android.deskclock/databases/alarms.db"

    # FIX: 修正位掩码定义 (DeskClock on Emulator treats Mon as 1)
    # Mon=1, Tue=2, Wed=4, Thu=8, Fri=16, Sat=32, Sun=64
    DAYS_MAP = {
        "mon": 1, "tue": 2, "wed": 4, "thu": 8, "fri": 16, "sat": 32, "sun": 64
    }

    def setup(self, clock_config: dict) -> bool:
        if not isinstance(clock_config, dict) or "alarms" not in clock_config:
            logger.error("Invalid clock configuration")
            return False

        alarms = clock_config["alarms"]
        success_count = 0

        for alarm in alarms:
            time_str = alarm.get("time", "")
            if not time_str or ":" not in time_str:
                continue

            try:
                # 1. Parse Fields
                hour, minute = map(int, time_str.split(":"))
                label = alarm.get("label", "").replace("'", "''")
                status = str(alarm.get("status", "on")).lower()
                enabled = 1 if status == "on" else 0
                
                # Parse Vibrate (bool -> int)
                vibrate = 1 if alarm.get("vibrate", True) else 0
                
                # Parse Delete After Use (bool -> int)
                delete_after_use = 1 if alarm.get("delete_after_use", False) else 0

                # Parse Repeat Days (list -> int bitmask)
                repeat_days = alarm.get("repeat", [])
                daysofweek = self._calculate_day_mask(repeat_days)

                # 2. Clean up existing alarm at same time (Force Update)
                # 先删除旧的同时间闹钟，防止配置冲突导致跳过更新
                delete_sql = f"DELETE FROM alarm_templates WHERE hour={hour} AND minutes={minute};"
                delete_cmd = f'adb -s {self.controller.device} shell "sqlite3 {self.DB_PATH} \\"{delete_sql}\\""'
                execute_adb(delete_cmd, output=False, root_required=True)

                # 3. Insert new alarm
                insert_sql = (
                    "INSERT INTO alarm_templates "
                    "(hour, minutes, enabled, daysofweek, vibrate, label, ringtone, delete_after_use) "
                    f"VALUES ({hour}, {minute}, {enabled}, {daysofweek}, {vibrate}, '{label}', '', {delete_after_use});"
                )

                insert_cmd = f'adb -s {self.controller.device} shell "sqlite3 {self.DB_PATH} \\"{insert_sql}\\""'
                res = execute_adb(insert_cmd, output=True, root_required=True)
                
                if res.success:
                    success_count += 1
                    logger.debug(f"Injected alarm: {time_str} [Days:{daysofweek} Vib:{vibrate}]")
                else:
                    logger.error(f"Failed to insert alarm {time_str}: {res.error}")
                
            except Exception as e:
                logger.error(f"Failed to inject alarm {time_str}: {e}")

        logger.info(f"Successfully processed {success_count} alarms")
        return success_count > 0

    def _calculate_day_mask(self, days: list) -> int:
        """Converts list like ['Mon', 'Tue'] to bitmask integer"""
        if not days or not isinstance(days, list):
            return 0
        
        mask = 0
        for day in days:
            key = str(day).lower()[:3]
            if key in self.DAYS_MAP:
                mask |= self.DAYS_MAP[key]
        return mask
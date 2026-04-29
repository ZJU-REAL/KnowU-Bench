import random
from datetime import datetime, timezone
from loguru import logger
from knowu_bench.runtime.utils.helpers import execute_adb
from .base import BaseSetup

class CalendarSetup(BaseSetup):
    """Handles data injection for Fossify Calendar app via SQLite"""

    DB_PATH = "/data/user/0/org.fossify.calendar/databases/events.db"

    def setup(self, calendar_config: dict) -> bool:
        if not isinstance(calendar_config, dict) or "events" not in calendar_config:
            logger.error("Invalid calendar configuration")
            return False

        # 1. Parse Base Date
        current_date_str = calendar_config.get("current_date", "")
        # FIX: 使用 UTC 时间作为基准，避免容器时区(如+8)导致的时间戳偏移
        base_date = datetime.now(timezone.utc)
        
        if current_date_str:
            try:
                date_part = current_date_str.split(" ")[0]
                # 解析为 UTC 时间对象
                dt = datetime.strptime(date_part, "%Y-%m-%d")
                base_date = dt.replace(tzinfo=timezone.utc)
            except ValueError:
                logger.warning(f"Failed to parse date: {current_date_str}, using now(UTC)")

        events = calendar_config["events"]
        success_count = 0

        for event in events:
            title = event.get("title", "")
            time_str = event.get("time", "")
            location = event.get("location", "")
            
            description = event.get("description", "")
            if "priority" in event:
                description = f"{description} [Priority: {event['priority']}]".strip()

            if not title or not time_str:
                continue

            try:
                # 2. Calculate Timestamps (UTC)
                start_ts, end_ts = self._parse_time_range(base_date, time_str)
                
                # 3. Insert into DB
                if self._insert_event(title, start_ts, end_ts, location, description):
                    success_count += 1
                    
            except Exception as e:
                logger.error(f"Failed to inject event '{title}': {e}")

        logger.info(f"Successfully processed {success_count} calendar events")
        return success_count > 0

    def _parse_time_range(self, base_date: datetime, time_str: str) -> tuple[int, int]:
        try:
            parts = time_str.split("-")
            start_part = parts[0].strip()
            end_part = parts[1].strip() if len(parts) > 1 else start_part

            s_h, s_m = map(int, start_part.split(":"))
            e_h, e_m = map(int, end_part.split(":"))

            # FIX: 显式保留 UTC 时区信息
            start_dt = base_date.replace(hour=s_h, minute=s_m, second=0, tzinfo=timezone.utc)
            end_dt = base_date.replace(hour=e_h, minute=e_m, second=0, tzinfo=timezone.utc)

            return int(start_dt.timestamp()), int(end_dt.timestamp())
        except Exception:
            ts = int(base_date.timestamp())
            return ts, ts + 3600

    def _insert_event(self, title: str, start_ts: int, end_ts: int, location: str, description: str) -> bool:
        # Escape single quotes for SQL
        title = title.replace("'", "''")
        location = location.replace("'", "''")
        description = description.replace("'", "''")
        
        import_id = f"mock{random.randint(1000, 9999)}"
        # last_updated 存的是毫秒
        last_updated = int(datetime.now(timezone.utc).timestamp() * 1000)
        
        # 使用 f-string 确保所有变量都被正确替换
        insert_sql = (
            "INSERT INTO events ("
            "start_ts, end_ts, title, location, description, "
            "reminder_1_minutes, reminder_2_minutes, reminder_3_minutes, "
            "reminder_1_type, reminder_2_type, reminder_3_type, "
            "repeat_interval, repeat_rule, repeat_limit, "
            "repetition_exceptions, attendees, import_id, time_zone, "
            "flags, event_type, parent_id, last_updated, source, "
            "availability, access_level, color, type, status"
            ") VALUES ("
            f"{start_ts}, {end_ts}, '{title}', '{location}', '{description}', "
            "-1, -1, -1, "
            "0, 0, 0, "
            "0, 0, 0, "
            f"'[]', '[]', '{import_id}', 'UTC', "
            f"0, 1, 0, {last_updated}, 'manual', "
            "0, 0, 0, 0, 1"
            ");"
        )

        cmd = f'adb -s {self.controller.device} shell "sqlite3 {self.DB_PATH} \\"{insert_sql}\\""'
        result = execute_adb(cmd, root_required=True)

        if not result.success:
            logger.error(f"SQLite error: {result.error}")
            return False
        return True
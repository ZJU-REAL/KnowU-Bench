"""General task: send a clock-out message on Mattermost."""

import subprocess
import time

try:
    from knowu_bench.runtime.app_helpers.mattermost import start_mattermost_backend
except ImportError:
    start_mattermost_backend = lambda: False

from knowu_bench.runtime.controller import AndroidController
from knowu_bench.runtime.utils.helpers import execute_adb
from knowu_bench.tasks.base import BaseTask


class ClockOutGeneralTask(BaseTask):
    """Send a clock-out message on Mattermost with explicit instruction."""

    task_tags = {"general", "easy"}
    snapshot_tag = "init_state"
    app_names = {"Mattermost"}

    TARGET_CHANNEL = "town-square"
    TARGET_TIMESTAMP = "021017592026.00"
    EXPECTED_KEYWORDS = ["下班", "辛苦", "明天见", "clocking", "out", "bye", "leaving", "see you"]

    goal = (
        "现在快下班了，请在 Mattermost 的 town-square 频道"
        "发一条下班消息：'今天的工作结束了，大家辛苦了！明天见！'"
    )

    def __init__(self, params=None):
        super().__init__(params)
        self.start_timestamp = 0

    def initialize_task_hook(self, controller: AndroidController) -> bool:
        self.start_timestamp = int(time.time() * 1000)
        try:
            start_mattermost_backend()
        except Exception:
            pass
        time.sleep(5)
        execute_adb("reverse tcp:8065 tcp:8065")
        cmds = [
            "shell settings put global auto_time 0",
            "shell settings put system time_12_24 24",
            f"shell su 0 date {self.TARGET_TIMESTAMP}",
            "shell am force-stop com.mattermost.rn",
            "shell am start -n com.mattermost.rn/.MainActivity",
        ]
        for cmd in cmds:
            execute_adb(cmd)
        time.sleep(8)
        execute_adb("shell input keyevent HOME")
        return True

    def _get_latest_db_message(self) -> tuple[bool, str]:
        try:
            channel = (self.TARGET_CHANNEL or "").replace("'", "''")
            sql = (
                f"SELECT p.message FROM posts p JOIN channels c ON p.channelid = c.id "
                f"WHERE p.createat > {self.start_timestamp} AND p.type = '' AND c.name = '{channel}' "
                f"ORDER BY p.createat DESC LIMIT 1;"
            )
            cmd = [
                "docker", "exec", "mattermost-docker-postgres-1",
                "psql", "-U", "mmuser", "-d", "mattermost", "-t", "-c", sql,
            ]
            res = subprocess.run(cmd, capture_output=True, text=True)
            output = res.stdout.strip().lower()
            return (True, output) if output else (False, "Silent")
        except Exception as e:
            return False, str(e)

    def is_successful(self, controller: AndroidController) -> tuple[float, str]:
        self._check_is_initialized()
        msg_sent, msg_content = self._get_latest_db_message()
        if not msg_sent:
            return 0.0, "Failure: No message sent in town-square channel."
        content_matched = any(kw in msg_content for kw in self.EXPECTED_KEYWORDS)
        status = f"Channel='{self.TARGET_CHANNEL}', Sent: '{msg_content[:80]}'"
        if content_matched:
            return 1.0, f"Success: Clock-out message sent correctly. [{status}]"
        return 0.0, f"Failure: Message sent but content does not match. [{status}]"

    def tear_down(self, controller: AndroidController) -> bool:
        super().tear_down(controller)
        execute_adb("shell settings put global auto_time 1")
        execute_adb("shell settings delete system time_12_24")
        return True

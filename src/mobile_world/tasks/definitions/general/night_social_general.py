"""General task: enable dark mode at night."""

import re
import time

try:
    from mobile_world.runtime.app_helpers.mastodon import start_mastodon_backend, is_mastodon_healthy
except ImportError:
    start_mastodon_backend, is_mastodon_healthy = lambda: False, lambda: True

from mobile_world.runtime.controller import AndroidController
from mobile_world.runtime.utils.helpers import execute_adb
from mobile_world.tasks.base import BaseTask


class NightSocialGeneralTask(BaseTask):
    """Enable dark mode with explicit instruction."""

    task_tags = {"general", "easy"}
    snapshot_tag = "init_state"
    app_names = {"Settings", "Mastodon"}

    SOCIAL_PACKAGE = "org.joinmastodon.android.mastodon"
    TARGET_TIMESTAMP = "021223002026.00"

    goal = "现在是晚上 23:00，屏幕太亮了，请帮我打开深色模式（Dark Mode）。"

    def initialize_task_hook(self, controller: AndroidController) -> bool:
        if not is_mastodon_healthy():
            start_mastodon_backend()
            for _ in range(5):
                if is_mastodon_healthy():
                    break
                time.sleep(3)

        execute_adb("shell settings put global auto_time 0")
        execute_adb("shell settings put system time_12_24 24")
        execute_adb(f"shell su 0 date {self.TARGET_TIMESTAMP}")
        execute_adb("shell cmd uimode night no")
        time.sleep(2)

        execute_adb(f"shell am force-stop {self.SOCIAL_PACKAGE}")
        res = execute_adb(f"shell cmd package resolve-activity --brief {self.SOCIAL_PACKAGE}")
        if res.success and (match := re.search(r'([a-zA-Z0-9\.]+/[a-zA-Z0-9\._]+)', res.output or "")):
            execute_adb(f"shell am start -n {match.group(1)}")
        else:
            execute_adb(f"shell monkey -p {self.SOCIAL_PACKAGE} -c android.intent.category.LAUNCHER 1")
        time.sleep(6)
        return True

    def is_successful(self, controller: AndroidController) -> tuple[float, str]:
        self._check_is_initialized()
        is_dark_mode = "yes" in execute_adb("shell cmd uimode night").output.lower()
        if is_dark_mode:
            return 1.0, "Success: Dark mode is ON."
        return 0.0, "Failure: Dark mode is still OFF."

    def tear_down(self, controller: AndroidController) -> bool:
        super().tear_down(controller)
        execute_adb("shell settings put global auto_time 1")
        execute_adb("shell settings delete system time_12_24")
        execute_adb("shell cmd uimode night no")
        return True

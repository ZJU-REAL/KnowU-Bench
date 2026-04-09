"""General task: open research paper websites in Chrome."""

import os
import sqlite3
import tempfile
from urllib.parse import urlparse

from loguru import logger

from mobile_world.runtime.controller import AndroidController
from mobile_world.runtime.utils.helpers import execute_adb
from mobile_world.tasks.base import BaseTask


class MorningPaperReadingGeneralTask(BaseTask):
    """Open alphaxiv.org and huggingface.co/papers in Chrome."""

    task_tags = {"general", "easy"}
    snapshot_tag = "init_state"
    app_names = {"Chrome"}

    CHROME_PKG = "com.android.chrome"
    CHROME_HISTORY_PATH = "/data/data/com.android.chrome/app_chrome/Default/History"
    TARGET_URLS = ["https://www.alphaxiv.org", "https://huggingface.co/papers"]
    TARGET_TIMESTAMP = "021008252026.00"

    goal = (
        "请用 Chrome 浏览器依次打开以下两个网站：\n"
        "1. https://www.alphaxiv.org\n"
        "2. https://huggingface.co/papers"
    )

    def initialize_task_hook(self, controller: AndroidController) -> bool:
        execute_adb("shell settings put global auto_time 0")
        execute_adb("shell settings put system time_12_24 24")
        execute_adb(f"shell su 0 date {self.TARGET_TIMESTAMP}")
        cmds = [
            "settings put global http_proxy 10.130.138.46:7897",
            f"am force-stop {self.CHROME_PKG}",
            f"pm clear {self.CHROME_PKG}",
            f"am start -n {self.CHROME_PKG}/com.google.android.apps.chrome.Main",
        ]
        for cmd in cmds:
            execute_adb(f"shell {cmd}")
        return True

    def _get_visited_urls(self) -> list[str]:
        execute_adb(f"shell am force-stop {self.CHROME_PKG}")
        tmp_remote = "/data/local/tmp/chrome_history_dump"
        with tempfile.NamedTemporaryFile(delete=False) as tmp_local:
            local_db = tmp_local.name
        try:
            cmd = f"cp {self.CHROME_HISTORY_PATH} {tmp_remote} && chmod 666 {tmp_remote}"
            execute_adb(f"shell \"su 0 sh -c '{cmd}'\"")
            execute_adb(f"pull {tmp_remote} {local_db}")
            execute_adb(f"shell rm {tmp_remote}")
            if os.path.getsize(local_db) == 0:
                return []
            with sqlite3.connect(local_db) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='urls'")
                if not cursor.fetchone():
                    return []
                cursor.execute("SELECT url FROM urls ORDER BY last_visit_time DESC LIMIT 10")
                return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            logger.warning(f"Failed to read history DB: {e}")
            return []
        finally:
            if os.path.exists(local_db):
                os.remove(local_db)

    def is_successful(self, controller: AndroidController) -> tuple[float, str]:
        self._check_is_initialized()
        visited = self._get_visited_urls()
        if not visited:
            return 0.0, "Failure: No browsing history found."

        visited_text = " ".join(visited).lower()
        missing = [url for url in self.TARGET_URLS if urlparse(url).netloc not in visited_text]
        if missing:
            return 0.0, f"Failure: Did not visit: {missing}"
        return 1.0, "Success: Both target websites were visited."

    def tear_down(self, controller: AndroidController) -> bool:
        super().tear_down(controller)
        execute_adb("shell settings put global http_proxy :0")
        execute_adb("shell settings put global auto_time 1")
        execute_adb("shell settings delete system time_12_24")
        return True

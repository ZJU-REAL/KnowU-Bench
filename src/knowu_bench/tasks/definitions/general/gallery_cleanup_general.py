"""General task: delete old screenshots from the gallery."""

import time
from datetime import datetime, timedelta

from loguru import logger

from knowu_bench.runtime.controller import AndroidController
from knowu_bench.runtime.utils.helpers import execute_adb
from knowu_bench.tasks.base import BaseTask


class GalleryCleanupGeneralTask(BaseTask):
    """Delete screenshots older than 7 days from the Screenshots directory."""

    task_tags = {"general", "hard"}
    snapshot_tag = "init_state"
    app_names = {"Gallery"}

    SCREENSHOTS_DIR = "/sdcard/Pictures/Screenshots"
    NUM_FILES = 3
    OLDER_THAN_DAYS = 7
    TARGET_TIMESTAMP = "052217002026.00"

    goal = (
        "请帮我删除 Screenshots 目录下超过 7 天的旧截图。"
        "保留最近 7 天内的截图，只删除更早的。"
    )

    def __init__(self, params=None):
        super().__init__(params)
        self.run_datetime = datetime(2026, 5, 22, 17, 0, 0)

    def _setup_files(self, controller: AndroidController):
        execute_adb(f"shell mkdir -p {self.SCREENSHOTS_DIR}")
        controller.get_screenshot("temp_asset", "/tmp")
        for i in range(self.NUM_FILES):
            remote = f"{self.SCREENSHOTS_DIR}/Screenshot_{i + 1}.png"
            controller.push_file("/tmp/temp_asset.png", remote)
            days_ago = (self.OLDER_THAN_DAYS + 10) if i < 2 else 2
            ts = (self.run_datetime - timedelta(days=days_ago)).strftime("%Y%m%d%H%M.%S")
            execute_adb(f"shell touch -t {ts} {remote}")
            controller.refresh_media_scan(remote)
        logger.info(f"Pushed {self.NUM_FILES} screenshots to {self.SCREENSHOTS_DIR}")

    def initialize_task_hook(self, controller: AndroidController) -> bool:
        execute_adb("shell settings put global auto_time 0")
        execute_adb("shell settings put system time_12_24 24")
        execute_adb(f"shell su 0 date {self.TARGET_TIMESTAMP}")
        self._setup_files(controller)
        execute_adb("shell am force-stop com.simplemobiletools.gallery.pro")
        execute_adb("shell am start -n com.simplemobiletools.gallery.pro/.activities.MainActivity")
        time.sleep(5)
        execute_adb("shell input keyevent HOME")
        return True

    def _get_files_info(self) -> tuple[int, list]:
        res = execute_adb(f"shell ls {self.SCREENSHOTS_DIR}")
        if not res.success:
            return 0, []
        files = [f for f in (res.output or "").splitlines() if f and "No such file" not in f]
        return len(files), files

    def is_successful(self, controller: AndroidController) -> tuple[float, str]:
        self._check_is_initialized()
        count, files = self._get_files_info()

        # 2 old files should be deleted, 1 recent file should remain
        expected_remaining = 1
        if count != expected_remaining:
            return 0.0, f"Failure: Expected {expected_remaining} file(s), found {count}. Files: {files}"

        now_ts = int(self.run_datetime.timestamp())
        for name in files:
            cmd = (
                f"shell stat -c %Y {self.SCREENSHOTS_DIR}/{name} "
                f"|| shell toybox stat -c %Y {self.SCREENSHOTS_DIR}/{name}"
            )
            res = execute_adb(cmd)
            if res.success:
                ts_str = res.output.strip().splitlines()[0]
                if ts_str.isdigit() and (now_ts - int(ts_str)) / 86400 > self.OLDER_THAN_DAYS:
                    return 0.0, f"Failure: Old screenshot '{name}' still remains."

        return 1.0, f"Success: Cleanup completed. Remaining: {count} file(s)."

    def tear_down(self, controller: AndroidController) -> bool:
        super().tear_down(controller)
        execute_adb("shell settings put global auto_time 1")
        execute_adb("shell settings delete system time_12_24")
        execute_adb(f"shell rm -rf {self.SCREENSHOTS_DIR}/*")
        return True

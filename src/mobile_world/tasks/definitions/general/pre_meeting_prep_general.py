"""General task: open a document to prepare for a meeting."""

import os
import re
import time
from datetime import datetime, timedelta
from urllib.parse import unquote

from loguru import logger

try:
    from mobile_world.runtime.app_helpers.fossify_calendar import insert_calendar_event
except ImportError:
    insert_calendar_event = lambda *args, **kwargs: False

from mobile_world.runtime.controller import AndroidController
from mobile_world.runtime.utils.helpers import execute_adb
from mobile_world.tasks.base import BaseTask


class PreMeetingPrepGeneralTask(BaseTask):
    """Open a specific document to prepare for an upcoming meeting."""

    task_tags = {"general", "easy"}
    snapshot_tag = "init_state"
    app_names = {"Calendar", "Files", "Docreader"}

    DOC_NAME = "Agent_Learning_via_Early_Experience.pdf"
    DOC_SOURCE_PATH = "src/mobile_world/cache/users/aiden_lin/Agent_Learning_via_Early_Experience.pdf"
    DOC_PATH = "/sdcard/Documents"
    MEETING_TITLE = "Product Review"
    MEETING_START = "2026-05-20 09:54:47"
    MEETING_END = "2026-05-20 10:54:47"
    SIMULATION_DATETIME = "2026-05-20 09:55:00"

    CALENDAR_PACKAGES = ["org.fossify.calendar", "com.simplemobiletools.calendar.pro"]
    READER_KEYWORDS = ["doc", "pdf", "reader", "file", "office", "wps", "sheet", "slide"]

    goal = (
        f"我马上有个会议（{MEETING_TITLE}），"
        f"请打开 Files 中 Documents 文件夹里的 {DOC_NAME} 文档来准备会议。"
    )

    def initialize_task_hook(self, controller: AndroidController) -> bool:
        local_path = self.DOC_SOURCE_PATH
        if not os.path.isabs(local_path):
            local_path = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "../../../../../", local_path)
            )
        if not os.path.exists(local_path):
            logger.error(f"Local source file not found: {local_path}")
            return False

        remote_path = f"{self.DOC_PATH}/{self.DOC_NAME}"
        execute_adb(f"shell mkdir -p {self.DOC_PATH}")
        controller.push_file(local_path, remote_path)
        controller.refresh_media_scan(remote_path)

        execute_adb("shell settings put global auto_time 0")
        execute_adb("shell settings put system time_12_24 24")

        start_dt = datetime.strptime(self.MEETING_START, "%Y-%m-%d %H:%M:%S")
        pre_reminder = start_dt - timedelta(minutes=1, seconds=5)
        execute_adb(f"shell su 0 date {pre_reminder.strftime('%m%d%H%M%Y.%S')}")

        try:
            insert_calendar_event(
                title=self.MEETING_TITLE,
                start_time=self.MEETING_START,
                end_time=self.MEETING_END,
                location="Room A",
                description=f"Open '{self.DOC_NAME}' before the meeting starts.",
                reminder_1_minutes=0,
                reminder_2_minutes=5,
                reminder_3_minutes=0,
            )
        except Exception:
            pass

        cal_pkg = next(
            (p for p in self.CALENDAR_PACKAGES
             if f"package:{p}" in (execute_adb("shell pm list packages").output or "")),
            None,
        )
        if cal_pkg:
            execute_adb(f"shell appops set {cal_pkg} POST_NOTIFICATION allow")
            execute_adb(f"shell am force-stop {cal_pkg}")
            execute_adb(f"shell monkey -p {cal_pkg} -c android.intent.category.LAUNCHER 1")
            time.sleep(3)

        target_adb_time = datetime.strptime(
            self.SIMULATION_DATETIME, "%Y-%m-%d %H:%M:%S"
        ).strftime("%m%d%H%M%Y.%S")
        execute_adb(f"shell su 0 date {target_adb_time}")
        time.sleep(5)
        execute_adb("shell input keyevent HOME")
        time.sleep(2)
        return True

    def _check_file_intent(self) -> bool:
        res = execute_adb("shell dumpsys activity activities")
        if not res.success:
            return False
        output = res.output or ""

        top_match = re.search(
            r"topResumedActivity=ActivityRecord\{([0-9a-f]+)\s+u\d+\s+([^\s]+)", output
        )
        if not top_match:
            return False

        top_token = top_match.group(1)
        block_match = re.search(
            rf"\* Hist\s+#\d+:\s+ActivityRecord\{{{top_token}.*?(?=\n\s+\* Hist\s+#|\n\n|\Z)",
            output,
            re.DOTALL,
        )
        if not block_match:
            return False

        top_block = block_match.group(0)
        target_path = f"{self.DOC_PATH}/{self.DOC_NAME}"

        if self.DOC_NAME in top_block or target_path in top_block:
            return True

        if dat_match := re.search(r"Intent \{[^\n]*\bdat=([^\s]+)", top_block):
            dat_uri = unquote(dat_match.group(1))
            if id_match := re.search(r"document:([0-9]+)", dat_uri):
                media_res = execute_adb(
                    f"shell content query --uri content://media/external/file "
                    f"--where \"_id={id_match.group(1)}\" "
                    f"--projection _display_name:_data:mime_type"
                )
                if media_res.success and any(
                    k in (media_res.output or "")
                    for k in [self.DOC_NAME, target_path, f"/{self.DOC_NAME}"]
                ):
                    return True
        return False

    def is_successful(self, controller: AndroidController) -> tuple[float, str]:
        self._check_is_initialized()
        if self._check_file_intent():
            return 1.0, f"Success: Document '{self.DOC_NAME}' is open."
        current_app = controller.get_current_app()
        return 0.0, f"Failure: Document not opened. Current app: {current_app}"

    def tear_down(self, controller: AndroidController) -> bool:
        super().tear_down(controller)
        execute_adb("shell settings put global auto_time 1")
        execute_adb("shell settings delete system time_12_24")
        execute_adb(f"shell rm {self.DOC_PATH}/{self.DOC_NAME}")
        return True

"""General task: send a weekly report email with attachment."""

from loguru import logger

from mobile_world.runtime.app_helpers.mail import get_sent_email_info
from mobile_world.runtime.controller import AndroidController
from mobile_world.runtime.utils.helpers import execute_adb
from mobile_world.tasks.base import BaseTask


class SendWeeklyReportGeneralTask(BaseTask):
    """Send a weekly report email with a PDF attachment."""

    task_tags = {"general", "hard"}
    snapshot_tag = "init_state"
    app_names = {"Mail", "Files"}

    FILE_NAME = "Weekly_Report.pdf"
    REMOTE_FILE_PATH = f"/sdcard/Documents/{FILE_NAME}"
    MAIL_PACKAGE = "com.gmailclone"
    TARGET_RECIPIENT = "dean@ftu.edu.cn"

    goal = (
        "请用 Mail 应用发送一封周报邮件给 dean@ftu.edu.cn，"
        "主题为 'Weekly Report'，"
        f"并附上 Documents 文件夹中的 {FILE_NAME} 作为附件。"
    )

    def initialize_task_hook(self, controller: AndroidController) -> bool:
        execute_adb("shell settings put global auto_time 0")
        execute_adb("shell settings put system time_12_24 24")
        res = execute_adb("shell su root date 021316592026.00")
        if not res.success:
            execute_adb("shell date 021316592026.00")

        execute_adb("shell mkdir -p /sdcard/Documents")
        if not execute_adb(f"shell touch {self.REMOTE_FILE_PATH}").success:
            return False
        execute_adb(f"shell chmod 666 {self.REMOTE_FILE_PATH}")
        execute_adb(
            f'shell am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE '
            f'-d file://{self.REMOTE_FILE_PATH}'
        )
        execute_adb(f"shell am force-stop {self.MAIL_PACKAGE}")
        execute_adb(f"shell am start -n {self.MAIL_PACKAGE}/.MainActivity")
        return True

    def is_successful(self, controller: AndroidController) -> tuple[float, str]:
        self._check_is_initialized()

        try:
            email_info = get_sent_email_info()
        except Exception:
            email_info = None

        if not email_info:
            return 0.0, "Failure: No email was sent."

        score = 0.0
        checks = []

        act_recipient = email_info.get("to", "").lower()
        if self.TARGET_RECIPIENT.lower() in act_recipient:
            score += 0.4
            checks.append(f"recipient=OK({act_recipient})")
        else:
            checks.append(f"recipient=WRONG(expected={self.TARGET_RECIPIENT}, got={act_recipient})")

        attachments = email_info.get("attachments", [])
        if any(self.FILE_NAME in att.get("name", "") for att in attachments):
            score += 0.6
            checks.append(f"attachment=OK({self.FILE_NAME})")
        else:
            checks.append(f"attachment=MISSING({self.FILE_NAME})")

        reason = f"Email sent. {', '.join(checks)}. Score: {score:.1f}"
        logger.info(f"[Eval] {reason}")
        return score, reason

    def tear_down(self, controller: AndroidController) -> bool:
        super().tear_down(controller)
        execute_adb("shell settings put global auto_time 1")
        execute_adb("shell settings delete system time_12_24")
        execute_adb(f"shell rm {self.REMOTE_FILE_PATH}")
        return True

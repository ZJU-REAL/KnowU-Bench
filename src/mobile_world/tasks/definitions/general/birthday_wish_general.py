"""General task: send a birthday wish SMS."""

import time
from datetime import datetime, timedelta

from loguru import logger

try:
    from mobile_world.runtime.app_helpers.fossify_calendar import insert_calendar_event
except ImportError:
    insert_calendar_event = lambda *args, **kwargs: True

try:
    from mobile_world.runtime.app_helpers.system import check_sms_via_adb
except ImportError:
    check_sms_via_adb = lambda *args, **kwargs: False

try:
    from mobile_world.runtime.setup.contacts import ContactsSetup
except ImportError:
    ContactsSetup = None

from mobile_world.runtime.controller import AndroidController
from mobile_world.runtime.utils.helpers import execute_adb
from mobile_world.tasks.base import BaseTask


class BirthdayWishGeneralTask(BaseTask):
    """Send a birthday wish SMS with explicit instruction."""

    task_tags = {"general", "easy"}
    snapshot_tag = "init_state"
    app_names = {"Calendar", "Messages"}

    CONTACT_NAME = "Mom"
    CONTACT_PHONE = "13800001111"
    EVENT_TITLE = "Mom Birthday"
    EVENT_DATE = "2026-05-20"
    EVENT_START = "2026-05-20 08:00:00"
    EVENT_END = "2026-05-20 23:59:59"
    REMINDER_MINUTES = 10
    KEYWORDS = ["happy birthday", "生日快乐", "birthday wish"]

    PKGS = {"cal": "org.fossify.calendar", "sms": "com.simplemobiletools.sms_messenger"}

    goal = (
        f"今天是 {CONTACT_NAME} 的生日，请给她发一条生日祝福短信，"
        f"号码是 {CONTACT_PHONE}，内容要包含 'Happy Birthday' 或 '生日快乐'。"
    )

    def _manage_contact(self, controller, mode="inject"):
        if mode == "inject":
            if not (ContactsSetup and self.CONTACT_NAME and self.CONTACT_PHONE):
                return
            try:
                ContactsSetup(controller).setup({
                    "list": [{"name": self.CONTACT_NAME, "phone": self.CONTACT_PHONE}]
                })
            except Exception as e:
                logger.error(f"Contact injection failed: {e}")
        elif mode == "clean" and self.CONTACT_NAME:
            safe = self.CONTACT_NAME.replace("'", "\\'")
            execute_adb(
                f"shell content delete --uri content://com.android.contacts/raw_contacts "
                f"--where \"display_name='{safe}'\""
            )

    def initialize_task_hook(self, controller: AndroidController) -> bool:
        execute_adb("shell settings put global auto_time 0")
        execute_adb("shell settings put system time_12_24 24")

        start_dt = datetime.strptime(self.EVENT_START, "%Y-%m-%d %H:%M:%S")
        pre_time = start_dt - timedelta(minutes=self.REMINDER_MINUTES + 5)
        execute_adb(f"shell su 0 date {pre_time.strftime('%m%d%H%M%Y.%S')}")

        self._manage_contact(controller, "inject")
        try:
            insert_calendar_event(
                title=self.EVENT_TITLE,
                start_time=self.EVENT_START,
                end_time=self.EVENT_END,
                description="Birthday",
                reminder_1_minutes=self.REMINDER_MINUTES,
                reminder_2_minutes=5,
                reminder_3_minutes=0,
            )
        except Exception as e:
            logger.error(f"Event injection failed: {e}")

        execute_adb(f"shell appops set {self.PKGS['cal']} POST_NOTIFICATION allow")
        for pkg in self.PKGS.values():
            execute_adb(f"shell am force-stop {pkg}")
        execute_adb(f"shell monkey -p {self.PKGS['cal']} -c android.intent.category.LAUNCHER 1")
        time.sleep(3)

        trigger_time = start_dt - timedelta(seconds=13)
        execute_adb(f"shell su 0 date {trigger_time.strftime('%m%d%H%M%Y.%S')}")
        time.sleep(5)
        execute_adb("shell input keyevent HOME")
        return True

    def is_successful(self, controller: AndroidController) -> tuple[float, str]:
        self._check_is_initialized()
        has_correct = any(
            check_sms_via_adb(controller, phone_number=self.CONTACT_PHONE, content=k)
            for k in self.KEYWORDS
        )
        has_any = check_sms_via_adb(controller, phone_number=self.CONTACT_PHONE, content="")

        if has_correct:
            return 1.0, f"Success: Birthday wish sent to {self.CONTACT_NAME}."
        if has_any:
            return 0.0, "Failure: SMS sent but content does not contain birthday keywords."
        return 0.0, "Failure: No SMS was sent."

    def tear_down(self, controller: AndroidController) -> bool:
        super().tear_down(controller)
        execute_adb("shell settings put global auto_time 1")
        execute_adb("shell settings delete system time_12_24")
        self._manage_contact(controller, "clean")
        return True

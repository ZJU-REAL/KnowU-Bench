"""General task: save a new contact from an SMS notification."""

import time

try:
    from mobile_world.runtime.app_helpers.system import check_contact_via_adb
except ImportError:
    check_contact_via_adb = lambda *args, **kwargs: False

from mobile_world.runtime.controller import AndroidController
from mobile_world.runtime.utils.helpers import execute_adb
from mobile_world.tasks.base import BaseTask


class ContactSaverGeneralTask(BaseTask):
    """Save a contact from an SMS with explicit instruction."""

    task_tags = {"general", "easy"}
    snapshot_tag = "init_state"
    app_names = {"Messages", "Contacts"}

    SENDER_PHONE = "5550199"
    SENDER_NAME = "Bob"
    SMS_CONTENT = "Hi, this is Bob, my new number is 555-0199."

    goal = (
        f"我刚收到一条短信：'{SMS_CONTENT}'，发件人号码是 {SENDER_PHONE}。"
        f"请把这个号码保存为联系人，姓名填 '{SENDER_NAME}'。"
    )

    def _ensure_contact_deleted(self):
        execute_adb(
            f"shell content delete --uri content://com.android.contacts/raw_contacts "
            f"--where \"display_name='{self.SENDER_NAME}'\""
        )

    def initialize_task_hook(self, controller: AndroidController) -> bool:
        execute_adb("shell settings put system time_12_24 24")
        self._ensure_contact_deleted()
        execute_adb("shell input keyevent HOME")
        time.sleep(1)
        controller.simulate_sms(sender=self.SENDER_PHONE, message=self.SMS_CONTENT)
        time.sleep(3)
        return True

    def is_successful(self, controller: AndroidController) -> tuple[float, str]:
        self._check_is_initialized()
        is_saved_correctly = check_contact_via_adb(
            controller, name=self.SENDER_NAME, phone=self.SENDER_PHONE, company=""
        )
        is_saved_any = check_contact_via_adb(
            controller, name="", phone=self.SENDER_PHONE, company=""
        )

        if is_saved_correctly:
            return 1.0, f"Success: Contact '{self.SENDER_NAME}' saved with phone {self.SENDER_PHONE}."
        if is_saved_any:
            return 0.0, f"Failure: Contact saved but name is not '{self.SENDER_NAME}'."
        return 0.0, "Failure: Contact was not saved."

    def tear_down(self, controller: AndroidController) -> bool:
        super().tear_down(controller)
        execute_adb("shell settings delete system time_12_24")
        self._ensure_contact_deleted()
        return True

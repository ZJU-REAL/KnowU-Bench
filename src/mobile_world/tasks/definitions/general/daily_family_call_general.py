"""General task: call a family member via Contacts."""

import re
import time

from loguru import logger

try:
    from mobile_world.runtime.setup.contacts import ContactsSetup
except ImportError:
    ContactsSetup = None

from mobile_world.runtime.controller import AndroidController
from mobile_world.runtime.utils.helpers import execute_adb
from mobile_world.tasks.base import BaseTask


class DailyFamilyCallGeneralTask(BaseTask):
    """Call a specific family member from Contacts."""

    task_tags = {"general", "easy"}
    snapshot_tag = "init_state"
    app_names = {"Contacts"}

    TARGET_NAME = "Son (Qiang)"
    TARGET_PHONE = "13988887777"
    TARGET_TIMESTAMP = "052619452026.00"

    goal = (
        f"请打开 Contacts（通讯录）应用，找到联系人'{TARGET_NAME}'，"
        "然后拨打电话给他。"
    )

    def _inject_contact(self, controller: AndroidController):
        if ContactsSetup and self.TARGET_NAME and self.TARGET_PHONE:
            try:
                ContactsSetup(controller).setup({
                    "list": [{"name": self.TARGET_NAME, "phone": self.TARGET_PHONE}]
                })
            except Exception as e:
                logger.error(f"Contact injection failed: {e}")

    def _clean_contact(self):
        safe_name = self.TARGET_NAME.replace("'", "\\'")
        execute_adb(
            f"shell content delete --uri content://com.android.contacts/raw_contacts "
            f"--where \"display_name='{safe_name}'\""
        )

    def initialize_task_hook(self, controller: AndroidController) -> bool:
        execute_adb("shell settings put global auto_time 0")
        execute_adb("shell settings put system time_12_24 24")
        execute_adb(f"shell su 0 date {self.TARGET_TIMESTAMP}")
        self._inject_contact(controller)
        execute_adb("shell content delete --uri content://call_log/calls")
        execute_adb("shell input keyevent HOME")
        time.sleep(1)
        return True

    def _check_call_log(self, controller: AndroidController) -> bool:
        target = re.sub(r"[^0-9]", "", self.TARGET_PHONE)
        if not target:
            return False
        try:
            res = execute_adb(f"adb -s {controller.device} shell content query --uri content://call_log/calls")
            if not res.success or not res.output:
                return False
            for line in res.output.strip().split("\n"):
                if "type=2" in line and "number=" in line:
                    if m := re.search(r"(?:^|,\s*)number=([^,]+)", line):
                        num = re.sub(r"[^0-9]", "", m.group(1).strip())
                        if num and num.upper() != "NULL" and target == num:
                            return True
        except Exception as e:
            logger.error(f"Error checking call log: {e}")
        return False

    def _check_ongoing_call(self, controller: AndroidController) -> bool:
        target_tail = re.sub(r"[^0-9]", "", self.TARGET_PHONE)[-2:]
        if not target_tail:
            return False

        def _masked_match(raw: str) -> bool:
            num = re.sub(r"[^0-9]", "", raw or "")
            return num[-2:] == target_tail if len(num) >= 2 else num == target_tail

        try:
            telecom_out = execute_adb(f"adb -s {controller.device} shell dumpsys telecom").output or ""
            if re.search(r"\b(DIALING|CONNECTING|ACTIVE|OFFHOOK|RINGING)\b", telecom_out, re.IGNORECASE):
                tels = (
                    re.findall(r"tel:([^\s,}]+)", telecom_out, re.IGNORECASE)
                    + re.findall(r"\+?\d[\d\-\s()]{6,}\d", telecom_out)
                )
                if any(_masked_match(t) for t in tels):
                    return True
        except Exception as e:
            logger.error(f"Error checking ongoing call: {e}")
        return False

    def is_successful(self, controller: AndroidController) -> tuple[float, str]:
        self._check_is_initialized()
        call_made = self._check_call_log(controller) or self._check_ongoing_call(controller)
        if call_made:
            return 1.0, f"Success: Outgoing call made to '{self.TARGET_NAME}'."
        return 0.0, f"Failure: No outgoing call to '{self.TARGET_NAME}' ({self.TARGET_PHONE})."

    def tear_down(self, controller: AndroidController) -> bool:
        super().tear_down(controller)
        execute_adb("shell settings put global auto_time 1")
        execute_adb("shell settings delete system time_12_24")
        self._clean_contact()
        return True

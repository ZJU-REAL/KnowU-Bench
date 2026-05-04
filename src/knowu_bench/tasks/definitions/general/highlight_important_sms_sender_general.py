"""General task: check an important SMS and add sender to contacts with highlight."""

from loguru import logger

from knowu_bench.runtime.app_helpers.system import (
    check_contact_starred_via_adb,
    get_contacts_via_adb,
)
from knowu_bench.runtime.controller import AndroidController
from knowu_bench.runtime.setup.contacts import ContactsSetup
from knowu_bench.runtime.utils.helpers import execute_adb
from knowu_bench.tasks.base import BaseTask
from datetime import datetime

SENDER_NAME = "Project Office"
SENDER_PHONE = "13577776666"
SMS_CONTENT = "[URGENT] This is Project Office. Please confirm today's 16:30 review with the Dean."


class HighlightImportantSmsSenderGeneralTask(BaseTask):
    """Check an important SMS, add the sender to Contacts, and highlight (star) them."""

    task_tags = {"general", "hard"}
    snapshot_tag = "init_state"
    app_names = {"Messages", "Contacts"}
    goal = (
        f"你收到了一条来自 {SENDER_PHONE} 的重要短信，"
        f"内容为：'{SMS_CONTENT}'。"
        f"请将发件人以'{SENDER_NAME}'为名加入 Contacts 联系人，"
        "并将其标记为星标联系人（highlight）。"
    )

    @staticmethod
    def _normalize_phone(phone: str) -> str:
        return "".join(ch for ch in str(phone) if ch.isdigit())

    def initialize_task_hook(self, controller: AndroidController) -> bool:
        execute_adb("shell settings put global auto_time 0")
        ts = datetime.now().strftime("%m%d%H%M%Y.%S")
        res = execute_adb(f"shell su root date {ts}")
        if not res.success:
            execute_adb(f"shell date {ts}")

        simulate_result = controller.simulate_sms(
            sender=SENDER_PHONE,
            message=SMS_CONTENT,
        )
        if not simulate_result.success:
            return False
        return True

    def is_successful(self, controller: AndroidController) -> float | tuple[float, str]:
        self._check_is_initialized()

        contacts = get_contacts_via_adb(controller, phone_number=SENDER_PHONE) or []
        contact_exists = bool(contacts)
        is_starred = check_contact_starred_via_adb(controller, phone_number=SENDER_PHONE)

        score = 0.0
        checks = []

        if contact_exists:
            score += 0.5
            checks.append("contact_added=OK")
        else:
            checks.append("contact_added=NO")

        if is_starred:
            score += 0.5
            checks.append("starred=OK")
        else:
            checks.append("starred=NO")

        reason = f"SMS sender handling. {', '.join(checks)}. Score: {score:.1f}"
        logger.info(f"[Eval] {reason}")
        return score, reason

    def tear_down(self, controller: AndroidController) -> bool:
        super().tear_down(controller)
        return True

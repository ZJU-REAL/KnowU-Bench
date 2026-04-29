"""General task: send a specific SMS to Mom asking for money."""

from loguru import logger

from knowu_bench.runtime.app_helpers.system import check_sms_via_adb, get_sent_sms_body_via_adb
from knowu_bench.runtime.controller import AndroidController
from knowu_bench.runtime.setup.contacts import ContactsSetup
from knowu_bench.tasks.base import BaseTask

MOM_NAME = "Mom"
MOM_PHONE = "+8613800001111"


class MessagesAskMomMoneyGeneralTask(BaseTask):
    """Send Mom an SMS asking for 2000 yuan living expenses with explicit content."""

    task_tags = {"general", "easy"}
    snapshot_tag = "init_state"

    app_names = {"Messages"}
    goal = (
        f"帮我给妈妈（{MOM_NAME}，电话 {MOM_PHONE}）发一条短信，"
        "内容为：'妈，这个月生活费不够了，能不能转 2000 块给我？谢谢妈妈！'"
    )

    def initialize_task_hook(self, controller: AndroidController) -> bool:
        ContactsSetup(controller).setup({
            "list": [{"name": MOM_NAME, "phone": MOM_PHONE}]
        })
        return True

    def is_successful(self, controller: AndroidController) -> tuple[float, str]:
        self._check_is_initialized()

        phone_clean = MOM_PHONE.replace("+86", "").replace("-", "").replace(" ", "")

        sms_found = check_sms_via_adb(controller, phone_clean, [""])
        if not sms_found:
            sms_found = check_sms_via_adb(controller, MOM_PHONE, [""])

        if not sms_found:
            return 0.0, f"Failure: No SMS sent to Mom ({MOM_PHONE})."

        sms_body = get_sent_sms_body_via_adb(controller, phone_clean)
        if not sms_body:
            sms_body = get_sent_sms_body_via_adb(controller, MOM_PHONE)

        score = 0.0
        checks = []

        score += 0.5
        checks.append("sms_sent=OK")

        money_keywords = ["生活费", "2000", "转", "钱", "money"]
        has_money_content = any(kw in (sms_body or "") for kw in money_keywords)
        if has_money_content:
            score += 0.5
            checks.append("content=OK")
        else:
            score += 0.1
            checks.append(f"content=PARTIAL('{(sms_body or '')[:50]}')")

        reason = f"SMS to Mom. {', '.join(checks)}. Body: {(sms_body or '')[:80]}. Score: {score:.1f}"
        logger.info(f"[Eval] {reason}")
        return score, reason

    def tear_down(self, controller: AndroidController) -> bool:
        super().tear_down(controller)
        return True

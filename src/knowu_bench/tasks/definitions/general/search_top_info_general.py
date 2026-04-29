"""General task: search for AI news and send email with explicit instructions."""

from loguru import logger

from knowu_bench.runtime.app_helpers.mail import get_sent_email_info
from knowu_bench.runtime.app_helpers.system import enable_auto_time_sync, reset_chrome
from knowu_bench.runtime.controller import AndroidController
from knowu_bench.tasks.base import BaseTask

KEVIN_EMAIL = "kevin@example.com"


class SearchTopInfoGeneralTask(BaseTask):
    """Search for recent AI news and send an email to Kevin with a summary."""

    task_tags = {"general", "hard"}
    snapshot_tag = "init_state"

    app_names = {"Chrome", "Mail"}
    goal = (
        "Search for the recent news in the field of Artificial Intelligence, "
        f"and send an email to Kevin ({KEVIN_EMAIL}) with a subject line that includes 'AI' "
        "and the following message:\n"
        "Here is the recent news in the AI field:\n"
        "[One sentence summary of the recent news you found]"
    )

    def initialize_task_hook(self, controller: AndroidController) -> bool:
        try:
            if not enable_auto_time_sync(controller):
                return False
            reset_chrome(controller)
            return True
        except Exception as exc:
            logger.error(f"Initialize search task failed: {exc}")
            return False

    def is_successful(self, controller: AndroidController) -> float | tuple[float, str]:
        self._check_is_initialized()

        email = get_sent_email_info()
        if email is None:
            return 0.0, "Failure: No email found."

        to_addr = str(email.get("to", "")).strip()
        subject = str(email.get("subject", "")).strip()
        body = str(email.get("body", "")).strip()

        if not to_addr:
            return 0.0, "Failure: Email recipient is empty."
        if not subject and not body:
            return 0.0, "Failure: Email subject and body are both empty."

        score = 0.0
        checks = []

        is_kevin = KEVIN_EMAIL.lower() in to_addr.lower() or "kevin" in to_addr.lower()
        if is_kevin:
            score += 0.4
            checks.append("recipient=OK")
        else:
            checks.append(f"recipient=WRONG({to_addr})")

        has_ai_subject = any(kw in subject.lower() for kw in ["ai", "artificial intelligence", "人工智能"])
        if has_ai_subject:
            score += 0.3
            checks.append("subject=OK")
        else:
            checks.append(f"subject=MISSING_AI({subject})")

        has_body_content = len(body) > 20
        if has_body_content:
            score += 0.3
            checks.append("body=OK")
        else:
            checks.append("body=TOO_SHORT")

        reason = f"Email sent. To: {to_addr}. Subject: {subject}. Checks: {', '.join(checks)}. Score: {score:.1f}"
        logger.info(f"[Eval] {reason}")
        return score, reason

    def tear_down(self, controller: AndroidController) -> bool:
        super().tear_down(controller)
        return True

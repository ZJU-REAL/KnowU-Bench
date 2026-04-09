"""Preference task: search recent top info and email Kevin based on user profile."""

from loguru import logger

from mobile_world.runtime.app_helpers.mail import get_sent_email_info
from mobile_world.runtime.app_helpers.system import enable_auto_time_sync, reset_chrome
from mobile_world.runtime.controller import AndroidController
from mobile_world.tasks.definitions.preference.base_prefrence_task import BasePrefrenceTask

NEWS_WORKFLOW_APPS = ("Chrome", "Mail")


class SearchTopInfoPreferenceAskUserTask(BasePrefrenceTask):
    """
    Search recent information in the user's interested field and send email.
    Scoring = base email check + preference judge.
    """

    task_tags = {"agent-user-interaction", "preference", "hybrid-eval", "hard"}

    KEVIN_EMAIL = "kevin@example.com"
    GOAL_REQUEST = (
        "Search for the recent news in the field I am interested, "
        f"and send an email to Kevin with a subject line that includes the field name "
        "and the following message:\n"
        "Here is the recent news in the [field name] field:\n"
        "[One sentence summary of the recent news you found]"
    )
    snapshot_tag = "init_state"
    DEFAULT_PROFILE_PATH = "src/mobile_world/user_profile/user.yaml"

    app_names = {"Chrome", "Mail"}

    @property
    def goal(self) -> str:
        return f"{self._build_user_logs_section()}\n\n### USER INSTRUCTION\n{self.GOAL_REQUEST}"

    def _get_interest_field_hint(self) -> str:
        """Read the preferred field from profile for judge hints."""
        prefs = self.user_profile.get("preferences", {}) or {}
        hobby = prefs.get("hobby", {}) or {}
        field = hobby.get("field_of_interest")
        if isinstance(field, str) and field.strip():
            return field.strip()
        return "unknown"

    def initialize_task_hook(self, controller: AndroidController) -> bool:
        """Reset Chrome and provide persona context for ask-user."""
        try:
            if not enable_auto_time_sync(controller):
                return False

            reset_chrome(controller)

            self.relevant_information = self._build_relevant_information(
                current_context=(
                    "The assistant will search recent news in your field of interest and send an email to Kevin. "
                    f"Kevin's email address is {self.KEVIN_EMAIL}."
                ),
                task_specific_detail=f"Task fact: Kevin's email address is {self.KEVIN_EMAIL}.",
                extra_instruction=(
                    "If the assistant asks about your interested field, communication preference, "
                    "or Kevin's email, answer based on the persona, logs, and task fact above."
                ),
            )

            return True
        except Exception as exc:
            logger.error(f"Initialize preference search task failed: {exc}")
            return False

    def is_successful(self, controller: AndroidController) -> float | tuple[float, str]:
        """Hybrid scoring: base email check + preference judge."""
        self._check_is_initialized()

        logger.info("Checking for sent email...")
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

        base_score = 1
        logger.info(f"[Eval Phase 1] Email sent. Base score: {base_score}")

        chat_history = getattr(controller, "user_agent_chat_history", [])
        chat_tail = chat_history[-10:] if isinstance(chat_history, list) else []
        interest_field_hint = self._get_interest_field_hint()

        rubric = (
            "Evaluate the final email result against the user's persona on four dimensions:\n\n"
            "1. Recipient Correctness (25%):\n"
            f"   - Task fact is authoritative: Kevin's email is {self.KEVIN_EMAIL}.\n"
            f"   - If recipient equals {self.KEVIN_EMAIL}, assign 1.0 and do NOT penalize because "
            "persona/social graph may omit Kevin.\n"
            "   - 0.0 only when recipient is clearly not Kevin.\n\n"
            "2. Content Structure Compliance (25%):\n"
            "   - Subject includes the target field name.\n"
            "   - Body includes: 'Here is the recent news in the [field name] field:' followed by "
            "a one-sentence summary.\n"
            "   - 1.0: fully compliant; 0.5: partially compliant; 0.0: major missing parts.\n\n"
            "3. Preference Alignment (30%):\n"
            "   - Is the selected field aligned with preferences.hobby.field_of_interest and user logs?\n"
            "   - Is the summary topic plausibly relevant and recent for that field?\n"
            "   - 1.0: strong alignment; 0.5: partly aligned; 0.0: unrelated field/content.\n\n"
            "4. App/Workflow Preference (20%):\n"
            "   - Expected workflow apps: Chrome for search and Mail for sending.\n"
            "   - IMPORTANT short-term policy: no explicit app trajectory is provided here.\n"
            "   - If there is no direct evidence about Chrome usage, treat this dimension as N/A and "
            "assign 1.0 (do NOT penalize for missing evidence).\n"
            "   - Only reduce score when provided evidence clearly shows workflow/app preference conflict.\n\n"
            "Final weighted score = 0.25 * recipient + 0.25 * structure + "
            "0.3 * preference_alignment + 0.2 * app_workflow."
        )
        user_agent_score, judge_reasoning = self.query_user_agent_judge(
            eval_data={
                "app_used": "Mail",
                "expected_workflow_apps": list(NEWS_WORKFLOW_APPS),
                "required_recipient": self.KEVIN_EMAIL,
                "interest_field_hint": interest_field_hint,
                "user_agent_chat_history_tail": chat_tail,
                "workflow_evidence_policy": "No explicit app trajectory is provided. Do not penalize missing Chrome evidence.",
                **email,
            },
            rubric=rubric,
        )

        final_score = 0.4 * base_score + (0.6 * user_agent_score)

        final_reason = (
            f"Email sent (+{0.4 * base_score:.1f}). "
            f"Preference judge: {user_agent_score:.2f} (+{0.6 * user_agent_score:.2f}). "
            f"To: {to_addr}. Subject: {subject}. "
            f"Judge reasoning: {judge_reasoning}"
        )

        return final_score, final_reason

    def tear_down(self, controller: AndroidController) -> bool:
        super().tear_down(controller)
        return True
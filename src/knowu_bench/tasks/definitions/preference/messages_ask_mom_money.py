"""Preference task: ask Mom for living expenses via SMS with Gen-Z style."""

from typing import Any

from loguru import logger

from knowu_bench.runtime.app_helpers.system import check_sms_via_adb, get_sent_sms_body_via_adb
from knowu_bench.runtime.controller import AndroidController
from knowu_bench.runtime.setup.contacts import ContactsSetup
from knowu_bench.tasks.definitions.preference.base_prefrence_task import BasePrefrenceTask


class MessagesAskMomForMoneyTask(BasePrefrenceTask):
    """
    Send Mom a text asking for money, using the user's social communication
    style (Gen-Z slang, cute emoji, Doge face).  Agent must NEVER initiate
    a voice or video call.
    Scoring = SMS sent check + style/tone judge.
    """

    task_tags = {"agent-user-interaction", "preference", "hybrid-eval", "easy"}
    supported_profiles = {"student"}

    GOAL_REQUEST = "这个月生活费见底了，找老妈要点钱。"
    snapshot_tag = "init_state"
    DEFAULT_PROFILE_PATH = "src/knowu_bench/user_profile/student.yaml"

    app_names = {"Messages"}

    def _get_mom_info(self) -> dict[str, Any]:
        """Resolve Mom's contact from social_graph."""
        graph = self.user_profile.get("social_graph", {}) or {}
        for group_key in ("financial", "high_priority", "personal"):
            contacts = graph.get(group_key, [])
            if isinstance(contacts, list):
                for c in contacts:
                    name = (c.get("name") or "").lower()
                    role = (c.get("role") or "").lower()
                    if "mom" in name or "mom" in role or "atm" in role:
                        return c
        return {"name": "Mom", "phone": "+8613800001111"}

    def _get_social_preferences(self) -> dict[str, Any]:
        prefs = self.user_profile.get("preferences", {}) or {}
        return prefs.get("social", {}) or {}

    def initialize_task_hook(self, controller: AndroidController) -> bool:
        mom = self._get_mom_info()
        social = self._get_social_preferences()

        tone = social.get("tone", "casual")
        emoji_usage = social.get("emoji_usage", "moderate")
        text_habits = social.get("text_habits", [])
        forbidden = social.get("forbidden", "")

        if isinstance(text_habits, list):
            habits_text = "; ".join(text_habits[:4]) if text_habits else "no specific habit"
        else:
            habits_text = str(text_habits)

        self._mom_phone = mom.get("phone", "+8613800001111")
        self._mom_name = mom.get("name", "Mom")

        ContactsSetup(controller).setup({
            "list": [{"name": self._mom_name, "phone": self._mom_phone}]
        })

        self.relevant_information = self._build_relevant_information(
            current_context=(
                f"You are running out of money this month and want to text {self._mom_name} "
                "to ask for some living expenses. "
                "You prefer to send an SMS message, NOT make a phone call."
            ),
            task_specific_detail=(
                f"Target contact: {self._mom_name} ({self._mom_phone})\n"
                f"- App preference for Mom: Messages (SMS)\n"
                f"- Social tone: {tone}\n"
                f"- Emoji usage: {emoji_usage}\n"
                f"- Text habits: {habits_text}\n"
                f"- Forbidden: {forbidden}\n"
                "IMPORTANT: NEVER make a voice call or video call. Text only."
            ),
            extra_instruction=(
                "If the assistant drafts a message for confirmation, approve it as long as "
                "it uses your casual style with emoji/slang. Reject overly formal drafts. "
                "If the assistant suggests calling, firmly refuse and insist on texting."
            ),
        )
        return True

    def is_successful(self, controller: AndroidController) -> tuple[float, str]:
        self._check_is_initialized()

        mom_phone = getattr(self, "_mom_phone", "+8613800001111")
        phone_clean = mom_phone.replace("+86", "").replace("-", "").replace(" ", "")

        sms_found = check_sms_via_adb(controller, phone_clean, [""])
        if not sms_found:
            sms_found = check_sms_via_adb(controller, mom_phone, [""])

        if not sms_found:
            return 0.0, f"Failure: No SMS sent to Mom ({mom_phone})."

        sms_body = get_sent_sms_body_via_adb(controller, phone_clean)
        if not sms_body:
            sms_body = get_sent_sms_body_via_adb(controller, mom_phone)
        logger.info(f"[Eval] Retrieved SMS body: {sms_body}")

        base_score = 0.4
        logger.info(f"[Eval Phase 1] SMS sent to Mom. Base score: {base_score}")

        social = self._get_social_preferences()
        rubric = (
            "Evaluate the SMS sent to Mom asking for money.\n"
            f"User social preferences: {social}\n"
            "Criteria:\n"
            "- Message should use casual / Gen-Z tone (slang, abbreviations).\n"
            "- Should include cute emoji or Doge-style emoticons to soften the request.\n"
            "- Must NOT be formal ('Dear Mom', 'Sincerely', etc.).\n"
            "- Agent must NOT have initiated a voice/video call.\n"
            "- The request should be endearing/playful, matching the user's personality.\n"
            "1.0 = perfect Gen-Z style with emoji, 0.0 = formal or call was made."
        )
        judge_score, judge_reason = self.query_user_agent_judge(
            eval_data={
                "action": "sms_sent",
                "recipient": getattr(self, "_mom_name", "Mom"),
                "phone": mom_phone,
                "sms_body": sms_body or "(unable to retrieve message text)",
                "social_prefs": social,
            },
            rubric=rubric,
            chat_history=controller.user_agent_chat_history,
        )

        final_score = base_score + 0.6 * judge_score
        reason = (
            f"SMS sent to Mom (+0.4). "
            f"Style judge: {judge_score:.2f} (+{0.6 * judge_score:.2f}). "
            f"Judge reason: {judge_reason}"
        )
        return final_score, reason

    def tear_down(self, controller: AndroidController) -> bool:
        super().tear_down(controller)
        return True

"""Preference task: send a sick-day / leave notice via Mattermost matching user's communication style."""

import json
import time

from loguru import logger

from mobile_world.runtime.app_helpers import mattermost
from mobile_world.runtime.app_helpers.mattermost import (
    get_latest_user_post_detail_after,
    start_mattermost_backend,
    stop_mattermost_backend,
)
from mobile_world.runtime.controller import AndroidController
from mobile_world.tasks.definitions.preference.base_prefrence_task import BasePrefrenceTask


class MattermostLeaveNoticeTask(BasePrefrenceTask):
    """
    Notify the team about taking a sick day via Mattermost.
    Agent must send the message in the correct channel/to the correct person
    using a tone that precisely matches the user's social communication style
    (Gen-Z casual for student, bullet-point Markdown for developer, concise
    and direct for professor).
    Scoring = message sent check + LLM style-match judge.
    """

    task_tags = {
        "agent-user-interaction",
        "preference",
        "social",
        "hybrid-eval",
        "hard",
    }
    supported_profiles = {"user", "developer", "student"}

    GOAL_REQUEST = "我今天身体不舒服，帮我跟组里说一声请个假。"
    snapshot_tag = "init_state"
    DEFAULT_PROFILE_PATH = "src/mobile_world/user_profile/user.yaml"

    app_names = {"Mattermost"}

    def _get_social_preferences(self) -> dict:
        prefs = self.user_profile.get("preferences", {}) or {}
        return prefs.get("social", {}) or {}

    def _get_app_preferences(self) -> dict:
        prefs = self.user_profile.get("preferences", {}) or {}
        return prefs.get("apps", {}) or {}

    def initialize_task_hook(self, controller: AndroidController) -> bool:
        self._init_timestamp = int(time.time()) * 1000

        if not start_mattermost_backend():
            logger.error("Failed to start Mattermost backend.")
            return False

        social_pref = self._get_social_preferences()
        app_pref = self._get_app_preferences()
        social_graph = self.user_profile.get("social_graph", {}) or {}

        social_detail = json.dumps(social_pref, indent=2, ensure_ascii=False) if social_pref else "N/A"
        app_detail = json.dumps(app_pref, indent=2, ensure_ascii=False) if app_pref else "N/A"

        self.relevant_information = self._build_relevant_information(
            current_context=(
                "You are feeling sick today and cannot go to work/school. "
                "You need the assistant to send a leave notice to your team via Mattermost. "
                "The message style should match how you normally communicate."
            ),
            task_specific_detail=(
                f"My social/communication preferences:\n{social_detail}\n\n"
                f"My app preferences:\n{app_detail}\n\n"
                f"My social graph (key contacts): {json.dumps(social_graph, indent=2, ensure_ascii=False)}"
            ),
            extra_instruction=(
                "If the assistant asks about the channel or recipient, answer based on "
                "your team communication habits (e.g. which Mattermost channel your team uses). "
                "If asked about the message tone, align with your social preference."
            ),
        )
        return True

    def is_successful(self, controller: AndroidController) -> tuple[float, str]:
        self._check_is_initialized()

        score = 0.0
        reasons: list[str] = []

        if not mattermost.is_mattermost_healthy():
            start_mattermost_backend()

        try:
            post_detail = get_latest_user_post_detail_after(self._init_timestamp)
        except Exception as exc:
            logger.error(f"Mattermost post query failed: {exc}")
            post_detail = None

        if post_detail:
            score += 0.4
            reasons.append("Mattermost leave notice message sent")
        else:
            reasons.append("No Mattermost message found after task init")
            return 0.0, "; ".join(reasons)

        post_message = post_detail.get("message", "")
        channel_name = post_detail.get("channel_name", "unknown")
        channel_display = post_detail.get("channel_display_name", "unknown")

        social_pref = self._get_social_preferences()
        identity = self.user_profile.get("identity", {}) or {}
        occupation = identity.get("occupation", "unknown")

        rubric = (
            "Evaluate whether the sick-day leave notice matches the user's "
            "communication style and is sent to the appropriate channel/person.\n\n"
            f"Message was sent to channel: #{channel_name} ({channel_display})\n\n"
            "1. Message Tone & Style (30%):\n"
            "   - Does the message tone match the user's social communication preference?\n"
            "   1.0 = perfect tone match, 0.0 = completely wrong tone.\n\n"
            "2. Recipient / Channel (50%):\n"
            "   - Was the message sent to the correct team channel or person "
            "based on the user's social graph and work context?\n"
            "   1.0 = correct recipient, 0.0 = wrong.\n\n"
            "3. Content Completeness (20%):\n"
            "   - Does the message include the reason for leave and the expected duration/time off?\n"
            "   1.0 = both reason and time mentioned, 0.5 = only one of them, 0.0 = neither."
        )

        judge_score, judge_reason = self.query_user_agent_judge(
            eval_data={
                "mattermost_message": post_message,
                "sent_to_channel": f"#{channel_name} ({channel_display})",
                "occupation": occupation,
                "social_preferences": social_pref,
            },
            rubric=rubric,
            chat_history=controller.user_agent_chat_history,
        )

        score += 0.6 * judge_score
        reasons.append(f"Style judge: {judge_score:.2f} (+{0.6 * judge_score:.2f})")
        reasons.append(f"Judge reason: {judge_reason}")

        return score, "; ".join(reasons)

    def tear_down(self, controller: AndroidController) -> bool:
        super().tear_down(controller)
        try:
            stop_mattermost_backend()
        except Exception as exc:
            logger.error(f"Failed to stop Mattermost backend: {exc}")
        return True

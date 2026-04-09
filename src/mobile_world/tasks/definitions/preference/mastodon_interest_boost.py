"""Preference task: forward interesting Mastodon posts to the Mattermost group chat."""

import json
import re
import time

from loguru import logger

from mobile_world.runtime.app_helpers import mastodon, mattermost
from mobile_world.runtime.app_helpers.mastodon import (
    start_mastodon_backend,
    stop_mastodon_backend,
)
from mobile_world.runtime.app_helpers.mattermost import (
    get_latest_user_post_detail_after,
    start_mattermost_backend,
    stop_mattermost_backend,
)
from mobile_world.runtime.controller import AndroidController
from mobile_world.tasks.definitions.preference.base_prefrence_task import BasePrefrenceTask


class MastodonInterestBoostTask(BasePrefrenceTask):
    """
    Browse the Mastodon timeline, find posts that match the user's interests,
    and forward them to the appropriate Mattermost group chat.
    Agent must infer interest domains from the user persona and pick the
    correct Mattermost channel based on social graph / team context.
    Scoring = message-forwarded check + LLM interest & channel match judge.
    """

    task_tags = {
        "agent-user-interaction",
        "preference",
        "hybrid-eval",
        "hard",
    }
    supported_profiles = {"user", "student"}

    GOAL_REQUEST = "Check my Mastodon timeline for a post that matches my interests and forward it to the corresponding group chat on Mattermost."
    snapshot_tag = "init_state"
    DEFAULT_PROFILE_PATH = "src/mobile_world/user_profile/user.yaml"

    app_names = {"Mastodon", "Mattermost"}

    def _get_social_preferences(self) -> dict:
        prefs = self.user_profile.get("preferences", {}) or {}
        return prefs.get("social", {}) or {}

    def _get_app_preferences(self) -> dict:
        prefs = self.user_profile.get("preferences", {}) or {}
        return prefs.get("apps", {}) or {}

    def initialize_task_hook(self, controller: AndroidController) -> bool:
        self._init_timestamp = int(time.time()) * 1000  # Mattermost createat is ms

        if not start_mastodon_backend():
            logger.error("Failed to start Mastodon backend.")
            return False

        if not start_mattermost_backend():
            logger.error("Failed to start Mattermost backend.")
            return False

        social_pref = self._get_social_preferences()
        app_pref = self._get_app_preferences()
        identity = self.user_profile.get("identity", {}) or {}

        self.relevant_information = self._build_relevant_information(
            current_context=(
                "You want the assistant to browse your Mastodon timeline, "
                "find posts that match your personal interests, and forward "
                "them to the appropriate group chat on Mattermost."
            ),
            task_specific_detail=(
                f"My identity: {json.dumps(identity, indent=2, ensure_ascii=False)}\n\n"
                f"My social preferences: {json.dumps(social_pref, indent=2, ensure_ascii=False)}\n\n"
                f"My app preferences (relevant news/interests): "
                f"{json.dumps(app_pref.get('news_and_papers', []), indent=2, ensure_ascii=False)}"
            ),
            extra_instruction=(
                "If the assistant asks what topics you are interested in, answer based "
                "on your persona's interests and active social media topics. "
                "Do not accept content outside your interest domain. "
                "If the assistant asks which Mattermost channel to use, guide them "
                "to the appropriate team or topic channel based on your social graph."
            ),
        )
        return True

    def is_successful(self, controller: AndroidController) -> tuple[float, str]:
        self._check_is_initialized()

        if not mastodon.is_mastodon_healthy():
            if not mastodon.start_mastodon_backend():
                return 0.0, "Mastodon backend is unhealthy and restart failed."

        if not mattermost.is_mattermost_healthy():
            if not mattermost.start_mattermost_backend():
                return 0.0, "Mattermost backend is unhealthy and restart failed."

        try:
            post_detail = get_latest_user_post_detail_after(self._init_timestamp)
        except Exception as exc:
            logger.error(f"Mattermost post query failed: {exc}")
            post_detail = None

        if not post_detail:
            return 0.0, "No message found on Mattermost after task init."

        score = 0.3
        reasons = ["Message forwarded to Mattermost (+0.3)"]

        post_message = post_detail.get("message", "")
        channel_name = post_detail.get("channel_name", "unknown")
        channel_display = post_detail.get("channel_display_name", "unknown")

        mastodon_content = ""
        url_match = re.search(r"https?://[^/]+/@\w+/(\d+)", post_message)
        if url_match:
            status_id = int(url_match.group(1))
            toot = mastodon.get_toot_by_status_id(status_id)
            if toot:
                mastodon_content = toot.get("text", "") or toot.get("content", "")
                logger.info(f"Resolved Mastodon post {status_id}: {mastodon_content[:200]}")
            else:
                logger.warning(f"Could not fetch Mastodon toot for status_id={status_id}")

        identity = self.user_profile.get("identity", {}) or {}
        social_pref = self._get_social_preferences()
        occupation = identity.get("occupation", "unknown")
        social_graph = self.user_profile.get("social_graph", {}) or {}

        rubric = (
            "Evaluate whether the agent successfully forwarded interesting Mastodon "
            "content to the correct Mattermost group chat.\n\n"
            f"User occupation: {occupation}\n"
            f"User social preferences: {json.dumps(social_pref.get('social_media', {}), ensure_ascii=False)}\n"
            f"User social graph: {json.dumps(social_graph, ensure_ascii=False)}\n"
            f"Message was sent to Mattermost channel: #{channel_name} ({channel_display})\n"
            f"Original Mastodon post content: {mastodon_content or '(not resolved)'}\n\n"
            "Criteria:\n"
            "1. Interest Match (50%):\n"
            "   - Given the user's occupation, hobbies, and social media preferences, "
            "does the forwarded content align with topics they would genuinely care about?\n"
            "   1.0 = strongly matches user's interest profile, "
            "0.5 = partially relevant, 0.0 = completely irrelevant.\n\n"
            "2. Correct Channel (50%):\n"
            "   - Given the user's social graph and team structure, was the message "
            "sent to a reasonable Mattermost channel?\n"
            "   1.0 = correct channel, 0.5 = acceptable but not ideal, 0.0 = wrong channel."
        )

        judge_score, judge_reason = self.query_user_agent_judge(
            eval_data={
                "forwarded_message": post_message,
                "mastodon_post_content": mastodon_content or "(could not resolve)",
                "mattermost_channel": f"#{channel_name} ({channel_display})",
                "occupation": occupation,
                "social_preferences": social_pref,
                "social_graph": social_graph,
            },
            rubric=rubric,
            chat_history=controller.user_agent_chat_history,
        )

        score += 0.7 * judge_score
        reasons.append(f"Content & channel judge: {judge_score:.2f} (+{0.7 * judge_score:.2f})")
        reasons.append(f"Judge reason: {judge_reason}")

        return score, "; ".join(reasons)

    def tear_down(self, controller: AndroidController) -> bool:
        super().tear_down(controller)
        for name, stop_fn in [
            ("Mastodon", stop_mastodon_backend),
            ("Mattermost", stop_mattermost_backend),
        ]:
            try:
                stop_fn()
            except Exception as exc:
                logger.error(f"Failed to stop {name} backend: {exc}")
        return True

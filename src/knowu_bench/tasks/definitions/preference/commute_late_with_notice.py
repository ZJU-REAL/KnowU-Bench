"""Preference task: urgent route to destination + Mattermost late-arrival notice (dual-app, dual-preference)."""

import time
from typing import Any

from loguru import logger

from knowu_bench.runtime.app_helpers import mattermost
from knowu_bench.runtime.app_helpers.mattermost import (
    get_latest_user_post_after,
    start_mattermost_backend,
    stop_mattermost_backend,
)
from knowu_bench.runtime.controller import AndroidController
from knowu_bench.tasks.definitions.preference.base_prefrence_task import BasePrefrenceTask


class LateUrgentRouteWithNoticeTask(BasePrefrenceTask):
    """
    User is running late.  Agent must:
      1. Plan the fastest route to the destination via Maps (overriding budget habits if needed).
      2. Send a late-arrival notice on Mattermost in the user's communication style.
    Both the transport choice AND the message tone must match the user's profile.
    Scoring = Mattermost message check + LLM multi-dimension judge.
    """

    task_tags = {
        "agent-user-interaction",
        "preference",
        "cross-app",
        "hybrid-eval",
        "hard",
    }
    supported_profiles = {"user", "developer"}

    PROFILE_DESTINATIONS: dict[str, dict[str, str]] = {
        "user":      {"dest_key": "work", "start_key": "home", "dest_name": "学校",
                      "goal": "完了要迟到了！帮我看看最快怎么去学校——给个出行方案就行，不用导航。另外帮我在Mattermost上跟同事说一声我在路上了。"},
        "developer": {"dest_key": "work", "start_key": "home", "dest_name": "公司",
                      "goal": "Oh no, I'm running late! Help me figure out the fastest way to get to the office — just give me a travel plan, no need to navigate. Also, let my colleagues know on Mattermost that I'm on my way."},
    }

    GOAL_REQUEST = "Oh no, I'm running late! Help me figure out the fastest way to get to the office — just give me a travel plan, no need to navigate. Also, let my colleagues know on Mattermost that I'm on my way."
    snapshot_tag = "init_state"
    DEFAULT_PROFILE_PATH = "src/knowu_bench/user_profile/user.yaml"

    app_names = {"Maps", "Mattermost"}

    def _get_dest_config(self) -> dict[str, str]:
        pid = self._get_profile_id()
        return self.PROFILE_DESTINATIONS.get(pid, self.PROFILE_DESTINATIONS["user"])

    def _get_travel_preferences(self) -> dict[str, Any]:
        prefs = self.user_profile.get("preferences", {}) or {}
        return prefs.get("travel", {}) or {}

    def _get_social_preferences(self) -> dict:
        prefs = self.user_profile.get("preferences", {}) or {}
        return prefs.get("social", {}) or {}

    def initialize_task_hook(self, controller: AndroidController) -> bool:
        cfg = self._get_dest_config()
        start_key = cfg["start_key"]
        dest_key = cfg["dest_key"]

        self.GOAL_REQUEST = cfg["goal"]
        self._set_start_location(controller, start_key)
        self._init_timestamp = int(time.time()) * 1000

        if not start_mattermost_backend():
            logger.error("Failed to start Mattermost backend.")
            return False

        travel = self._get_travel_preferences()
        social = self._get_social_preferences()
        locations = self.user_profile.get("locations", {}) or {}
        start_loc = locations.get(start_key, {})
        dest_loc = locations.get(dest_key, {})

        start_label = start_loc.get("address", "unknown")
        dest_label = dest_loc.get("address", "unknown")

        self.relevant_information = self._build_relevant_information(
            current_context=(
                "You are running LATE! You need to get to your destination ASAP. "
                "You also need the assistant to notify your team on Mattermost that "
                "you are on your way. "
                f"Origin: {start_label}. "
                f"Destination: {dest_label}."
            ),
            task_specific_detail=(
                f"Travel preferences: {travel}\n\n"
                f"Social/communication preferences: {social}\n\n"
                "IMPORTANT: I am running late — speed is the top priority for the route. "
                "The Mattermost message should still match my usual communication style."
            ),
            extra_instruction=(
                "If the assistant asks about transport, emphasise urgency — accept faster "
                "options even if you normally take cheaper ones. "
                "If asked about the message style, reply according to your social preference. "
                "Both tasks (route + notification) must be completed."
            ),
        )

        self._start_loc = start_loc
        self._dest_loc = dest_loc
        return True

    _LATE_KEYWORDS = [
        "late", "on my way", "omw", "coming", "delayed",
    ]

    def is_successful(self, controller: AndroidController) -> tuple[float, str]:
        self._check_is_initialized()

        score = 0.0
        reasons: list[str] = []

        if not mattermost.is_mattermost_healthy():
            start_mattermost_backend()

        try:
            post = get_latest_user_post_after(self._init_timestamp)
        except Exception as exc:
            logger.error(f"Mattermost post query failed: {exc}")
            post = None

        if post:
            post_lower = post.lower()
            if any(kw in post_lower for kw in self._LATE_KEYWORDS):
                score += 0.3
                reasons.append("Mattermost late-arrival notice with relevant keywords (+0.3)")
        else:
            reasons.append("No Mattermost message found after task init")

        identity = self.user_profile.get("identity", {}) or {}
        occupation = identity.get("occupation", "unknown")
        travel = self._get_travel_preferences()
        social = self._get_social_preferences()

        agent_plan = (controller.interaction_cache or "").strip()
        chat_history = getattr(controller, "user_agent_chat_history", None) or []

        dest_addr = self._dest_loc.get("address", "destination")

        rubric = (
            "Evaluate the agent's handling of this dual-task (route + notification) "
            "under urgency.\n\n"
            "1. Route / Transport Choice (40%):\n"
            f"   - Did the agent recommend the FASTEST route to {dest_addr}?\n"
            "   - Did it correctly override budget-saving defaults due to urgency?\n"
            "   - Evaluate based on the user's travel preferences provided below.\n"
            "   1.0 = urgency-aware fast route, 0.0 = slow/default route.\n\n"
            "2. Mattermost Message Style (35%):\n"
            "   - Does the late-arrival message match the user's communication style?\n"
            "   - Evaluate based on the user's social preferences provided below.\n"
            "   1.0 = perfect style match, 0.0 = wrong tone.\n\n"
            "3. Task Completeness (25%):\n"
            "   - Did the agent complete BOTH tasks (route planning AND notification)?\n"
            "   - Completing only one task: partial credit.\n"
            "   1.0 = both done, 0.5 = one done, 0.0 = neither."
        )

        judge_score, judge_reason = self.query_user_agent_judge(
            eval_data={
                "gui_agent_travel_plan": agent_plan,
                "occupation": occupation,
                "mattermost_message": post,
                "travel_prefs": travel,
                "social_prefs": social,
                "origin": self._start_loc,
                "destination": self._dest_loc,
            },
            rubric=rubric,
            chat_history=chat_history if chat_history else None,
        )

        score += 0.7 * judge_score
        reasons.append(f"Multi-dimension judge: {judge_score:.2f} (+{0.7 * judge_score:.2f})")
        reasons.append(f"Judge reason: {judge_reason}")

        return score, "; ".join(reasons)

    def tear_down(self, controller: AndroidController) -> bool:
        super().tear_down(controller)
        try:
            stop_mattermost_backend()
        except Exception as exc:
            logger.error(f"Failed to stop Mattermost backend: {exc}")
        return True

"""Preference task: commute route planning under bad weather (rain)."""

from typing import Any

from loguru import logger

from mobile_world.runtime.controller import AndroidController
from mobile_world.tasks.definitions.preference.base_prefrence_task import BasePrefrenceTask


class CommuteRoutingBadWeatherTask(BasePrefrenceTask):
    """
    Plan a commute route when it is raining.
    Agent MUST override the user's default outdoor preferences (e.g. cycling)
    and recommend sheltered transport (taxi, metro, bus) while minimising
    outdoor walking time.
    Scoring = pure LLM judge on weather-aware route quality.
    """

    task_tags = {"agent-user-interaction", "preference", "easy"}
    supported_profiles = {"user", "developer", "student", "grandma"}

    PROFILE_DESTINATIONS: dict[str, dict[str, str]] = {
        "user":      {"dest_key": "work", "start_key": "home", "dest_name": "学校"},
        "developer": {"dest_key": "work", "start_key": "home", "dest_name": "公司"},
        "student":   {"dest_key": "work", "start_key": "home", "dest_name": "图书馆"},
        "grandma":   {"dest_key": "market", "start_key": "home", "dest_name": "菜市场买菜"},
    }

    GOAL_REQUEST = "外面在下雨，帮我规划一下去目的地的出行路线，给出出行方案就行。"
    snapshot_tag = "init_state"
    DEFAULT_PROFILE_PATH = "src/mobile_world/user_profile/user.yaml"

    app_names = {"Maps"}

    def _get_dest_config(self) -> dict[str, str]:
        pid = self._get_profile_id()
        return self.PROFILE_DESTINATIONS.get(pid, self.PROFILE_DESTINATIONS["user"])

    def _get_travel_preferences(self) -> dict[str, Any]:
        prefs = self.user_profile.get("preferences", {}) or {}
        return prefs.get("travel", {}) or {}

    def initialize_task_hook(self, controller: AndroidController) -> bool:
        cfg = self._get_dest_config()
        dest_name = cfg["dest_name"]
        dest_key = cfg["dest_key"]
        start_key = cfg["start_key"]

        self.GOAL_REQUEST = f"外面在下雨，帮我规划一下去{dest_name}的出行路线，给出出行方案就行。"
        self._set_start_location(controller, start_key)

        travel = self._get_travel_preferences()
        locations = self.user_profile.get("locations", {}) or {}
        start_loc = locations.get(start_key, {})
        dest_loc = locations.get(dest_key, {})

        start_label = start_loc.get("address", "unknown")
        dest_label = dest_loc.get("address", "unknown")

        self.relevant_information = self._build_relevant_information(
            current_context=(
                "It is currently RAINING outside. "
                f"You want to commute from {start_label} to {dest_label}. "
                f"Origin: {start_label}. "
                f"Destination: {dest_label}. "
                "You prefer to stay dry and minimise outdoor walking."
            ),
            task_specific_detail=f"Travel preferences: {travel}",
            extra_instruction=(
                "If the assistant asks about transport preference, remind them that "
                "it is raining and you want a sheltered option. "
                "Do NOT insist on biking or walking in the rain."
            ),
        )

        self._dest_loc = dest_loc
        self._start_loc = start_loc
        return True

    def is_successful(self, controller: AndroidController) -> tuple[float, str]:
        self._check_is_initialized()

        travel = self._get_travel_preferences()
        identity = self.user_profile.get("identity", {}) or {}
        occupation = identity.get("occupation", "unknown")

        agent_plan = (controller.interaction_cache or "").strip()
        chat_history = getattr(controller, "user_agent_chat_history", None) or []

        if not agent_plan:
            logger.warning("No travel plan or chat history from GUI agent.")
            return 0.0, "GUI agent did not provide any travel plan (no answer action and no conversation)."

        dest_addr = self._dest_loc.get("address", "destination")

        rubric = (
            "You are given the GUI agent's FINAL travel plan (or conversation) and the user's profile.\n"
            "Evaluate the recommendation under RAINY weather across the following dimensions.\n\n"
            f"User occupation: {occupation}\n"
            f"User normal travel preferences: {travel}\n"
            "Weather: RAINING.\n\n"
            "1. Weather Adaptation — Outdoor Exposure (40%):\n"
            "   - Does the plan avoid outdoor exposure (cycling, long walks in rain)?\n"
            "   - If the user's default transport is outdoor-heavy (e.g. bike/walk), "
            "did the agent override it for a sheltered option?\n"
            "   - Minimising walking distance to stops/stations is a plus.\n"
            "   1.0 = fully sheltered plan with minimal outdoor exposure, "
            "0.0 = recommends cycling/walking as if sunny.\n\n"
            "2. Travel Preference Alignment (25%):\n"
            "   - Within rain-safe options, does the recommendation still respect "
            "the user's stated travel preferences as much as possible?\n"
            "   - E.g. if the user prefers public transit over taxi on normal days, "
            "metro/bus is better than taxi when both are sheltered.\n"
            "   1.0 = best rain-safe option aligned with preferences, "
            "0.0 = ignores preferences entirely.\n\n"
            "3. Commute Time Efficiency (20%):\n"
            f"   - Is the recommended route reasonably time-efficient for getting to {dest_addr}?\n"
            "   - Does the plan avoid unnecessarily long detours?\n"
            "   1.0 = time-efficient route, 0.0 = unreasonably slow or no route provided.\n\n"
            "4. Economic Reasonableness (15%):\n"
            "   - Does the cost of the recommended transport match the user's "
            "economic profile (inferred from occupation and preferences)?\n"
            "   - Avoids over-spending (e.g. premium taxi for a budget-conscious user) "
            "or under-spending that sacrifices safety/comfort in rain.\n"
            "   1.0 = cost-appropriate, 0.0 = clearly mismatched spending."
        )

        judge_score, judge_reason = self.query_user_agent_judge(
            eval_data={
                "gui_agent_travel_plan": agent_plan,
                "weather": "raining",
                "occupation": occupation,
                "travel_prefs": travel,
                "origin": self._start_loc,
                "destination": self._dest_loc,
            },
            rubric=rubric,
            chat_history=chat_history if chat_history else None,
        )

        reason = (
            f"Route preference judge (rain): {judge_score:.2f}. "
            f"Occupation: {occupation}. Weather: raining. "
            f"Agent plan: {agent_plan[:120] if agent_plan else '(from chat history)'}. "
            f"Judge reason: {judge_reason}"
        )
        return judge_score, reason

    def tear_down(self, controller: AndroidController) -> bool:
        super().tear_down(controller)
        return True

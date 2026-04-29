"""Preference task: commute route planning on a sunny day."""

from typing import Any

from loguru import logger

from knowu_bench.runtime.controller import AndroidController
from knowu_bench.tasks.definitions.preference.base_prefrence_task import BasePrefrenceTask


class CommuteRoutingSunnyTask(BasePrefrenceTask):
    """
    Plan a commute route under good weather.
    Agent should recommend a transport mode that best fits the user's persona
    (student -> budget-friendly transit/bike, developer -> fastest, grandma -> least walking).
    Scoring = pure LLM judge on route appropriateness.
    """

    task_tags = {"agent-user-interaction", "preference", "pure-judge-eval", "easy"}
    supported_profiles = {"user", "developer", "student", "grandma"}

    PROFILE_DESTINATIONS: dict[str, dict[str, str]] = {
        "user":      {"dest_key": "work", "start_key": "home", "dest_name": "学校"},
        "developer": {"dest_key": "work", "start_key": "home", "dest_name": "公司"},
        "student":   {"dest_key": "work", "start_key": "home", "dest_name": "图书馆"},
        "grandma":   {"dest_key": "work", "start_key": "home", "dest_name": "地坛公园"},
    }

    GOAL_REQUEST = "帮我规划一下去目的地的出行路线，给出出行方案就行。"
    snapshot_tag = "init_state"
    DEFAULT_PROFILE_PATH = "src/knowu_bench/user_profile/user.yaml"

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

        self.GOAL_REQUEST = f"帮我规划一下去{dest_name}的出行路线，给出出行方案就行。"
        self._set_start_location(controller, start_key)

        travel = self._get_travel_preferences()
        locations = self.user_profile.get("locations", {}) or {}
        start_loc = locations.get(start_key, {})
        dest_loc = locations.get(dest_key, {})

        start_label = start_loc.get("address", "unknown")
        dest_label = dest_loc.get("address", "unknown")

        self.relevant_information = self._build_relevant_information(
            current_context=(
                "It is a sunny day with good weather. "
                f"You want to commute from {start_label} to {dest_label}. "
                f"Origin: {start_label}. "
                f"Destination: {dest_label}."
            ),
            task_specific_detail=f"Travel preferences: {travel}",
            extra_instruction=(
                "If asked about preferred transport mode, answer based on "
                "your travel preferences above. Today's weather is fine."
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
            "Evaluate the recommendation under SUNNY / good weather across the following dimensions.\n\n"
            f"User occupation: {occupation}\n"
            f"User travel preferences: {travel}\n"
            "Weather: sunny / good.\n\n"
            "1. Travel Preference Alignment (40%):\n"
            "   - Does the recommended transport mode match the user's stated "
            "daily transport and travel preferences?\n"
            "   - Since the weather is good, outdoor options (cycling, walking) "
            "are fully acceptable if they align with the user's preferences.\n"
            "   1.0 = closely matches stated preferences, "
            "0.0 = completely ignores preferences.\n\n"
            "2. Route Correctness (25%):\n"
            f"   - Does the route go from the origin to {dest_addr}?\n"
            "   - Is the route geographically sensible without unnecessary detours?\n"
            "   1.0 = correct origin-destination with a reasonable path, "
            "0.0 = wrong destination or no route provided.\n\n"
            "3. Commute Time Efficiency (20%):\n"
            "   - Is the recommended route reasonably time-efficient for getting to the destination?\n"
            "   - Does it leverage the good weather to pick the most practical option "
            "(e.g. biking may be faster than bus for short distances)?\n"
            "   1.0 = time-efficient route, 0.0 = unreasonably slow.\n\n"
            "4. Economic Reasonableness (15%):\n"
            "   - Does the cost of the recommended transport match the user's "
            "economic profile (inferred from occupation and preferences)?\n"
            "   - Avoids over-spending (e.g. taxi when user prefers budget transit) "
            "or under-serving (e.g. long walk when user values convenience).\n"
            "   1.0 = cost-appropriate, 0.0 = clearly mismatched spending."
        )

        judge_score, judge_reason = self.query_user_agent_judge(
            eval_data={
                "gui_agent_travel_plan": agent_plan,
                "weather": "sunny",
                "occupation": occupation,
                "travel_prefs": travel,
                "origin": self._start_loc,
                "destination": self._dest_loc,
            },
            rubric=rubric,
            chat_history=chat_history if chat_history else None,
        )

        reason = (
            f"Route preference judge: {judge_score:.2f}. "
            f"Occupation: {occupation}. Weather: sunny. "
            f"Agent plan: {agent_plan[:120] if agent_plan else '(from chat history)'}. "
            f"Judge reason: {judge_reason}"
        )
        return judge_score, reason

    def tear_down(self, controller: AndroidController) -> bool:
        super().tear_down(controller)
        return True

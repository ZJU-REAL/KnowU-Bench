"""Preference task: late-night commute home after overtime work."""

from typing import Any

from loguru import logger

from mobile_world.runtime.controller import AndroidController
from mobile_world.tasks.definitions.preference.base_prefrence_task import BasePrefrenceTask


class LateNightCommuteTask(BasePrefrenceTask):
    """
    Plan a commute home late at night after working overtime.
    Agent must recognise that public transit (bus, metro, shared bike) is
    likely unavailable or unsafe at this hour and recommend appropriate
    alternatives while respecting the user's budget profile.
    Scoring = pure LLM judge on time-awareness and transport suitability.
    """

    task_tags = {
        "agent-user-interaction",
        "preference",
        "hybrid-eval",
        "easy",
    }
    supported_profiles = {"user", "developer", "student"}

    PROFILE_DESTINATIONS: dict[str, dict[str, str]] = {
        "user":      {"start_key": "work", "dest_key": "home",
                      "goal": "加班到现在都十一点半了，好累，帮我看看怎么回家，给出出行方案就行。",
                      "origin_desc": "work"},
        "developer": {"start_key": "work", "dest_key": "home",
                      "goal": "It's already 11:30 PM, been working overtime forever. Help me figure out how to get home — just give me a travel plan.",
                      "origin_desc": "work"},
        "student":   {"start_key": "work", "dest_key": "home",
                      "goal": "在图书馆学到十一点半了，太晚了，帮我看看怎么回宿舍，给出出行方案就行。",
                      "origin_desc": "library"},
    }

    GOAL_REQUEST = "加班到现在都十一点半了，好累，帮我看看怎么回家，给出出行方案就行。"
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
        start_key = cfg["start_key"]
        dest_key = cfg["dest_key"]

        self.GOAL_REQUEST = cfg["goal"]
        self._set_start_location(controller, start_key)

        travel = self._get_travel_preferences()
        locations = self.user_profile.get("locations", {}) or {}
        start_loc = locations.get(start_key, {})
        dest_loc = locations.get(dest_key, {})

        start_label = start_loc.get("address", "unknown")
        dest_label = dest_loc.get("address", "unknown")

        self.relevant_information = self._build_relevant_information(
            current_context=(
                "It is 23:30 (11:30 PM). "
                "You have been working overtime and are exhausted. "
                "Public transit (metro, bus) may have stopped or is about to stop running. "
                f"Current location: {start_label}. "
                f"Destination: {dest_label}."
            ),
            task_specific_detail=f"Travel preferences: {travel}",
            extra_instruction=(
                "If the assistant asks about transport preference, remind them "
                "that it is very late and you are tired. You want a safe and "
                "convenient way home. Accept taxi if that is the only option, "
                "but prefer the cheapest safe option if you are a student."
            ),
        )

        self._start_loc = start_loc
        self._dest_loc = dest_loc
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
            "Evaluate the recommendation under LATE-NIGHT conditions (23:30) across the following dimensions.\n\n"
            f"User occupation: {occupation}\n"
            f"User normal travel preferences: {travel}\n"
            "Time: 23:30 (11:30 PM). Metro/bus likely stopped or about to stop.\n\n"
            "1. Late-Night Constraint Awareness (40%):\n"
            "   - Does the agent recognise that public transit (metro, bus, shared bike) "
            "is unavailable or unsafe at 23:30?\n"
            "   - Does the plan avoid recommending these as the primary option?\n"
            "   - Is the recommended transport safe and realistic for late-night travel "
            "(e.g. taxi / ride-hailing)?\n"
            "   1.0 = correctly identifies late-night constraint and recommends a safe option, "
            "0.0 = recommends unavailable transit or unsafe option (e.g. cycling at night).\n\n"
            "2. Travel Preference Alignment (25%):\n"
            "   - Within late-night-safe options, does the specific ride-hailing tier or "
            "cost strategy match the user's economic profile and travel preferences?\n"
            "   - Budget-conscious users may prefer cheaper tiers or fare-splitting; "
            "users who prioritise speed or comfort may prefer premium services.\n"
            "   1.0 = ride-hailing tier closely matches stated preferences, "
            "0.0 = completely ignores economic profile.\n\n"
            "3. Route Correctness (20%):\n"
            f"   - Does the route go from the origin to {dest_addr}?\n"
            "   - Is the route geographically sensible without unnecessary detours?\n"
            "   1.0 = correct origin-destination with a reasonable path, "
            "0.0 = wrong destination or no route provided.\n\n"
            "4. Safety & Comfort (15%):\n"
            "   - Is the plan appropriate for a tired person travelling alone late at night?\n"
            "   - Does it consider factors like well-lit pick-up points, licensed services, "
            "or sharing trip info with contacts?\n"
            "   1.0 = thoughtful safety considerations, "
            "0.0 = no regard for late-night safety."
        )

        judge_score, judge_reason = self.query_user_agent_judge(
            eval_data={
                "gui_agent_travel_plan": agent_plan,
                "time_context": "23:30 (11:30 PM), late night after overtime",
                "public_transit_status": "likely stopped or about to stop",
                "occupation": occupation,
                "travel_prefs": travel,
                "origin": self._start_loc,
                "destination": self._dest_loc,
            },
            rubric=rubric,
            chat_history=chat_history if chat_history else None,
        )

        reason = (
            f"Late-night commute judge: {judge_score:.2f}. "
            f"Occupation: {occupation}. Time: 23:30. "
            f"Agent plan: {agent_plan[:120] if agent_plan else '(from chat history)'}. "
            f"Judge reason: {judge_reason}"
        )
        return judge_score, reason

    def tear_down(self, controller: AndroidController) -> bool:
        super().tear_down(controller)
        return True

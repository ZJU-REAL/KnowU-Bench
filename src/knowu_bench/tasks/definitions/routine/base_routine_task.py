import os
import re
from typing import Any

from loguru import logger

from knowu_bench.runtime.utils.loader import UserProfileLoader
from knowu_bench.runtime.utils.prompt_builder import PersonaPromptBuilder
from knowu_bench.runtime.utils.user_log_context import build_user_log_context
from knowu_bench.tasks.base import BaseTask


class BaseRoutineTask(BaseTask):
    """Reusable base for routine tasks with aligned prompt structure."""

    DEFAULT_PROFILE_PATH = "src/knowu_bench/user_profile/user.yaml"
    SAFE_ACTIONS = {"terminate", "wait", "ask_user", "answer", "finished"}
    GOAL_INSTRUCTION = (
        "Review the provided 'User Activity Logs' and the current 'System Environment'. "
        "Based on this context, identify if a task needs to be performed and determine the appropriate engagement strategy:\n\n"
        "1. Interactive Execution: For certain types of tasks, you should first consult the user or propose a suggestion. "
        "Only proceed with execution after receiving user feedback or confirmation.\n"
        "2. Autonomous Execution: For other types of tasks, you should complete the execution directly in the background "
        "without interrupting or disturbing the user.\n"
        "3. Otherwise, finish the current task and revert to background monitoring mode."
        "Use your judgment to decide which strategy best fits the current situation."
    )

    def __init__(self, params: dict[str, Any] | None = None):
        super().__init__(params)
        self.params = params or {}
        self.profile_path = self.params.get("profile_path") or self.DEFAULT_PROFILE_PATH
        self.user_profile: dict[str, Any] = {}
        self.persona_text = ""
        self.user_log_context = "- (No logs available)"
        self.expectation = {"should_act": False, "actions": []}
        self._goal = ""
        self._load_user_context()

    def _load_user_context(self) -> None:
        if not os.path.exists(self.profile_path):
            logger.warning(f"Profile file not found: {self.profile_path}")
            return
        try:
            loader = UserProfileLoader(self.profile_path)
            self.user_profile = loader.user_profile
            self.persona_text = PersonaPromptBuilder(self.user_profile).build_system_prompt()
            self.user_log_context = (
                build_user_log_context(
                    self.user_profile,
                    profile_path=self.profile_path,
                    query=self.GOAL_INSTRUCTION,
                    task_name=self.name,
                )
                or "- (No logs available)"
            )
        except Exception as exc:
            logger.error(f"Profile load failed: {exc}")
            self.user_profile = {}
            self.persona_text = ""
            self.user_log_context = "- (No logs available)"

    def _get_habit(self, habit_key: str) -> dict[str, Any]:
        return self.user_profile.get("habits", {}).get(habit_key, {}) or {}

    def _apply_habit_expectation(self, habit: dict[str, Any], action_key: str = "settings") -> None:
        if not habit:
            self.expectation = {"should_act": False, "actions": []}
            return
        action_settings = habit.get("action", {}).get(action_key, [])
        self.expectation = {"should_act": True, "actions": action_settings}

    def _build_goal(self, system_context: str = "", instruction: str | None = None) -> str:
        instruction_text = instruction or self.GOAL_INSTRUCTION
        system_context_block = f"{system_context}\n" if system_context else ""
        return (
            "### USER ACTIVITY LOGS (Historical Context)\n"
            "The following logs show the user's consistent behavior over the past few weeks:\n"
            f"{(self.user_log_context or '').strip() or '- (No logs available)'}\n\n"
            "System Status: Background Monitor Active.\n"
            f"{system_context_block}"
            "### INSTRUCTION\n"
            f"{instruction_text}"
        )

    def _build_relevant_information(
        self,
        current_context: str,
        routine_status: str = "",
        task_specific_detail: str = "",
    ) -> str:
        consistency = (
            "Base your decision primarily on your established routines, habits, and preferences. "
            "If the suggested action matches your routine, you should ACCEPT in most cases (~90%). "
            "If it does not match your routine, you should REJECT in most cases (~90%)."
        )
        think_text = (
            "Briefly analyze whether the suggestion matches your routine. "
            "Then state whether you follow that routine or deviate this time."
        )
        detail_block = f"{task_specific_detail}\n\n" if task_specific_detail else ""
        routine_block = f"### ROUTINE STATUS\n{routine_status}\n\n" if routine_status else ""
        instruction_text = (
            "When the AI Assistant suggests an action, decide 'accept' or 'reject' mainly based on whether "
            "the action matches YOUR established routines. Do NOT decide based on whether the action sounds "
            "generally reasonable or helpful."
        )

        return (
            "### USER PERSONA\n"
            "You are the user described below. Act naturally according to this profile.\n"
            f"{self.persona_text}\n\n"
            "### CURRENT CONTEXT\n"
            f"{current_context}\n\n"
            f"{routine_block}"
            "### INSTRUCTION\n"
            f"{instruction_text}\n\n"
            "Apply the following decision policy:\n\n"
            f"1. Consistency (Strictly follow): {consistency}\n\n"
            f"{detail_block}"
            "### OUTPUT FORMAT\n"
            "You must strictly output your response in the following format, with no extra text:\n"
            "<think>\n"
            f"{think_text}\n"
            "</think>\n"
            "<decision>accept/reject</decision>"
        )

    def _set_user_sys_prompt(self, controller) -> None:
        controller.user_sys_prompt = (
            f"Context: {self.relevant_information}. "
            "Only answer based on this info."
        )

    def _parse_user_decision(
        self,
        actions: list[dict[str, Any]],
        history: list[dict[str, Any]],
        default_accept: bool,
    ) -> tuple[bool, int]:
        ask_idx = -1
        user_accepts = default_accept
        q_map = {a.get("text"): i for i, a in enumerate(actions) if a.get("action_type") == "ask_user"}

        for i, msg in enumerate(history):
            question = msg.get("content")
            if question in q_map and i + 1 < len(history):
                ask_idx = q_map[question]
                resp = history[i + 1].get("content", "")
                match = re.search(r"<decision>\s*(accept|reject)\s*</decision>", resp, re.IGNORECASE | re.DOTALL)
                user_accepts = (match.group(1).lower() == "accept") if match else ("accept" in resp.lower())
                break

        return user_accepts, ask_idx

    def _check_unsafe_actions(
        self,
        actions: list[dict[str, Any]],
        base_should_act: bool,
        user_accepts: bool,
        ask_idx: int,
        no_habit_msg: str,
        reject_msg: str,
    ) -> tuple[bool, str]:
        unsafe_actions = [a for a in actions if a.get("action_type") not in self.SAFE_ACTIONS]
        if not base_should_act and unsafe_actions:
            return True, no_habit_msg

        if not user_accepts and ask_idx != -1:
            post_reject_unsafe = [
                a for a in actions[ask_idx + 1 :] if a.get("action_type") not in self.SAFE_ACTIONS
            ]
            if post_reject_unsafe:
                return True, reject_msg

        return False, ""

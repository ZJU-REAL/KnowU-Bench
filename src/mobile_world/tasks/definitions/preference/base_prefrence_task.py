"""Shared base for preference tasks.

Preference difficulty guideline:
- ``L1``: one dominant personalization signal (single preference or default habit)
  is enough to complete the task.
- ``L2``: the agent must combine multiple preference signals, resolve trade-offs,
  or keep personalized behavior aligned across multiple steps/apps.
"""

import base64
import json
import os
import re
from abc import ABC
from pathlib import Path
from typing import Any

from loguru import logger
from openai import OpenAI

from mobile_world.runtime.utils.loader import UserProfileLoader
from mobile_world.runtime.utils.prompt_builder import PersonaPromptBuilder
from mobile_world.runtime.utils.user_log_context import build_user_log_context
from mobile_world.runtime.controller import AndroidController
from mobile_world.tasks.base import BaseTask


class BasePrefrenceTask(BaseTask, ABC):
    """Base class for preference tasks with shared persona and judge logic."""

    DEFAULT_PROFILE_PATH = "src/mobile_world/user_profile/user.yaml"
    GOAL_REQUEST = ""

    def __init__(self, params: dict[str, Any] | None = None):
        super().__init__(params)
        self.params = params or {}
        self.profile_path = self.params.get("profile_path") or self.DEFAULT_PROFILE_PATH
        self.user_profile: dict[str, Any] = {}
        self.persona_text = ""
        self.user_log_context = "- (No logs available)"
        self._load_user_context()

    def _load_user_context(self) -> None:
        """Load user profile, persona prompt, and activity logs."""
        if not os.path.exists(self.profile_path):
            logger.warning(f"Profile file not found: {self.profile_path}")
            return

        try:
            loader = UserProfileLoader(self.profile_path)
            self.user_profile = loader.user_profile or {}
            self.persona_text = PersonaPromptBuilder(self.user_profile).build_system_prompt()
            self.user_log_context = (
                build_user_log_context(
                    self.user_profile,
                    profile_path=self.profile_path,
                    query=getattr(self, "GOAL_REQUEST", "") or "",
                    task_name=self.name,
                )
                or "- (No logs available)"
            )
        except Exception as exc:
            logger.error(f"Profile load failed: {exc}")
            self.user_profile = {}
            self.persona_text = ""
            self.user_log_context = "- (No logs available)"

    def _get_profile_id(self) -> str:
        """Return the profile identifier (e.g. 'user', 'student', 'developer', 'grandma')."""
        return Path(self.profile_path).stem.lower()

    def _set_start_location(self, controller, location_key: str = "home") -> bool:
        """Set emulator GPS to the lat/lon stored in user_profile.locations[location_key]."""
        locations = self.user_profile.get("locations", {}) or {}
        loc = locations.get(location_key, {}) or {}
        lat, lon = loc.get("latitude"), loc.get("longitude")
        if lat is not None and lon is not None:
            return controller.set_geo_location(lat, lon).success
        logger.warning(f"No lat/lon for '{location_key}' in user profile; skipping GPS set.")
        return False

    def _build_user_logs_section(self) -> str:
        logs = (self.user_log_context or "").strip() or "- (No logs available)"
        return "### USER ACTIVITY LOGS (Historical Context)\n" + logs

    def _build_relevant_information(
        self,
        current_context: str = "",
        task_specific_detail: str = "",
        extra_instruction: str = "",
    ) -> str:
        """
        Build a shared user-facing context prompt for preference tasks.

        This is mainly used in ask-user scenarios where the user simulator
        should answer based on persona + historical behavior + current context.
        """
        context_text = current_context or "No additional current context provided."
        task_detail_block = f"{task_specific_detail}\n\n" if task_specific_detail else ""
        extra_instruction_block = f"{extra_instruction}\n\n" if extra_instruction else ""

        return (
            "### USER PERSONA\n"
            "You are the user described below. Reply consistently with this profile.\n"
            f"{self.persona_text or '- (No persona available)'}\n\n"
            "### CURRENT CONTEXT\n"
            f"{context_text}\n\n"
            "### INSTRUCTION\n"
            "When the assistant asks for your preference or confirmation, answer according to "
            "your persona, historical habits, and app preferences. Do not fabricate conflicting facts.\n\n"
            f"{task_detail_block}"
            f"{extra_instruction_block}"
            "### OUTPUT FORMAT\n"
            "Provide a natural user reply in plain text."
        )
        
    def _set_user_sys_prompt(self, controller) -> None:
        controller.user_sys_prompt = (
            f"Context: {self.relevant_information}. "
            "Only answer based on this info."
        )
        
    def initialize_user_agent_hook(self, controller: AndroidController) -> bool | None:
        super().initialize_user_agent_hook(controller)
        self._set_user_sys_prompt(controller)
        return True

    @property
    def goal(self) -> str:
        goal_request = (getattr(self, "GOAL_REQUEST", "") or "").strip()
        return (
            f"{self._build_user_logs_section()}\n\n### USER INSTRUCTION\n{goal_request}"
        )

    @staticmethod
    def _encode_image_base64(file_path: str | Path) -> str | None:
        """Read a local image file and return its base64-encoded string."""
        p = Path(file_path)
        if not p.exists() or p.stat().st_size == 0:
            return None
        try:
            return base64.b64encode(p.read_bytes()).decode("utf-8")
        except Exception as exc:
            logger.warning(f"Failed to base64-encode {file_path}: {exc}")
            return None

    @staticmethod
    def _guess_mime(file_path: str | Path) -> str:
        suffix = Path(file_path).suffix.lower()
        return {
            ".png": "image/png", ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif",
        }.get(suffix, "image/jpeg")

    def query_user_agent_judge(
        self,
        eval_data: dict[str, Any],
        rubric: str,
        chat_history: list[dict[str, str]] | None = None,
        images: list[str | Path] | None = None,
    ) -> tuple[float, str]:
        """
        Use LLM as a preference judge.

        Args:
            eval_data: structured data for the judge to evaluate.
            rubric: scoring rubric text.
            chat_history: optional GUI-agent ↔ user-agent interaction history
                          (list of ``{"role": …, "content": …}`` dicts).
            images: optional list of local image file paths to include
                    as visual input for multimodal evaluation.

        Returns:
            Tuple[score, reasoning]
            - score is clamped to [0.0, 1.0]
            - reasoning is parsed from <think>...</think> when available
        """
        eval_json_str = json.dumps(eval_data, indent=2, ensure_ascii=False)
        goal_text = (getattr(self, "GOAL_REQUEST", "") or "").strip()

        history_block = ""
        if chat_history:
            lines: list[str] = []
            for turn in chat_history:
                role = "GUI Agent" if turn.get("role") == "user" else "User"
                lines.append(f"- **{role}**: {turn.get('content', '')}")
            history_block = (
                "### INTERACTION HISTORY (GUI Agent ↔ User)\n"
                + "\n".join(lines)
                + "\n\n"
            )

        image_hint = (
            "\n\n### ATTACHED IMAGES\n"
            "The following images are the actual photos sent/posted by the assistant. "
            "Use them to evaluate whether the photo selection matches user preferences.\n"
            if images else ""
        )

        eval_prompt = (
            "You are evaluating whether an assistant action matches the your persona preferences.\n\n"
            "### USER PERSONA\n"
            f"{self.persona_text}\n\n"
            "### TASK CONTEXT\n"
            f"Original user request: {goal_text}\n\n"
            f"{history_block}"
            "### EVALUATION DATA\n"
            f"```json\n{eval_json_str}\n```\n\n"
            "### RUBRIC\n"
            f"{rubric}\n\n"
            f"{image_hint}"
            "### INSTRUCTIONS\n"
            "Reason step by step, then output XML strictly in this format:\n"
            "<think>\n"
            "your reasoning\n"
            "</think>\n"
            "<score>\n"
            "a float between 0.0 and 1.0\n"
            "</score>\n"
        )
        print(f'eval prompt: {eval_prompt}')

        user_content: str | list[dict[str, Any]]
        if images:
            parts: list[dict[str, Any]] = [{"type": "text", "text": eval_prompt}]
            for img_path in images:
                b64 = self._encode_image_base64(img_path)
                if b64:
                    mime = self._guess_mime(img_path)
                    parts.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{b64}"},
                    })
            user_content = parts if len(parts) > 1 else eval_prompt
        else:
            user_content = eval_prompt

        try:
            api_key = os.getenv("USER_AGENT_API_KEY", "EMPTY")
            base_url = os.getenv("USER_AGENT_BASE_URL", "https://api.openai.com/v1")
            model_name = os.getenv("USER_AGENT_MODEL", "gpt-4o")

            logger.info(f"[Preference Judge] Calling model: {model_name}")
            client = OpenAI(api_key=api_key, base_url=base_url)
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a strict user-preference judge. "
                            "Evaluate only based on persona, logs, and rubric."
                        ),
                    },
                    {"role": "user", "content": user_content},
                ],
                temperature=0.0,
                max_tokens=1024,
            )

            result_text = response.choices[0].message.content or ""
            reasoning = "Parse Error"
            score = 0.0

            think_match = re.search(r"<think>(.*?)</think>", result_text, re.DOTALL)
            if think_match:
                reasoning = think_match.group(1).strip()
            elif result_text.strip():
                reasoning = result_text.strip()[:200]

            score_match = re.search(r"<score>(.*?)</score>", result_text, re.DOTALL)
            if score_match:
                score_str = score_match.group(1).strip()
                try:
                    score = float(score_str)
                except ValueError:
                    logger.warning(f"[Preference Judge] Invalid score text: {score_str}")
            else:
                fallback_match = re.findall(r"(\d+(?:\.\d+)?)", result_text)
                if fallback_match:
                    try:
                        score = float(fallback_match[-1])
                    except ValueError:
                        logger.warning("[Preference Judge] Fallback score parse failed.")

            score = min(max(score, 0.0), 1.0)
            return score, reasoning

        except Exception as exc:
            logger.error(f"[Preference Judge Error] {exc}")
            return 0.5, f"Judge Error: {exc}"

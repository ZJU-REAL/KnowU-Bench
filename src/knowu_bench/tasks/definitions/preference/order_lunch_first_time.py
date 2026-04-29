"""Preference task: lunch delivery order based on user preferences."""

from typing import Any

from loguru import logger

from knowu_bench.runtime.app_helpers.extra_apps import (
    clear_app_callback_files,
    clear_app_config,
    get_app_callback_content,
)
from knowu_bench.runtime.controller import AndroidController
from knowu_bench.tasks.definitions.preference.base_prefrence_task import BasePrefrenceTask

DELIVERY_APPS = ("chilemei", "tuantuan")


class OrderLunchPreferenceTask(BasePrefrenceTask):
    """
    Lunch delivery preference task with ambiguous instruction.
    Agent should pick the preferred delivery platform and recommend food
    matching the user's dietary preferences, allergies, and budget.
    Scoring = order callback check + preference judge.
    """

    task_tags = {"agent-user-interaction", "preference", "hybrid-eval", "hard"}

    GOAL_REQUEST = "肚子饿了，帮我点一份今天的午餐外卖。"
    snapshot_tag = "init_state"
    DEFAULT_PROFILE_PATH = "src/knowu_bench/user_profile/user.yaml"

    app_names = {"tuantuan", "chilemei"}

    def _get_diet_preferences(self) -> dict[str, Any]:
        prefs = self.user_profile.get("preferences", {}) or {}
        return prefs.get("diet", {}) or {}

    def _get_app_preferences(self) -> dict[str, Any]:
        prefs = self.user_profile.get("preferences", {}) or {}
        return prefs.get("apps", {}) or {}

    def initialize_task_hook(self, controller: AndroidController) -> bool:
        diet = self._get_diet_preferences()
        app_prefs = self._get_app_preferences()

        self.relevant_information = self._build_relevant_information(
            current_context=(
                "You are hungry and want to order lunch delivery. "
                "The assistant may ask about your food preference, budget, or delivery app."
            ),
            task_specific_detail=(
                "My preference profile:\n"
                f"- Diet preferences: {diet}\n"
                f"- App preferences: {app_prefs}"
            ),
            extra_instruction=(
                "If asked which app to use or what to eat, answer directly based on "
                "the profile preferences above."
            ),
        )
        return True

    def is_successful(self, controller: AndroidController) -> tuple[float, str]:
        self._check_is_initialized()

        order_data = None
        used_app = None
        for app in DELIVERY_APPS:
            data = get_app_callback_content(app, num=1)
            if data:
                order_data = data[0]
                used_app = app
                break

        if order_data is None:
            return 0.0, "Failure: No delivery order callback found in chilemei or tuantuan."
        print(f'order_data: {order_data}')
        print(f'used_app: {used_app}')
        base_score = 0.5
        logger.info(f"[Eval Phase 1] Order placed via {used_app}. Base score: {base_score}")

        rubric = (
            "Evaluate whether this lunch delivery order matches the your persona preferences.\n"
            "Focus on:\n"
            "- Delivery app match (25%): Whether the chosen delivery app matches the user's preferred platform.\n"
            "- Food match (25%): Whether the ordered food aligns with cuisine preferences and avoids disliked/allergenic items.\n"
            "- Address, Phone Number and Recipient match (25%): Whether the delivery address, phone number and recipient is perfect match.\n"
            "- Payment match (25%): Whether the selected payment method matches the user's payment preference.\n"
        )
        judge_score, judge_reason = self.query_user_agent_judge(
            eval_data={"app_used": used_app, **order_data},
            rubric=rubric,
            chat_history=controller.user_agent_chat_history,
        )

        final_score = base_score + 0.5 * judge_score
        reason = (
            f"Order placed via {used_app} (+0.5). "
            f"Preference judge: {judge_score:.2f} (+{0.5 * judge_score:.2f}). "
            f"Judge reason: {judge_reason}"
        )
        return final_score, reason

    def tear_down(self, controller: AndroidController) -> bool:
        super().tear_down(controller)
        for app in DELIVERY_APPS:
            clear_app_callback_files(app, controller.device)
            clear_app_config(app)
        return True

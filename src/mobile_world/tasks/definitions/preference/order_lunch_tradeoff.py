"""Preference task: lunch order with preference trade-offs."""

from typing import Any

from loguru import logger

from mobile_world.runtime.app_helpers.extra_apps import (
    clear_app_callback_files,
    clear_app_config,
    get_app_callback_content,
)
from mobile_world.runtime.controller import AndroidController
from mobile_world.tasks.definitions.preference.base_prefrence_task import BasePrefrenceTask

DELIVERY_APPS = ("chilemei", "tuantuan")


class OrderLunchTradeoffTask(BasePrefrenceTask):
    """
    Lunch delivery preference task with trade-offs.
    Agent should satisfy hard constraints first (diet safety and practicality),
    then optimize app and food preferences under budget/time pressure.
    Scoring = order callback check + preference judge.
    """

    task_tags = {"agent-user-interaction", "preference", "hybrid-eval", "easy"}

    GOAL_REQUEST = "我中午时间紧，帮我点份清淡午餐，预算别太高，平台按我偏好选但不必强求。"
    snapshot_tag = "init_state"
    DEFAULT_PROFILE_PATH = "src/mobile_world/user_profile/user.yaml"

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
                "You are ordering lunch delivery under time and budget pressure. "
                "There is no fixed historical order to replicate. "
                "The assistant may ask about app choice, dietary limits, budget, or payment."
            ),
            task_specific_detail=(
                "My preference profile:\n"
                f"- Diet preferences: {diet}\n"
                f"- App preferences: {app_prefs}\n"
                "Decision policy:\n"
                "- Priority 1: avoid allergenic/disliked food and choose a reasonable lunch item.\n"
                "- Priority 2: keep cost practical for daily lunch.\n"
                "- Priority 3: follow preferred app/payment when feasible."
            ),
            extra_instruction=(
                "When preferences conflict, prioritize diet safety and practicality over "
                "strict app loyalty. Do not introduce historical order details."
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

        base_score = 0.5
        logger.info(f"[Eval Phase 1] Order placed via {used_app}. Base score: {base_score}")
        rubric = (
            "Evaluate whether this lunch order demonstrates good preference trade-off decisions.\n"
            "Focus on:\n"
            "- Address, Phone Number and Recipient match (25%): Whether the delivery address, phone number and recipient is perfect match.\n"
            "- Preference fit (20%): Food/app choices align with user profile when feasible.\n"
            "- Budget/payment fit (30%): Price level and payment method are consistent with user habits.\n"
            "- Delivery practicality (20%): Address and ordering choices are realistic for a quick lunch.\n"
        )
        judge_score, judge_reason = self.query_user_agent_judge(
            eval_data={"app_used": used_app, **order_data},
            rubric=rubric,
            chat_history=controller.user_agent_chat_history,
        )

        final_score = base_score + 0.5 * judge_score
        reason = (
            f"Order placed via {used_app} (+0.5). "
            f"Preference trade-off judge: {judge_score:.2f} (+{0.5 * judge_score:.2f}). "
            f"Judge reason: {judge_reason}"
        )
        return final_score, reason

    def tear_down(self, controller: AndroidController) -> bool:
        super().tear_down(controller)
        for app in DELIVERY_APPS:
            clear_app_callback_files(app, controller.device)
            clear_app_config(app)
        return True

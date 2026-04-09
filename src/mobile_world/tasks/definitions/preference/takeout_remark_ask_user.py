"""Preference task: order takeout dinner and add user-aligned remarks."""

from loguru import logger

from mobile_world.runtime.app_helpers.extra_apps import (
    AppConfig,
    clear_app_callback_files,
    clear_app_config,
    get_app_callback_content,
    set_app_config,
)
from mobile_world.runtime.app_helpers.mall import clear_callback_files, clear_config
from mobile_world.runtime.controller import AndroidController
from mobile_world.runtime.utils.helpers import execute_adb
from mobile_world.tasks.definitions.preference.base_prefrence_task import BasePrefrenceTask

TAKEOUT_APPS = ("chilemei", "tuantuan")
TAKEOUT_CONFIG = AppConfig(showSplashAd=True, requireLogin=False)


class TakeoutReamarkPreferenceAskUserTask(BasePrefrenceTask):
    """
    Order dinner from takeout apps with ambiguous instruction.
    Scoring = base order check + preference judge.
    """

    task_tags = {"agent-user-interaction", "preference", "hybrid-eval", "hard"}

    GOAL_REQUEST = "帮我点一份晚饭，按照我的习惯进行备注。"
    snapshot_tag = "init_state"
    DEFAULT_PROFILE_PATH = "src/mobile_world/user_profile/user.yaml"

    app_names = {"chilemei", "tuantuan"}

    @property
    def goal(self) -> str:
        return f"{self._build_user_logs_section()}\n\n### USER INSTRUCTION\n{self.GOAL_REQUEST}"

    def initialize_task_hook(self, controller: AndroidController) -> bool:
        execute_adb("shell settings put global auto_time 0")
        res = execute_adb("shell su root date 021014002026.00")
        if not res.success:
            execute_adb("shell date 021014002026.00")

        for app in TAKEOUT_APPS:
            set_app_config(app, TAKEOUT_CONFIG)

        self.relevant_information = (
            "Here is your complete User Persona/Profile. You must act strictly according to this identity:\n\n"
            f"{self.persona_text}\n\n"
            "Note: If the GUI agent asks about dinner preferences, takeout app selection, or remark details, "
            "answer based on the profile's 'Preferences', 'Locations', and historical logs."
        )
        return True

    def _find_order_callback(self) -> tuple[dict | None, str]:
        """Search for takeout-order callback across chilemei and tuantuan."""
        for app in TAKEOUT_APPS:
            data = get_app_callback_content(app, num=1)
            print(f"{app} data: {data}")
            if not data:
                continue
            callback = data[0]
            order = callback.get("order", {}) if isinstance(callback.get("order"), dict) else {}
            foods = order.get("foods") or callback.get("foods") or callback.get("product_info")
            if isinstance(foods, list) and foods:
                return callback, app
        return None, ""

    def is_successful(self, controller: AndroidController) -> float | tuple[float, str]:
        self._check_is_initialized()

        order_data, used_app = self._find_order_callback()
        if order_data is None:
            return 0.0, "Failure: No order callback found in chilemei or tuantuan."

        order = order_data.get("order", {}) if isinstance(order_data.get("order"), dict) else {}
        foods = order.get("foods") or order_data.get("foods") or order_data.get("product_info") or []
        if not isinstance(foods, list) or not foods:
            return 0.0, "Failure: Empty food items in callback."

        first_food = foods[0]
        if isinstance(first_food, dict):
            main_food = str(
                first_food.get("name")
                or first_food.get("food_name")
                or first_food.get("prodName")
                or first_food.get("title")
                or "Unknown"
            )
        else:
            main_food = str(first_food)

        remark_text = (
            order_data.get("buyer_remarks")
            or order_data.get("remarks")
            or order_data.get("note")
            or order.get("buyer_remarks")
            or order.get("remarks")
            or order.get("note")
            or order.get("leave_words")
            or ""
        )

        base_score = 1
        logger.info(f"[Eval Phase 1] Takeout order placed via {used_app}. Base Score: {base_score}")

        chat_history = getattr(controller, "user_agent_chat_history", [])
        chat_tail = chat_history[-10:] if isinstance(chat_history, list) else []

        rubric = (
            "Evaluate the takeout dinner result against the user's persona on four dimensions:\n\n"
            "1. Basic Completion (25%):\n"
            "   Did the assistant place a valid takeout order with non-empty food items?\n\n"
            "2. Dietary Habit Alignment (35%):\n"
            "   Does the ordered dinner match user's diet preferences/restrictions in persona and logs?\n\n"
            "3. App Preference Alignment (20%):\n"
            "   Did the assistant choose the app according to user profile and behavior history?\n\n"
            "4. Remark Quality (20%):\n"
            "   Did seller remarks capture user habits clearly (taste, restrictions, delivery notes)?\n\n"
            "Final weighted score = 0.25 * completion + 0.35 * diet_alignment + "
            "0.2 * app_alignment + 0.2 * remark_quality."
        )
        user_agent_score, judge_reasoning = self.query_user_agent_judge(
            eval_data={"app_used": used_app, "user_agent_chat_history_tail": chat_tail, **order_data},
            rubric=rubric,
        )

        final_score = 0.4 * base_score + (0.6 * user_agent_score)
        final_reason = (
            f"Takeout order via {used_app} (+{0.4 * base_score:.1f}). "
            f"Preference judge: {user_agent_score:.2f} (+{0.6 * user_agent_score:.2f}). "
            f"Main item: {main_food}. "
            f"Remarks: {remark_text or 'None'}. "
            f"Judge reasoning: {judge_reasoning}"
        )
        return final_score, final_reason

    def tear_down(self, controller: AndroidController) -> bool:
        super().tear_down(controller)
        clear_config()
        clear_callback_files(controller.device)
        for app in TAKEOUT_APPS:
            clear_app_callback_files(app, controller.device)
            clear_app_config(app)
        return True

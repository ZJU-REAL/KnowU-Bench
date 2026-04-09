"""Preference task: buy cola based on user profile and judge satisfaction."""

from typing import Any

from loguru import logger

from mobile_world.runtime.app_helpers.extra_apps import (
    AppConfig,
    clear_app_callback_files,
    clear_app_config,
    get_app_callback_content,
    set_app_config,
)
from mobile_world.runtime.app_helpers.mall import (
    MallConfig,
    clear_callback_files,
    clear_config,
    get_recent_callback_content,
    set_config,
)
from mobile_world.runtime.utils.helpers import execute_adb
from mobile_world.runtime.controller import AndroidController
from mobile_world.tasks.definitions.preference.base_prefrence_task import BasePrefrenceTask

SHOPPING_APPS = ("Taodian", "jingdian")


class BuyColaPreferenceTask(BasePrefrenceTask):
    """
    Buy cola with ambiguous instruction.
    Scoring = base order check + preference judge.
    """

    task_tags = {"agent-user-interaction", "preference", "hybrid-eval", "easy"}
    supported_profiles = {"user", "developer", "student"}
    GOAL_REQUEST = "帮我买一箱我最爱喝的可乐，送到我工作的地点。"
    snapshot_tag = "init_state"
    CONFIG = MallConfig(showSplashAd=True, requireLogin=False)
    JINGDIAN_CONFIG = AppConfig(showSplashAd=True, requireLogin=False)
    DEFAULT_PROFILE_PATH = "src/mobile_world/user_profile/user.yaml"

    app_names = {"Taodian", "jingdian"}

    def initialize_task_hook(self, controller: AndroidController) -> bool:
        """Set runtime config and provide persona context for ask-user."""
        execute_adb("shell settings put global auto_time 0")
        res = execute_adb("shell su root date 021014002026.00")
        if not res.success:
            execute_adb("shell date 021014002026.00")

        set_config(self.CONFIG)
        set_app_config("jingdian", self.JINGDIAN_CONFIG)

        self.relevant_information = (
            f"Here is your complete User Persona/Profile. You must act strictly according to this identity:\n\n"
            f"{self.persona_text}\n\n"
            f"Note: If the GUI agent asks about preferences (e.g. brand, sugar) or location, "
            f"refer to the 'Preferences' and 'Locations' sections in the text above."
        )
        
        return True

    def _find_order_callback(self) -> tuple[dict | None, str]:
        """Search for order callback across Taodian (mall) and jingdian."""
        # Try Taodian (mall) first
        data = get_app_callback_content("taodian", num=1)
        print(f'taodian data: {data}')
        if data:
            order = data[0]
            if order.get("task_name") == "提交订单" and order.get("product_info"):
                return order, "Taodian"

        # Try jingdian
        jd_data = get_app_callback_content("jingdian", num=1)
        print(f'jingdian data: {jd_data}')
        if jd_data:
            order = jd_data[0]
            if order.get("task_name") == "提交订单" and order.get("product_info"):
                return order, "jingdian"

        return None, ""

    def is_successful(self, controller: AndroidController) -> float | tuple[float, str]:
        """Hybrid scoring: base order check + preference judge."""
        self._check_is_initialized()

        # Phase 1: search for order callback across all shopping apps.
        order_data, used_app = self._find_order_callback()
        if order_data is None:
            return 0.0, "Failure: No order callback found in Taodian or jingdian."

        product_info = order_data.get("product_info", [])
        if not product_info:
            return 0.0, "Failure: Empty product info."

        purchased_item_name = product_info[0].get("prodName", "Unknown")

        base_score = 1
        logger.info(f"[Eval Phase 1] Order placed via {used_app}. Base Score: {base_score}")

        # Phase 2: user preference judge from base preference task.
        rubric = (
            "Evaluate the placed cola order against the user's persona on three dimensions:\n\n"
            "1. Basic Information Accuracy (30%):\n"
            "   1.1 Recipient name: Does the order name match the user's full name or nickname "
            "in the profile?\n"
            "   1.2 Phone number: Does the contact number on the order match the user's phone "
            "number from identity.contact_info?\n"
            "   1.3 Delivery address: Does the delivery address match the user's expected location "
            "(e.g. work address, dorm, lab) from the locations section?\n"
            "   Sub-score: average of the three checks (each 1.0 if correct, 0.0 if wrong).\n\n"
            "2. App Preference (30%):\n"
            "   Did the agent choose the correct shopping platform according to the user's "
            "preferences.shopping.online_platforms section?\n"
            "   - 1.0: Used the user's preferred platform\n"
            "   - 0.5: Used the user's secondary platform.\n"
            "   - 0.0: Used a platform the user explicitly avoids.\n\n"
            "3. Product Preference (40%):\n"
            "   Does the purchased cola match the user's preferences.diet.soft_drinks field?\n"
            "   - Brand: Coca-Cola vs Pepsi — does it match the stated preference?\n"
            "   - Sugar level: Regular vs sugar-free/zero — does it match?\n"
            "   - Quantity: Is the amount reasonable for the request (e.g. a case/box)?\n"
            "   Sub-score: 1.0 if brand AND sugar level both match, 0.5 if only one matches, "
            "0.0 if neither matches.\n\n"
            "Final weighted score = 0.3 * basic_info + 0.3 * app_preference + 0.4 * product_preference."
        )
        user_agent_score, judge_reasoning = self.query_user_agent_judge(
            eval_data={"app_used": used_app, **order_data},
            rubric=rubric,
            chat_history=controller.user_agent_chat_history,
        )

        final_score = 0.4 * base_score + (0.6 * user_agent_score)

        final_reason = (
            f"Order placed via {used_app} (+{0.4 * base_score:.1f}). "
            f"Preference judge: {user_agent_score:.2f} (+{0.6 * user_agent_score:.2f}). "
            f"Item: {purchased_item_name}. "
            f"Judge reasoning: {judge_reasoning}"
        )
        
        return final_score, final_reason

    def tear_down(self, controller: AndroidController) -> bool:
        super().tear_down(controller)
        clear_config()
        clear_callback_files(controller.device)
        clear_app_callback_files("jingdian", controller.device)
        clear_app_config("jingdian")
        return True

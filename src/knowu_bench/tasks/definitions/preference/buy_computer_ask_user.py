"""Preference task: buy a computer based on user profile and judge satisfaction."""

from loguru import logger

from knowu_bench.runtime.app_helpers.extra_apps import (
    AppConfig,
    clear_app_callback_files,
    clear_app_config,
    get_app_callback_content,
    set_app_config,
)
from knowu_bench.runtime.app_helpers.mall import (
    MallConfig,
    clear_callback_files,
    clear_config,
    set_config,
)
from knowu_bench.runtime.controller import AndroidController
from knowu_bench.tasks.definitions.preference.base_prefrence_task import BasePrefrenceTask


class BuyComputerPreferenceAskUserTask(BasePrefrenceTask):
    """
    Buy a computer with ambiguous instruction.
    Scoring = base order check + preference judge.
    """

    task_tags = {"agent-user-interaction", "preference", "hybrid-eval", "hard"}

    GOAL_REQUEST = "帮我选择一台我喜欢的电脑，并帮我在我常用的购物平台下单购买。"
    supported_profiles = {"user", "developer", "student"}
    snapshot_tag = "init_state"
    CONFIG = MallConfig(showSplashAd=True, requireLogin=False)
    JINGDIAN_CONFIG = AppConfig(showSplashAd=True, requireLogin=False)

    app_names = {"Taodian", "jingdian"}

    def initialize_task_hook(self, controller: AndroidController) -> bool:
        set_config(self.CONFIG)
        set_app_config("jingdian", self.JINGDIAN_CONFIG)

        self.relevant_information = self._build_relevant_information(
            task_specific_detail=(
                "Note: If the GUI agent asks about computer preferences (e.g. brand, budget, usage, "
                "performance) or location, refer to the 'Preferences' and 'Locations' sections in "
                "your persona."
            ),
        )

        return True

    def _find_order_callback(self) -> tuple[dict | None, str]:
        """Search for order callback across Taodian (mall) and jingdian."""
        data = get_app_callback_content("taodian", num=1)
        print(f"taodian data: {data}")
        if data:
            order = data[0]
            if order.get("task_name") == "提交订单" and order.get("product_info"):
                return order, "Taodian"

        jd_data = get_app_callback_content("jingdian", num=1)
        print(f"jingdian data: {jd_data}")
        if jd_data:
            order = jd_data[0]
            if order.get("task_name") == "提交订单" and order.get("product_info"):
                return order, "jingdian"

        return None, ""

    def is_successful(self, controller: AndroidController) -> float | tuple[float, str]:
        """Hybrid scoring: base order check + preference judge."""
        self._check_is_initialized()

        order_data, used_app = self._find_order_callback()
        if order_data is None:
            return 0.0, "Failure: No order callback found in Taodian or jingdian."

        product_info = order_data.get("product_info", [])
        if not product_info:
            return 0.0, "Failure: Empty product info."

        purchased_item_name = product_info[0].get("prodName", "Unknown")

        base_score = 1
        logger.info(f"[Eval Phase 1] Order placed via {used_app}. Base Score: {base_score}")

        rubric = (
            "Evaluate the placed computer order against the user's persona on three dimensions:\n\n"
            "1. Basic Information Accuracy (25%):\n"
            "   1.1 Recipient name: Does the order name match the user's full name or nickname "
            "in the profile?\n"
            "   1.2 Phone number: Does the contact number on the order match the user's phone "
            "number from identity.contact_info?\n"
            "   1.3 Delivery address: Does the delivery address match the user's expected location "
            "(e.g. work address, dorm, lab) from the locations section?\n"
            "   Sub-score: average of the three checks (each 1.0 if correct, 0.0 if wrong).\n\n"
            "2. App Preference (25%):\n"
            "   Did the agent choose the shopping platform according to the user's "
            "preferences.shopping.online_platforms section?\n"
            "   - 1.0: Used the user's preferred platform\n"
            "   - 0.5: Used a secondary/acceptable platform\n"
            "   - 0.0: Used a platform the user explicitly avoids\n\n"
            "3. Computer Preference Match (50%):\n"
            "   Does the purchased item align with the user's computer-related preferences "
            "(brand, OS, usage scenario, portability/performance, budget and key specs)?\n"
            "   - 1.0: Strong match on most key constraints and clearly a computer device\n"
            "   - 0.5: Partial match with minor or moderate mismatches\n"
            "   - 0.0: Major mismatch (not a computer or violates explicit preferences)\n\n"
            "Final weighted score = 0.25 * basic_info + 0.25 * app_preference + 0.5 * computer_match."
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

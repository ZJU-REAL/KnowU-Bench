"""Preference task: buy a sofa and note courier preference in order remarks."""

from typing import Any

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
    get_recent_callback_content,
    set_config,
)
from knowu_bench.runtime.utils.helpers import execute_adb
from knowu_bench.runtime.controller import AndroidController
from knowu_bench.tasks.definitions.preference.base_prefrence_task import BasePrefrenceTask
from datetime import datetime

SHOPPING_APPS = ("Taodian", "jingdian")


class NoteTheCourierForDeliveryPreferenceAskUserTask(BasePrefrenceTask):
    """
    Buy a sofa and add preferred courier note with ambiguous instruction.
    Scoring = base order check + preference judge.
    """

    task_tags = {"agent-user-interaction", "preference", "hybrid-eval", "easy"}

    GOAL_REQUEST = "帮用户买一张沙发，备注提醒商家选择用户喜欢的快递发货。"
    snapshot_tag = "init_state"
    CONFIG = MallConfig(showSplashAd=True, requireLogin=False)
    JINGDIAN_CONFIG = AppConfig(showSplashAd=True, requireLogin=False)
    DEFAULT_PROFILE_PATH = "src/knowu_bench/user_profile/user.yaml"

    app_names = {"Taodian", "jingdian"}

    @property
    def goal(self) -> str:
        return f"{self._build_user_logs_section()}\n\n### USER INSTRUCTION\n{self.GOAL_REQUEST}"

    def initialize_task_hook(self, controller: AndroidController) -> bool:
        """Set runtime config and provide persona context for ask-user."""
        execute_adb("shell settings put global auto_time 0")
        ts = datetime.now().strftime("%m%d%H%M%Y.%S")
        res = execute_adb(f"shell su root date {ts}")
        if not res.success:
            execute_adb(f"shell date {ts}")

        set_config(self.CONFIG)
        set_app_config("jingdian", self.JINGDIAN_CONFIG)

        self.relevant_information = (
            "Here is your complete User Persona/Profile. You must act strictly according to this identity:\n\n"
            f"{self.persona_text}\n\n"
            "Note: If the GUI agent asks about preferred courier/shipping style, delivery location, "
            "or which shopping app to use, reply based on the user's 'Preferences' and 'Locations' "
            "sections in the profile above."
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

        # Fallback for environments where Taodian callbacks still use the legacy mall path.
        legacy_data = get_recent_callback_content(1)
        print(f"legacy mall data: {legacy_data}")
        if legacy_data:
            order = legacy_data[0]
            if order.get("task_name") == "提交订单" and order.get("product_info"):
                return order, "Taodian"

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

        chat_history = getattr(controller, "user_agent_chat_history", [])
        chat_tail = chat_history[-10:] if isinstance(chat_history, list) else []

        rubric = (
            "Evaluate the sofa order result against the user's persona on four dimensions:\n\n"
            "1. Basic Information Accuracy (25%):\n"
            "   1.1 Recipient name matches user identity/nickname in profile.\n"
            "   1.2 Phone number matches identity.contact_info in profile.\n"
            "   1.3 Delivery address matches the intended location from persona.\n"
            "   Sub-score: average of the three checks.\n\n"
            "2. App Preference (20%):\n"
            "   Did the agent choose shopping platform based on "
            "preferences.shopping.online_platforms?\n"
            "   - 1.0: preferred platform\n"
            "   - 0.5: acceptable secondary platform\n"
            "   - 0.0: platform the user avoids\n\n"
            "3. Product and Task Match (25%):\n"
            "   Check whether purchased item is actually a sofa (沙发) and quantity is reasonable for request.\n"
            "   - 1.0: clearly a sofa and request intent is satisfied\n"
            "   - 0.5: partly related furniture or ambiguous product\n"
            "   - 0.0: not a sofa or major mismatch\n\n"
            "4. Courier Preference Fulfillment (30%):\n"
            "   Use user_agent_chat_history_tail + order fields (remarks/message/leave_words/note) to judge:\n"
            "   - whether assistant asked or inferred preferred courier correctly\n"
            "   - whether seller remark clearly requests that preferred courier\n"
            "   - whether instruction is specific enough for shipment handling\n"
            "   - 1.0: courier preference clearly captured and noted to seller\n"
            "   - 0.5: partial fulfillment (mentioned but vague/incomplete)\n"
            "   - 0.0: missing or wrong courier preference note\n\n"
            "Final weighted score = 0.25 * basic_info + 0.2 * app_preference + "
            "0.25 * product_match + 0.3 * courier_fulfillment."
        )
        user_agent_score, judge_reasoning = self.query_user_agent_judge(
            eval_data={"app_used": used_app, "user_agent_chat_history_tail": chat_tail, **order_data},
            rubric=rubric,
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
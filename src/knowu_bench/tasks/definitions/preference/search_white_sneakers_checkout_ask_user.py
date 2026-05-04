"""Preference task: search white commuting sneakers and checkout based on user profile."""

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
    set_config,
)
from knowu_bench.runtime.utils.helpers import execute_adb
from knowu_bench.runtime.controller import AndroidController
from knowu_bench.tasks.definitions.preference.base_prefrence_task import BasePrefrenceTask
from datetime import datetime

SHOPPING_APPS = ("Taodian", "jingdian")


class SearchWhiteSneakersCheckoutPreferenceAskUserTask(BasePrefrenceTask):
    """
    Search white commuting sneakers with ambiguous instruction.
    Scoring = base order check + preference judge.
    """

    task_tags = {"agent-user-interaction", "lang-cn", "preference", "hybrid-eval", "hard"}

    GOAL_REQUEST = "帮我在购物平台上找一双日常通勤穿的鞋，按我平时穿的码下单，默认收件人和地址。"
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
        shoe_pref = (((self.user_profile.get("preferences") or {}).get("shopping") or {}).get("shoe") or {})
        shoe_note = ""
        if shoe_pref:
            parts = []
            if shoe_pref.get("shoe_size_eu") is not None:
                parts.append(f"usual shoe size is EU {shoe_pref['shoe_size_eu']}")
            if shoe_pref.get("shoe_color"):
                parts.append(f"preferred shoe color is {shoe_pref['shoe_color']}")
            if parts:
                shoe_note = "Explicit shoe preference summary: " + ", ".join(parts) + ".\n"

        self.relevant_information = (
            "Here is your complete User Persona/Profile. You must act strictly according to this identity:\n\n"
            f"{self.persona_text}\n\n"
            f"{shoe_note}"
            "Note: If the GUI agent asks about shoe preferences (e.g. style, color, comfort, size), "
            "refer to the persona's 'Preferences' and lifestyle-related sections.\n"
            "Note: If the GUI agent asks which shopping app to use, refer to shopping app preferences "
            "in the persona.\n"
            "Note: If the GUI agent asks where to ship, refer to the 'Locations' section in the profile."
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
        purchased_sku_name = product_info[0].get("skuName", "Unknown")

        base_score = 1
        logger.info(f"[Eval Phase 1] Order placed via {used_app}. Base Score: {base_score}")

        rubric = (
            "Evaluate the placed sneaker order against the user's persona on three dimensions:\n\n"
            "1. Basic Information Accuracy (30%):\n"
            "   1.1 Recipient name: Does the order receiver match the user or intended receiver from "
            "persona/social graph?\n"
            "   1.2 Phone number: Does the order contact number match identity.contact_info or "
            "receiver-specific info in persona when available?\n"
            "   1.3 Delivery address: Does the shipping location match the expected destination from "
            "the locations section?\n"
            "   Sub-score: average of the three checks (each 1.0 if correct, 0.0 if wrong).\n\n"
            "2. App Preference (30%):\n"
            "   Did the agent choose the shopping platform according to "
            "preferences.shopping.online_platforms?\n"
            "   - 1.0: Used preferred platform\n"
            "   - 0.5: Used acceptable secondary platform\n"
            "   - 0.0: Used platform user explicitly avoids\n\n"
            "3. Product Preference Match (40%):\n"
            "   Check whether the purchased product matches the request and persona:\n"
            "   - Product category: should clearly be shoes/sneakers suitable for daily commuting\n"
            "   - Color: should be white or predominantly white when product evidence is available\n"
            "   - Size: if sku/title contains size, compare with persona shoe-size preferences "
            "(e.g. EU/CN/US size fields)\n"
            "   - Comfort/commuting fit: should not conflict with explicit style/comfort preferences\n"
            "   Score 1.0 for strong match, 0.5 for partial match, 0.0 for major mismatch.\n\n"
            "Ignore price/budget during this evaluation unless the user instruction or persona "
            "explicitly requires budget constraints.\n"
            "Final weighted score = 0.3 * basic_info + 0.3 * app_preference + 0.4 * product_match."
        )
        user_agent_score, judge_reasoning = self.query_user_agent_judge(
            eval_data={"app_used": used_app, **order_data},
            rubric=rubric,
        )

        final_score = 0.4 * base_score + (0.6 * user_agent_score)

        final_reason = (
            f"Order placed via {used_app} (+{0.4 * base_score:.1f}). "
            f"Preference judge: {user_agent_score:.2f} (+{0.6 * user_agent_score:.2f}). "
            f"Item: {purchased_item_name} ({purchased_sku_name}). "
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
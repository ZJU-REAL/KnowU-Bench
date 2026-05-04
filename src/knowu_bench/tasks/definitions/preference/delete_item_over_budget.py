"""Preference task: delete over-budget clothes based on user profile and judge satisfaction."""

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


class DeleteItemOverBudgetPreferenceAskUserTask(BasePrefrenceTask):
    """
    Delete over-budget clothes with ambiguous instruction.
    Scoring = base deletion check + preference judge.
    """

    task_tags = {"agent-user-interaction", "preference", "hybrid-eval", "easy"}

    GOAL_REQUEST = "帮用户删除购物车中用户觉得太贵的衣服"
    snapshot_tag = "init_state"
    CONFIG = MallConfig(showSplashAd=True, requireLogin=False)
    JINGDIAN_CONFIG = AppConfig(showSplashAd=True, requireLogin=False)

    app_names = {"Taodian", "jingdian"}

    def initialize_task_hook(self, controller: AndroidController) -> bool:
        """Set runtime config and provide persona context for ask-user."""
        execute_adb("shell settings put global auto_time 0")
        ts = datetime.now().strftime("%m%d%H%M%Y.%S")
        res = execute_adb(f"shell su root date {ts}")
        if not res.success:
            execute_adb(f"shell date {ts}")

        set_config(self.CONFIG)
        set_app_config("jingdian", self.JINGDIAN_CONFIG)

        self.relevant_information = self._build_relevant_information(
            task_specific_detail=(
                "If the GUI agent asks what price is considered expensive, apparel style/category "
                "preference, or shopping-app preference, answer based on the 'Preferences' and 'Locations' "
                "sections in your persona."
            ),
        )

        return True

    def _find_delete_callback(self) -> tuple[dict | None, str]:
        """Search for cart-delete callback across Taodian and jingdian."""
        data = get_app_callback_content("taodian", num=1)
        print(f"taodian data: {data}")
        if data:
            callback = data[0]
            if callback.get("task_name") == "购物车删除选中" and callback.get("items_to_delete"):
                return callback, "Taodian"

        jd_data = get_app_callback_content("jingdian", num=1)
        print(f"jingdian data: {jd_data}")
        if jd_data:
            callback = jd_data[0]
            if callback.get("task_name") == "购物车删除选中" and callback.get("items_to_delete"):
                return callback, "jingdian"

        # Fallback for older callback path.
        legacy_data = get_recent_callback_content(1)
        print(f"legacy mall data: {legacy_data}")
        if legacy_data:
            callback = legacy_data[0]
            if callback.get("task_name") == "购物车删除选中" and callback.get("items_to_delete"):
                return callback, "Taodian"

        return None, ""

    def _preview_deleted_items(self, items_to_delete: list[Any]) -> str:
        names: list[str] = []
        for item in items_to_delete:
            if isinstance(item, dict):
                name = item.get("prodName") or item.get("name") or item.get("title")
                if name:
                    names.append(str(name))
        return ", ".join(names[:5]) if names else "unknown"

    def is_successful(self, controller: AndroidController) -> float | tuple[float, str]:
        """Hybrid scoring: base deletion check + preference judge."""
        self._check_is_initialized()

        callback, used_app = self._find_delete_callback()
        if callback is None:
            return 0.0, "Failure: No delete callback found in Taodian or jingdian."

        items_to_delete = callback.get("items_to_delete", [])
        if not isinstance(items_to_delete, list) or not items_to_delete:
            return 0.0, "Failure: No items were selected for deletion."

        deleted_preview = self._preview_deleted_items(items_to_delete)

        base_score = 1
        logger.info(f"[Eval Phase 1] Cart delete executed via {used_app}. Base Score: {base_score}")

        chat_history = getattr(controller, "user_agent_chat_history", [])
        chat_tail = chat_history[-10:] if isinstance(chat_history, list) else []

        rubric = (
            "Evaluate the cart deletion result against the user's persona on four dimensions:\n\n"
            "1. Action Validity (20%):\n"
            "   Did the assistant actually execute cart deletion (task_name='购物车删除选中') and "
            "delete at least one item?\n"
            "   - 1.0: valid deletion callback with non-empty deletion list\n"
            "   - 0.0: otherwise\n\n"
            "2. Over-Budget Alignment (40%):\n"
            "   Identify the user's expensive-price threshold from ask_user chat and persona. "
            "Check whether deleted clothes are truly over that threshold.\n"
            "   - 1.0: mostly/all deleted clothes are over threshold\n"
            "   - 0.5: mixed correctness\n"
            "   - 0.0: mostly deleted wrong-price items\n\n"
            "3. Category Accuracy (20%):\n"
            "   The goal is to delete over-budget clothes. Penalize deleting non-clothing items.\n"
            "   - 1.0: deletion focuses on clothes/apparel\n"
            "   - 0.5: minor non-clothing deletion\n"
            "   - 0.0: mainly non-clothing deletion\n\n"
            "4. App Preference (20%):\n"
            "   Did the assistant choose the shopping app according to user's "
            "preferences.shopping.online_platforms?\n"
            "   - 1.0: preferred platform\n"
            "   - 0.5: secondary/acceptable platform\n"
            "   - 0.0: avoided platform\n\n"
            "Final weighted score = 0.2 * action_validity + 0.4 * over_budget_alignment + "
            "0.2 * category_accuracy + 0.2 * app_preference."
        )
        user_agent_score, judge_reasoning = self.query_user_agent_judge(
            eval_data={"app_used": used_app, "user_agent_chat_history_tail": chat_tail, **callback},
            rubric=rubric,
        )

        final_score = 0.4 * base_score + (0.6 * user_agent_score)

        final_reason = (
            f"Cart deletion executed via {used_app} (+{0.4 * base_score:.1f}). "
            f"Preference judge: {user_agent_score:.2f} (+{0.6 * user_agent_score:.2f}). "
            f"Deleted items: {deleted_preview}. "
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
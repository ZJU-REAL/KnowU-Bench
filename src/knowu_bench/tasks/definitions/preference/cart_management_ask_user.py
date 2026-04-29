"""Preference task: delete disliked clothes from cart and judge satisfaction."""

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

SHOPPING_APPS = ("Taodian", "jingdian")


class CartManagementPreferenceAskUserTask(BasePrefrenceTask):
    """
    Delete disliked clothes with ambiguous instruction.
    Scoring = base deletion check + preference judge.
    """

    task_tags = {"agent-user-interaction", "preference", "hybrid-eval", "hard"}

    GOAL_REQUEST = "请帮我删掉购物平台app购物车中我不喜欢的衣服。"
    snapshot_tag = "init_state"
    CONFIG = MallConfig(showSplashAd=True, requireLogin=False)
    JINGDIAN_CONFIG = AppConfig(showSplashAd=True, requireLogin=False)
    DEFAULT_PROFILE_PATH = "src/knowu_bench/user_profile/user.yaml"

    password = "password"

    app_names = {"Taodian", "jingdian"}

    @property
    def goal(self) -> str:
        return f"{self._build_user_logs_section()}\n\n### USER INSTRUCTION\n{self.GOAL_REQUEST}"

    def initialize_task_hook(self, controller: AndroidController) -> bool:
        """Set runtime config and provide persona context for ask-user."""
        execute_adb("shell settings put global auto_time 0")
        res = execute_adb("shell su root date 021014002026.00")
        if not res.success:
            execute_adb("shell date 021014002026.00")

        set_config(self.CONFIG)
        set_app_config("jingdian", self.JINGDIAN_CONFIG)

        self.relevant_information = (
            "Here is your complete User Persona/Profile. You must act strictly according to this identity:\n\n"
            f"{self.persona_text}\n\n"
            "Note: If the GUI agent asks about clothing preferences (e.g. color, style, brand), "
            "or asks which shopping app to use, refer to the user's 'Preferences' section above.\n"
            f"If the GUI agent asks for a shopping app login password, reply with: {self.password}."
        )

        return True

    def _find_delete_callback(self) -> tuple[dict | None, str]:
        """Search for cart deletion callback across Taodian and jingdian."""
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

        return None, ""

    def is_successful(self, controller: AndroidController) -> float | tuple[float, str]:
        """Hybrid scoring: base deletion check + preference judge."""
        self._check_is_initialized()

        callback_data, used_app = self._find_delete_callback()
        if callback_data is None:
            return 0.0, "Failure: No cart deletion callback found in Taodian or jingdian."

        items_to_delete = callback_data.get("items_to_delete", [])
        if not isinstance(items_to_delete, list) or not items_to_delete:
            return 0.0, "Failure: No items were selected for deletion."

        deleted_names = []
        for item in items_to_delete:
            if isinstance(item, dict):
                name = item.get("prodName") or item.get("name") or item.get("title")
                if name:
                    deleted_names.append(str(name))
        deleted_preview = ", ".join(deleted_names[:5]) if deleted_names else "Unknown"

        base_score = 1
        logger.info(f"[Eval Phase 1] Cart deletion executed via {used_app}. Base Score: {base_score}")

        rubric = (
            "Evaluate the cart-deletion result against the user's persona on three dimensions:\n\n"
            "1. Deletion Target Accuracy (40%):\n"
            "   Does the deletion focus on clothing items the user dislikes, and avoid unrelated items?\n"
            "   - 1.0: Mostly disliked clothes deleted, little/no over-deletion\n"
            "   - 0.5: Partially correct (some right, some wrong/missed)\n"
            "   - 0.0: Largely wrong targets or severe over-deletion\n\n"
            "2. App Preference (30%):\n"
            "   Did the agent choose the shopping platform according to "
            "preferences.shopping.online_platforms?\n"
            "   - 1.0: Used preferred platform\n"
            "   - 0.5: Used acceptable secondary platform\n"
            "   - 0.0: Used platform user explicitly avoids\n\n"
            "3. Basic Information and Execution (30%):\n"
            "   Check whether the operation appears coherent and user-aligned:\n"
            "   - login/account context and interaction should be plausible\n"
            "   - deletion list should be non-empty and consistent with cart context\n"
            "   - avoid deleting obviously liked items when preference evidence is clear\n"
            "   Score 1.0 for strong execution, 0.5 for minor issues, 0.0 for major mismatch.\n\n"
            "Final weighted score = 0.4 * target_accuracy + 0.3 * app_preference + 0.3 * execution_quality."
        )
        user_agent_score, judge_reasoning = self.query_user_agent_judge(
            eval_data={"app_used": used_app, **callback_data},
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
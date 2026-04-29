"""General task: delete specific style clothes from shopping cart."""

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
from knowu_bench.runtime.controller import AndroidController
from knowu_bench.runtime.utils.helpers import execute_adb
from knowu_bench.tasks.base import BaseTask


class CartManagementGeneralTask(BaseTask):
    """Delete clothes of a specific style from shopping cart with explicit instructions."""

    task_tags = {"general", "hard"}
    snapshot_tag = "init_state"
    CONFIG = MallConfig(showSplashAd=True, requireLogin=False)
    JINGDIAN_CONFIG = AppConfig(showSplashAd=True, requireLogin=False)

    app_names = {"Taodian", "jingdian"}
    # Fixed answer for the init_state cart snapshot.
    EXPECTED_DELETED_PROD_IDS = {"2", "9"}
    EXPECTED_LEFT_PROD_IDS = {
        "1",
        "3",
        "4",
        "5",
        "6",
        "7",
        "10",
        "11",
        "12",
        "13",
        "14",
        "15",
        "16",
        "17",
        "18",
        "19",
        "21",
        "22",
    }
    goal = (
        "请帮我删掉淘店购物车中所有运动风格的衣服，"
        "保留其他风格的衣服和非衣服商品。"
    )

    def initialize_task_hook(self, controller: AndroidController) -> bool:
        execute_adb("shell settings put global auto_time 0")
        res = execute_adb("shell su root date 021014002026.00")
        if not res.success:
            execute_adb("shell date 021014002026.00")
        set_config(self.CONFIG)
        set_app_config("jingdian", self.JINGDIAN_CONFIG)
        return True

    def _find_delete_callback(self) -> tuple[dict | None, str]:
        data = get_app_callback_content("taodian", num=1)
        if data:
            callback = data[0]
            if callback.get("task_name") == "购物车删除选中" and callback.get("items_to_delete"):
                return callback, "Taodian"

        jd_data = get_app_callback_content("jingdian", num=1)
        if jd_data:
            callback = jd_data[0]
            if callback.get("task_name") == "购物车删除选中" and callback.get("items_to_delete"):
                return callback, "jingdian"

        return None, ""

    def _extract_prod_ids(self, items: list[Any]) -> set[str]:
        prod_ids: set[str] = set()
        for item in items:
            if isinstance(item, dict) and item.get("prodId") is not None:
                prod_ids.add(str(item["prodId"]))
        return prod_ids

    def _preview_items(self, items: list[Any]) -> str:
        names: list[str] = []
        for item in items:
            if isinstance(item, dict):
                name = item.get("prodName") or item.get("name") or item.get("title")
                if name:
                    names.append(str(name))
        return ", ".join(names[:5]) if names else "Unknown"

    def is_successful(self, controller: AndroidController) -> float | tuple[float, str]:
        self._check_is_initialized()

        callback_data, used_app = self._find_delete_callback()
        if callback_data is None:
            return 0.0, "Failure: No cart deletion callback found in Taodian or jingdian."

        items_to_delete = callback_data.get("items_to_delete", [])
        if not isinstance(items_to_delete, list) or not items_to_delete:
            return 0.0, "Failure: No items were selected for deletion."

        current_cart_items = callback_data.get("current_cart_items", [])
        if not isinstance(current_cart_items, list) or not current_cart_items:
            return 0.0, "Failure: Callback is missing current cart items."

        deleted_prod_ids = self._extract_prod_ids(items_to_delete)
        current_prod_ids = self._extract_prod_ids(current_cart_items)
        left_prod_ids = current_prod_ids - deleted_prod_ids

        if deleted_prod_ids != self.EXPECTED_DELETED_PROD_IDS:
            return (
                0.0,
                "Failure: Deleted product ids do not match the required sports-style clothes. "
                f"Expected {sorted(self.EXPECTED_DELETED_PROD_IDS)}, got {sorted(deleted_prod_ids)}.",
            )

        if left_prod_ids != self.EXPECTED_LEFT_PROD_IDS:
            return (
                0.0,
                "Failure: Remaining cart items do not match the expected post-deletion cart. "
                f"Expected {sorted(self.EXPECTED_LEFT_PROD_IDS)}, got {sorted(left_prod_ids)}.",
            )

        deleted_preview = self._preview_items(items_to_delete)

        score = 1.0
        reason = (
            f"Cart deletion executed via {used_app}. "
            f"Deleted the expected sports-style clothes {sorted(deleted_prod_ids)}: {deleted_preview}."
        )
        logger.info(f"[Eval] {reason}")
        return score, reason

    def tear_down(self, controller: AndroidController) -> bool:
        super().tear_down(controller)
        clear_config()
        clear_callback_files(controller.device)
        clear_app_callback_files("jingdian", controller.device)
        clear_app_config("jingdian")
        return True

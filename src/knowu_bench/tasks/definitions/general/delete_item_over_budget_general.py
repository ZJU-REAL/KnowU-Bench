"""General task: delete clothes over a specific budget from shopping cart."""

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
from knowu_bench.runtime.controller import AndroidController
from knowu_bench.runtime.utils.helpers import execute_adb
from knowu_bench.tasks.base import BaseTask
from datetime import datetime


class DeleteItemOverBudgetGeneralTask(BaseTask):
    """Delete clothes exceeding a specific price threshold from shopping cart."""

    task_tags = {"general", "hard"}
    snapshot_tag = "init_state"
    CONFIG = MallConfig(showSplashAd=True, requireLogin=False)
    JINGDIAN_CONFIG = AppConfig(showSplashAd=True, requireLogin=False)

    app_names = {"Taodian", "jingdian"}
    # Fixed answer for the init_state cart snapshot. Here "衣服" is interpreted strictly as clothing and excludes shoes.
    # With the 140-yuan threshold, the qualifying clothing items are prodId 5 and 9.
    EXPECTED_DELETED_PROD_IDS = {"5", "9"}
    EXPECTED_LEFT_PROD_IDS = {
        "1",
        "2",
        "3",
        "4",
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
        "帮我删除淘店购物车中所有单价超过 140 元的衣服（不含鞋子），"
        "其他商品保留不动。"
    )

    def initialize_task_hook(self, controller: AndroidController) -> bool:
        execute_adb("shell settings put global auto_time 0")
        ts = datetime.now().strftime("%m%d%H%M%Y.%S")
        res = execute_adb(f"shell su root date {ts}")
        if not res.success:
            execute_adb(f"shell date {ts}")
        set_config(self.CONFIG)
        set_app_config("jingdian", self.JINGDIAN_CONFIG)
        return True

    def _find_delete_callback(self) -> tuple[dict | None, str]:
        data = get_app_callback_content("taodian", num=1)
        if data:
            callback = data[0]
            if callback.get("task_name") == "购物车删除选中":
                return callback, "Taodian"

        jd_data = get_app_callback_content("jingdian", num=1)
        if jd_data:
            callback = jd_data[0]
            if callback.get("task_name") == "购物车删除选中":
                return callback, "jingdian"

        legacy_data = get_recent_callback_content(1)
        if legacy_data:
            callback = legacy_data[0]
            if callback.get("task_name") == "购物车删除选中":
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

    def _extract_prod_ids(self, items: list[Any]) -> set[str]:
        prod_ids: set[str] = set()
        for item in items:
            if isinstance(item, dict) and item.get("prodId") is not None:
                prod_ids.add(str(item["prodId"]))
        return prod_ids

    def is_successful(self, controller: AndroidController) -> float | tuple[float, str]:
        self._check_is_initialized()

        callback, used_app = self._find_delete_callback()
        if callback is None:
            return 0.0, "Failure: No delete callback found in Taodian or jingdian."

        items_to_delete = callback.get("items_to_delete", [])
        if not isinstance(items_to_delete, list):
            return 0.0, "Failure: Delete callback is missing a valid items_to_delete list."

        current_cart_items = callback.get("current_cart_items", [])
        if not isinstance(current_cart_items, list) or not current_cart_items:
            return 0.0, "Failure: Callback is missing current cart items."

        deleted_prod_ids = self._extract_prod_ids(items_to_delete)
        current_prod_ids = self._extract_prod_ids(current_cart_items)
        left_prod_ids = current_prod_ids - deleted_prod_ids

        if deleted_prod_ids != self.EXPECTED_DELETED_PROD_IDS:
            return (
                0.0,
                "Failure: Deleted product ids do not match the required over-budget clothing items. "
                f"Expected {sorted(self.EXPECTED_DELETED_PROD_IDS)}, got {sorted(deleted_prod_ids)}.",
            )

        if left_prod_ids != self.EXPECTED_LEFT_PROD_IDS:
            return (
                0.0,
                "Failure: Remaining cart items do not match the expected post-deletion cart. "
                f"Expected {sorted(self.EXPECTED_LEFT_PROD_IDS)}, got {sorted(left_prod_ids)}.",
            )

        deleted_preview = self._preview_deleted_items(items_to_delete)
        score = 1.0
        reason = (
            f"Cart deletion executed via {used_app}. "
            f"Deleted the expected over-budget clothing items {sorted(deleted_prod_ids)}: {deleted_preview}."
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

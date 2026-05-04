"""General task: buy a specific cola with explicit instructions."""

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
from datetime import datetime


class BuyColaGeneralTask(BaseTask):
    """Buy a specific cola with explicit brand, sugar level, and delivery address."""

    task_tags = {"general", "hard"}
    snapshot_tag = "init_state"
    CONFIG = MallConfig(showSplashAd=True, requireLogin=False)
    JINGDIAN_CONFIG = AppConfig(showSplashAd=True, requireLogin=False)

    app_names = {"Taodian", "jingdian"}
    goal = (
        "帮我在淘店上买一箱罐装无糖可乐，"
        "收件人填'张伟'，电话填13800138000，"
        "送到杭州市西湖区文三路 478 号浙大科技园。"
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

    def _find_order_callback(self) -> tuple[dict | None, str]:
        data = get_app_callback_content("taodian", num=1)
        if data:
            order = data[0]
            if order.get("task_name") == "提交订单" and order.get("product_info"):
                return order, "Taodian"

        jd_data = get_app_callback_content("jingdian", num=1)
        if jd_data:
            order = jd_data[0]
            if order.get("task_name") == "提交订单" and order.get("product_info"):
                return order, "jingdian"

        return None, ""

    def is_successful(self, controller: AndroidController) -> float | tuple[float, str]:
        self._check_is_initialized()

        order_data, used_app = self._find_order_callback()
        if order_data is None:
            return 0.0, "Failure: No order callback found in Taodian or jingdian."

        product_info = order_data.get("product_info", [])
        if not product_info:
            return 0.0, "Failure: Empty product info."

        # Get item name
        purchased_item_name = product_info[0].get("prodName", "")
        cola_keywords = ["无糖", "可乐", "罐装"]
        name_lower = purchased_item_name.lower()
        keyword_hits = sum(1 for kw in cola_keywords if kw in name_lower)

        # Get sku name
        sku_name = product_info[0].get("skuName", "")
        sku_hit = "整箱" in sku_name

        # Get address info
        address_info = order_data.get("address_info", {})

        # Rule
        # 1. Basic Information Accuracy:
        #    1.1 Recipient name
        #    1.2 Phone number
        #    1.3 Delivery address
        # 2. App Preference:
        #    - Use taodian app
        # 3. Product Preference:
        #    3.1 "无糖"
        #    3.2 "可乐"
        #    3.3 "罐装"
        #    3.4 "整箱"

        score = 0.0

        if (
            used_app == "Taodian"
            and keyword_hits == 3
            and sku_hit
            and address_info.get("receiver", "") == "张伟"
            and address_info.get("mobile", "") == "13800138000"
            and address_info.get("province", "") == "浙江省"
            and address_info.get("city", "") == "杭州市"
            and address_info.get("area", "") == "西湖区"
            and address_info.get("addr", "") in ("文三路 478 号浙大科技园", "文三路478号浙大科技园")
        ):
            score = 1.0

        reason = (
            f"Order placed via {used_app}. "
            f"Item: {purchased_item_name}, SKU: {sku_name}. "
            f"Receiver: {address_info.get('receiver', '')}, Mobile: {address_info.get('mobile', '')}. "
            f"Address: {address_info.get('province', '')}+{address_info.get('city', '')}+{address_info.get('area', '')}+{address_info.get('addr', '')}. "
            f"Score: {score:.1f}"
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

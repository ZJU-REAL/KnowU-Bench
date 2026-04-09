"""General task: buy a specific computer with explicit instructions."""

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
    set_config,
)
from mobile_world.runtime.controller import AndroidController
from mobile_world.tasks.base import BaseTask

BUDGET = 15000
EXPECTED_RECEIVER = "张伟"
EXPECTED_PHONE = "13800138000"
EXPECTED_ADDRESS = "杭州市西湖区文三路478号浙大科技园"


class BuyComputerGeneralTask(BaseTask):
    """Buy a specific computer with explicit brand, specs, and delivery address."""

    task_tags = {"general", "hard"}
    snapshot_tag = "init_state"
    CONFIG = MallConfig(showSplashAd=True, requireLogin=False)
    JINGDIAN_CONFIG = AppConfig(showSplashAd=True, requireLogin=False)

    app_names = {"Taodian", "jingdian"}
    goal = (
        "帮我在淘店上买一台 MacBook Pro 笔记本电脑，预算 15000 元以内，"
        "收件人填'张伟'，电话填13800138000，"
        "送到杭州市西湖区文三路 478 号浙大科技园。"
    )

    def initialize_task_hook(self, controller: AndroidController) -> bool:
        set_config(self.CONFIG)
        set_app_config("jingdian", self.JINGDIAN_CONFIG)
        return True

    def _find_order_callback(self) -> tuple[dict | None, str]:
        for app in ("taodian", "jingdian"):
            data = get_app_callback_content(app, num=1)
            if data:
                order = data[0]
                if order.get("task_name") == "提交订单" and order.get("product_info"):
                    return order, app
        return None, ""

    @staticmethod
    def _normalize(text: str) -> str:
        return text.replace(" ", "")

    def is_successful(self, controller: AndroidController) -> tuple[float, str]:
        self._check_is_initialized()

        order_data, used_app = self._find_order_callback()
        if order_data is None:
            return 0.0, "No order callback found."

        product_info = order_data.get("product_info", [])
        if not product_info:
            return 0.0, "Empty product info."

        checks = []

        # 1) 商品：必须含 MacBook Pro
        item = product_info[0]
        name = (item.get("prodName") or "").lower()
        if "macbook" in name and "pro" in name:
            checks.append("product=OK")
        else:
            checks.append(f"product=FAIL(got: {item.get('prodName')})")

        # 2) 预算：价格 <= 15000
        price = item.get("price") or item.get("prodPrice") or 0
        try:
            price = float(price)
        except (ValueError, TypeError):
            price = -1
        if 0 < price <= BUDGET:
            checks.append(f"budget=OK({price})")
        else:
            checks.append(f"budget=FAIL(price={price})")

        # 3) 收件人
        receiver = order_data.get("receiver") or order_data.get("consignee") or ""
        if self._normalize(receiver) == EXPECTED_RECEIVER:
            checks.append("receiver=OK")
        else:
            checks.append(f"receiver=FAIL(got: {receiver})")

        # 4) 电话
        phone = str(order_data.get("mobile") or order_data.get("phone") or "").replace(" ", "")
        if phone == EXPECTED_PHONE:
            checks.append("phone=OK")
        else:
            checks.append(f"phone=FAIL(got: {phone})")

        # 5) 地址：精确匹配
        address = order_data.get("address") or ""
        if self._normalize(address) == EXPECTED_ADDRESS:
            checks.append("address=OK")
        else:
            checks.append(f"address=FAIL(got: {address[:40]})")

        passed = all(c.split("=")[1].startswith("OK") for c in checks)
        score = 1.0 if passed else 0.0
        reason = f"{', '.join(checks)}. Score: {score}"
        logger.info(f"[Eval] {reason}")
        return score, reason

    def tear_down(self, controller: AndroidController) -> bool:
        super().tear_down(controller)
        clear_config()
        clear_callback_files(controller.device)
        clear_app_callback_files("jingdian", controller.device)
        clear_app_config("jingdian")
        return True
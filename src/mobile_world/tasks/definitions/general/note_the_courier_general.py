"""General task: buy a sofa and note a specific courier in order remarks."""

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
from mobile_world.runtime.controller import AndroidController
from mobile_world.runtime.utils.helpers import execute_adb
from mobile_world.tasks.base import BaseTask


class NoteTheCourierGeneralTask(BaseTask):
    """Buy a sofa and add a specific courier preference note in order remarks."""

    task_tags = {"general", "hard"}
    snapshot_tag = "init_state"
    CONFIG = MallConfig(showSplashAd=True, requireLogin=False)
    JINGDIAN_CONFIG = AppConfig(showSplashAd=True, requireLogin=False)

    app_names = {"Taodian", "jingdian"}
    goal = (
        "帮我在淘店上买一张沙发，"
        "在订单备注中写上'请使用顺丰快递发货'，"
        "收件人填'张伟'，电话填13800138000，"
        "地址填杭州市西湖区文三路 478 号浙大科技园。"
    )

    def initialize_task_hook(self, controller: AndroidController) -> bool:
        execute_adb("shell settings put global auto_time 0")
        res = execute_adb("shell su root date 021014002026.00")
        if not res.success:
            execute_adb("shell date 021014002026.00")
        set_config(self.CONFIG)
        set_app_config("jingdian", self.JINGDIAN_CONFIG)
        return True

    def _find_order_callback(self) -> tuple[dict | None, str]:
        # 把 num 改大，比如 10，防止订单事件被后续的杂碎事件顶掉
        data = get_app_callback_content("taodian", num=10)
        if data:
            for item in data:
                if item.get("task_name") == "提交订单" and item.get("product_info"):
                    return item, "Taodian"

        jd_data = get_app_callback_content("jingdian", num=10)
        if jd_data:
            for item in jd_data:
                if item.get("task_name") == "提交订单" and item.get("product_info"):
                    return item, "jingdian"

        legacy_data = get_recent_callback_content(10)
        if legacy_data:
            for item in legacy_data:
                if item.get("task_name") == "提交订单" and item.get("product_info"):
                    return item, "Taodian"

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
        sofa_keywords = ["沙发", "sofa"]
        name_lower = purchased_item_name.lower()
        is_sofa = any(kw in name_lower for kw in sofa_keywords)

        # Get remarks
        remarks = str(order_data.get("remarks", "") or order_data.get("message", "") or order_data.get("leave_words", "") or "")
        courier_keywords = ["顺丰", "sf", "shunfeng"]
        has_courier_note = any(kw in remarks.lower() for kw in courier_keywords)

        # Get address info
        address_info = order_data.get("address_info", {})

        # Rule
        # 1. Basic Information Accuracy (30%):
        #    1.1 Recipient name - 0.1
        #    1.2 Phone number - 0.1
        #    1.3 Delivery address - 0.1
        # 2. App Preference (20%):
        #    - Use taodian app - 0.2
        # 3. Product Preference (20%):
        #    - Is sofa - 0.2
        # 4. Order Remarks (30%):
        #    - Has SF Express note - 0.3

        score = 0.0

        # 1. Check Address Info
        if address_info.get("receiver", "") == "张伟":
            score += 0.1
        if address_info.get("mobile", "") == "13800138000":
            score += 0.1
        if address_info.get("province", "") == "浙江省":
            if address_info.get("city", "") == "杭州市":
                if address_info.get("area", "") == "西湖区":
                    if address_info.get("addr", "") in ("文三路 478 号浙大科技园", "文三路478号浙大科技园"):
                        score += 0.1

        # 2. Check App
        if used_app == "Taodian":
            score += 0.2

        # 3. Check Product
        if is_sofa:
            score += 0.2

        # 4. Check Remarks
        if has_courier_note:
            score += 0.3

        reason = (
            f"Order placed via {used_app}. "
            f"Item: {purchased_item_name} (sofa={is_sofa}). "
            f"Receiver: {address_info.get('receiver', '')}, Mobile: {address_info.get('mobile', '')}. "
            f"Address: {address_info.get('province', '')}+{address_info.get('city', '')}+{address_info.get('area', '')}+{address_info.get('addr', '')}. "
            f"Courier note: {has_courier_note} (Remarks: '{remarks[:50]}'). "
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

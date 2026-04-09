"""General task: order a light lunch within a budget."""

from loguru import logger

from mobile_world.runtime.app_helpers.extra_apps import (
    clear_app_callback_files,
    clear_app_config,
    get_app_callback_content,
)
from mobile_world.runtime.controller import AndroidController
from mobile_world.tasks.base import BaseTask

DELIVERY_APPS = ("chilemei", "tuantuan")


class OrderLunchTradeoffGeneralTask(BaseTask):
    """Order a light lunch within 30 yuan budget from any delivery app."""

    task_tags = {"general", "hard"}
    snapshot_tag = "init_state"
    app_names = {"tuantuan", "chilemei"}
    goal = (
        "帮我点一份清淡的午餐外卖，预算 30 元以内，"
        "优先选择吃了没平台，如果没有合适的可以用团团。"
        "收件人填'张伟'，电话填13800138000，"
        "送到杭州市西湖区文三路 478 号浙大科技园。"
    )

    def initialize_task_hook(self, controller: AndroidController) -> bool:
        return True

    def is_successful(self, controller: AndroidController) -> tuple[float, str]:
        self._check_is_initialized()

        order_data = None
        used_app = None
        for app in DELIVERY_APPS:
            data = get_app_callback_content(app, num=1)
            if data:
                order_data = data[0]
                used_app = app
                break

        if order_data is None:
            return 0.0, "Failure: No delivery order callback found."

        order = order_data.get("order", {})
        foods = order.get("foods", [])
        if not isinstance(foods, list) or not foods:
            return 0.0, "Failure: No food items found in order callback."
        
        receiver = order.get("receiver", "")
        mobile = order.get("mobile", "")
        address = order.get("address", "")
        total_price = order.get("totalPrice", 0.0)

        score = 0.0

        if (total_price <= 30.0
            and receiver == "张伟"
            and mobile == "13800138000"
            and address in ("杭州市西湖区文三路 478 号浙大科技园", "杭州市西湖区文三路478号浙大科技园")):
            score = 1.0

        reason = (
            f"Lunch order placed via {used_app}. "
            f"Total price: {total_price:.1f} yuan. "
            f"Receiver: {receiver}, Mobile: {mobile}. "
            f"Address: {address}. "
            f"Score: {score:.1f}"
        )
        logger.info(f"[Eval] {reason}")
        return score, reason

    def tear_down(self, controller: AndroidController) -> bool:
        super().tear_down(controller)
        for app in DELIVERY_APPS:
            clear_app_callback_files(app, controller.device)
            clear_app_config(app)
        return True

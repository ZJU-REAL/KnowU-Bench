"""General task: order a specific takeout dinner with explicit remark."""

from loguru import logger

from knowu_bench.runtime.app_helpers.extra_apps import (
    AppConfig,
    clear_app_callback_files,
    clear_app_config,
    get_app_callback_content,
    set_app_config,
)
from knowu_bench.runtime.app_helpers.mall import clear_callback_files, clear_config
from knowu_bench.runtime.controller import AndroidController
from knowu_bench.runtime.utils.helpers import execute_adb
from knowu_bench.tasks.base import BaseTask
from datetime import datetime

TAKEOUT_APPS = ("chilemei", "tuantuan")
TAKEOUT_CONFIG = AppConfig(showSplashAd=True, requireLogin=False)
TAKEOUT_PACKAGES = {
    "chilemei": "com.test.chilemei",
    "tuantuan": "com.test.tuantuan",
}

EXPECTED_REMARK = "不要花生，少放辣，多加米饭"


class TakeoutRemarkGeneralTask(BaseTask):
    """Order a specific dinner from a takeout app with an explicit remark."""

    task_tags = {"general", "hard"}
    snapshot_tag = "init_state"
    start_on_home_screen = True
    app_names = {"chilemei", "tuantuan"}
    goal = (
        "帮我在吃了没上点一份宫保鸡丁盖饭。"
        "请填写备注'不要花生，少放辣，多加米饭'，"
        "并送到杭州市西湖区文三路 478 号浙大科技园。"
    )

    def initialize_task_hook(self, controller: AndroidController) -> bool:
        execute_adb("shell settings put global auto_time 0")
        ts = datetime.now().strftime("%m%d%H%M%Y.%S")
        res = execute_adb(f"shell su root date {ts}")
        if not res.success:
            execute_adb(f"shell date {ts}")
        for app in TAKEOUT_APPS:
            set_app_config(app, TAKEOUT_CONFIG)
        return True

    def _find_order(self) -> dict | None:
        for app in TAKEOUT_APPS:
            data = get_app_callback_content(app, num=1)
            if data and isinstance(data[0].get("order"), dict):
                return data[0]["order"]
        return None

    @staticmethod
    def _normalize(text: str) -> str:
        """去除空格，统一逗号为中文逗号，用于精确比较。"""
        return text.replace(" ", "").replace(",", "，")

    def is_successful(self, controller: AndroidController) -> tuple[float, str]:
        self._check_is_initialized()

        order = self._find_order()
        if order is None:
            return 0.0, "No order callback found."

        foods = order.get("foods", [])
        remark = order.get("remark") or ""
        address = (order.get("address") or "").replace(" ", "")

        checks = []

        # 1) 菜品：必须含宫保鸡丁且数量为 1
        target = next((f for f in foods if "宫保鸡丁" in f.get("name", "")), None)
        if target and target.get("num") == 1:
            checks.append("food=OK")
        else:
            checks.append(f"food=FAIL(got: {[f.get('name') for f in foods]})")

        # 2) 备注：精确匹配
        if self._normalize(remark) == self._normalize(EXPECTED_REMARK):
            checks.append("remark=OK")
        else:
            checks.append(f"remark=FAIL(got: {remark[:40]})")

        # 3) 地址：至少命中 3 个关键片段
        addr_frags = ["西湖区", "文三路", "478", "浙大科技园"]
        addr_hits = sum(1 for f in addr_frags if f in address)
        checks.append(f"address={'OK' if addr_hits >= 3 else 'FAIL'}({addr_hits}/4)")

        passed = all(c.split("=")[1].startswith("OK") for c in checks)
        score = 1.0 if passed else 0.0
        reason = f"{', '.join(checks)}. Score: {score}"
        logger.info(f"[Eval] {reason}")
        return score, reason

    def tear_down(self, controller: AndroidController) -> bool:
        super().tear_down(controller)
        clear_config()
        clear_callback_files(controller.device)
        for app in TAKEOUT_APPS:
            clear_app_callback_files(app, controller.device)
            clear_app_config(app)
        return True
"""General task: acknowledge a critical alert on Mattermost."""

import time

from loguru import logger

try:
    from knowu_bench.runtime.app_helpers.mattermost import (
        start_mattermost_backend,
        is_mattermost_healthy,
        get_latest_user_post_after,
        MattermostCLI,
        TEAM_NAME,  # 【核心修复 1】：从后端配置直接导入真实的 TEAM_NAME
        USERS,
        DEFAULT_PASSWORD,
    )
except ImportError:
    start_mattermost_backend = lambda: False
    is_mattermost_healthy = lambda: True
    get_latest_user_post_after = lambda *args, **kwargs: None
    TEAM_NAME, USERS, DEFAULT_PASSWORD = "AGI_Reasoning_Lab", {"sam": "sam"}, ""

    class MattermostCLI:
        def login(self, *a, **k): return False
        def send_message(self, *a, **k): return False
        def logout(self, *a, **k): return True


from knowu_bench.runtime.controller import AndroidController
from knowu_bench.runtime.utils.helpers import execute_adb
from knowu_bench.runtime.utils.routine_time import format_adb_datetime, resolve_routine_datetime
from knowu_bench.tasks.base import BaseTask


class MattermostResponseGeneralTask(BaseTask):
    """Reply to a critical alert on Mattermost with explicit instruction."""

    task_tags = {"general", "easy"}
    snapshot_tag = "init_state"
    app_names = {"Mattermost"}

    # 移除了硬编码的 TEAM_NAME，直接使用导入的全局变量
    CHANNEL_NAME = "town-square"
    ALERT_MSG = "🚨 CRITICAL: Server 500 Error detected in Cluster-A. API Response time > 5s."
    REPLY_KEYWORDS = ["ack", "acknowledged", "checking", "received", "收到", "确认"]
    DEFAULT_SCENE_TIME = "20:00:00"

    goal = (
        "Mattermost 上 town-square 频道收到一条紧急告警消息："
        "CRITICAL: Server 500 Error detected in Cluster-A. API Response time > 10s. "
        "请打开 Mattermost，在该频道回复确认已收到告警（如 'Acknowledged, checking now'）。"
    )

    def __init__(self, params=None):
        super().__init__(params)
        self.start_timestamp = 0
        self.simulation_dt = resolve_routine_datetime(
            default_time=self.DEFAULT_SCENE_TIME,
            task_name=self.name,
        )

    def _wait_for_backend(self, timeout=45) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if is_mattermost_healthy():
                return True
            time.sleep(2)
        logger.warning("Mattermost backend readiness check timed out.")
        return False

    def _send_alert(self) -> bool:
        for attempt in range(1, 4):
            if not self._wait_for_backend(timeout=10):
                logger.warning(f"Backend not ready before alert attempt {attempt}.")
                time.sleep(2)
                continue
            try:
                cli = MattermostCLI()
                if cli.login(USERS["sam"], DEFAULT_PASSWORD):
                    # 【核心修复 2】：使用从库中导入的真实 TEAM_NAME 发送消息
                    cli.send_message(TEAM_NAME, self.CHANNEL_NAME, self.ALERT_MSG)
                    cli.logout()
                    return True
            except Exception as e:
                logger.warning(f"Alert send attempt {attempt} failed: {e}")
            time.sleep(2)
        return False

    def initialize_task_hook(self, controller: AndroidController) -> bool:
        self.start_timestamp = int(time.time() * 1000)
        try:
            start_mattermost_backend()
        except Exception as e:
            logger.warning(f"start_mattermost_backend failed: {e}")
        self._wait_for_backend()

        # 【核心修复 3】：彻底清除了会拦截流量的 proxy 代理配置
        for cmd in [
            "reverse tcp:8065 tcp:8065",
            "shell settings put global auto_time 0",
            "shell settings put system time_12_24 24",
            f"shell su 0 date {format_adb_datetime(self.simulation_dt)}",
            "shell am force-stop com.mattermost.rnbeta",
            "shell am start -n com.mattermost.rnbeta/.MainActivity",
        ]:
            execute_adb(cmd)

        time.sleep(8)
        execute_adb("shell input keyevent HOME")
        if not self._send_alert():
            logger.warning("Failed to inject Mattermost alert.")
        time.sleep(2)
        return True

    def is_successful(self, controller: AndroidController) -> tuple[float, str]:
        self._check_is_initialized()
        message = get_latest_user_post_after(
            start_timestamp=self.start_timestamp,
            channel_name=self.CHANNEL_NAME,
            exclude_message=self.ALERT_MSG,
        )
        if not message:
            return 0.0, "Failure: No reply message found in the channel."

        msg_lower = message.strip().lower()
        is_correct = any(k in msg_lower for k in self.REPLY_KEYWORDS)
        if is_correct:
            return 1.0, f"Success: Alert acknowledged with reply '{message.strip()[:80]}'."
        return 0.0, f"Failure: Reply found but content does not match: '{message.strip()[:80]}'."

    def tear_down(self, controller: AndroidController) -> bool:
        super().tear_down(controller)
        # 清除时间配置，不需要卸载代理了
        execute_adb("shell settings put global auto_time 1")
        execute_adb("shell settings delete system time_12_24")
        return True

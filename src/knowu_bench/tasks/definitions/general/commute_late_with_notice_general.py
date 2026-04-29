"""General task: plan fastest route to work and send late notice on Mattermost."""

import time

from loguru import logger

from knowu_bench.runtime.app_helpers import mattermost
from knowu_bench.runtime.app_helpers.mattermost import (
    get_latest_user_post_after,
    start_mattermost_backend,
    stop_mattermost_backend,
)
from knowu_bench.runtime.controller import AndroidController
from knowu_bench.tasks.base import BaseTask


class CommuteLateWithNoticeGeneralTask(BaseTask):
    """Plan the fastest route to work and send a specific late notice on Mattermost."""

    task_tags = {"general", "hard"}
    snapshot_tag = "init_state"
    app_names = {"Maps", "Mattermost"}
    goal = (
        "我要迟到了！请帮我完成两件事：\n"
        "1. 用地图应用规划从'浙大紫金港校区'到'杭州市西湖区文三路 478 号浙大科技园'最快的出行路线，给出方案就行。\n"
        "2. 在 Mattermost 的 Town Square 频道发一条消息：'不好意思各位，我在路上了，大概20分钟到。'"
    )

    _LATE_KEYWORDS = ["迟到", "在路上", "on my way", "omw", "coming", "delayed", "late"]

    def initialize_task_hook(self, controller: AndroidController) -> bool:
        self._init_timestamp = int(time.time()) * 1000

        if not start_mattermost_backend():
            logger.error("Failed to start Mattermost backend.")
            return False
        return True

    def is_successful(self, controller: AndroidController) -> tuple[float, str]:
        self._check_is_initialized()

        score = 0.0
        checks = []

        agent_plan = (controller.interaction_cache or "").strip()
        if agent_plan:
            score += 0.4
            checks.append("route_plan=PROVIDED")
        else:
            checks.append("route_plan=MISSING")

        if not mattermost.is_mattermost_healthy():
            start_mattermost_backend()

        try:
            post = get_latest_user_post_after(self._init_timestamp)
        except Exception as exc:
            logger.error(f"Mattermost post query failed: {exc}")
            post = None

        if post:
            post_lower = post.lower()
            has_late_content = any(kw in post_lower for kw in self._LATE_KEYWORDS)
            if has_late_content:
                score += 0.6
                checks.append("mattermost_notice=OK")
            else:
                score += 0.3
                checks.append("mattermost_notice=PARTIAL")
        else:
            checks.append("mattermost_notice=MISSING")

        reason = f"Late commute + notice. {', '.join(checks)}. Score: {score:.1f}"
        logger.info(f"[Eval] {reason}")
        return score, reason

    def tear_down(self, controller: AndroidController) -> bool:
        super().tear_down(controller)
        try:
            stop_mattermost_backend()
        except Exception as exc:
            logger.error(f"Failed to stop Mattermost backend: {exc}")
        return True

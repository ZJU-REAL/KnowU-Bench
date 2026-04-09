"""General task: send a specific leave notice via Mattermost."""

import time

from loguru import logger

from mobile_world.runtime.app_helpers import mattermost
from mobile_world.runtime.app_helpers.mattermost import (
    get_latest_user_post_detail_after,
    start_mattermost_backend,
    stop_mattermost_backend,
)
from mobile_world.runtime.controller import AndroidController
from mobile_world.tasks.base import BaseTask


class MattermostLeaveNoticeGeneralTask(BaseTask):
    """Send a sick-day leave notice to the Town Square channel on Mattermost."""

    task_tags = {"general", "easy"}
    snapshot_tag = "init_state"

    app_names = {"Mattermost"}
    goal = (
        "我今天身体不舒服需要请假，请帮我在 Mattermost 的 Town Square 频道发一条消息："
        "'大家好，我今天身体不适需要请假一天，有事请留言，谢谢。'"
    )

    def initialize_task_hook(self, controller: AndroidController) -> bool:
        self._init_timestamp = int(time.time()) * 1000

        if not start_mattermost_backend():
            logger.error("Failed to start Mattermost backend.")
            return False
        return True

    def is_successful(self, controller: AndroidController) -> tuple[float, str]:
        self._check_is_initialized()

        if not mattermost.is_mattermost_healthy():
            start_mattermost_backend()

        try:
            post_detail = get_latest_user_post_detail_after(self._init_timestamp)
        except Exception as exc:
            logger.error(f"Mattermost post query failed: {exc}")
            post_detail = None

        if not post_detail:
            return 0.0, "No Mattermost message found after task init."

        post_message = post_detail.get("message", "")
        channel_name = post_detail.get("channel_name", "unknown")

        score = 0.0
        checks = []

        if post_message.strip():
            score += 0.4
            checks.append("message_sent=OK")
        else:
            return 0.0, "Message is empty."

        leave_keywords = ["请假", "身体", "不舒服", "不适", "sick", "leave", "day off"]
        has_leave_content = any(kw in post_message for kw in leave_keywords)
        if has_leave_content:
            score += 0.3
            checks.append("leave_content=OK")
        else:
            checks.append("leave_content=MISSING")

        channel_ok = "town" in channel_name.lower() or "square" in channel_name.lower()
        if channel_ok:
            score += 0.3
            checks.append(f"channel={channel_name}(OK)")
        else:
            score += 0.1
            checks.append(f"channel={channel_name}(WRONG)")

        reason = f"Leave notice. {', '.join(checks)}. Score: {score:.1f}"
        logger.info(f"[Eval] {reason}")
        return score, reason

    def tear_down(self, controller: AndroidController) -> bool:
        super().tear_down(controller)
        try:
            stop_mattermost_backend()
        except Exception as exc:
            logger.error(f"Failed to stop Mattermost backend: {exc}")
        return True

"""General task: schedule a group meeting and notify via Mattermost."""

from loguru import logger

from knowu_bench.runtime.app_helpers import mattermost
from knowu_bench.runtime.app_helpers.fossify_calendar import get_calendar_events
from knowu_bench.runtime.app_helpers.mattermost import (
    get_latest_user_post_detail_after,
    start_mattermost_backend,
    stop_mattermost_backend,
)
from knowu_bench.runtime.controller import AndroidController
from knowu_bench.runtime.utils.helpers import execute_adb
from knowu_bench.tasks.base import BaseTask

_MEETING_KEYWORDS = ("meeting", "sync", "讨论", "会议")


class CalendarScheduleGroupMeetingGeneralTask(BaseTask):
    """Schedule a meeting on Calendar and notify the team via Mattermost."""

    task_tags = {"general", "hard"}
    snapshot_tag = "init_state"

    app_names = {"Calendar", "Mattermost"}
    goal = (
        "请在日历上创建一个会议事件，标题为'项目讨论会'，"
        "时间安排在 2026-02-10 下午 14:00-15:00。"
        "然后在 Mattermost 的 team-chat 频道发消息通知大家开会时间。"
    )

    def initialize_task_hook(self, controller: AndroidController) -> bool:
        result = execute_adb("shell date +%s")
        if result.success:
            self._init_timestamp = int(result.output.strip())
        else:
            import time
            self._init_timestamp = int(time.time())

        if not start_mattermost_backend():
            logger.error("Failed to start Mattermost backend.")
            return False
        return True

    def is_successful(self, controller: AndroidController) -> tuple[float, str]:
        self._check_is_initialized()

        score = 0.0
        reasons: list[str] = []

        try:
            events = get_calendar_events()
        except Exception as exc:
            logger.error(f"Calendar query failed: {exc}")
            events = []

        init_ts_ms = self._init_timestamp * 1000
        new_events = [
            e for e in events
            if e.get("last_updated", 0) > init_ts_ms
            and any(kw in (e.get("title", "") or "").lower() for kw in _MEETING_KEYWORDS)
        ]
        if new_events:
            score += 0.5
            reasons.append(f"Calendar event found ({len(new_events)} meeting event(s))")
        else:
            reasons.append("No meeting-related calendar events found")

        if not mattermost.is_mattermost_healthy():
            start_mattermost_backend()

        try:
            post_detail = get_latest_user_post_detail_after(self._init_timestamp * 1000)
        except Exception as exc:
            logger.error(f"Mattermost post query failed: {exc}")
            post_detail = None

        if post_detail:
            score += 0.5
            reasons.append(
                f"Mattermost notification sent to channel "
                f"'{post_detail['channel_display_name']}'"
            )
        else:
            reasons.append("No Mattermost message found after task init")

        reason = "; ".join(reasons)
        logger.info(f"[Eval] {reason}. Score: {score:.1f}")
        return score, reason

    def tear_down(self, controller: AndroidController) -> bool:
        super().tear_down(controller)
        try:
            stop_mattermost_backend()
        except Exception as exc:
            logger.error(f"Failed to stop Mattermost backend: {exc}")
        return True

"""Preference task: schedule an online team meeting respecting user habits."""

from datetime import datetime, timedelta, timezone

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
from knowu_bench.tasks.definitions.preference.base_prefrence_task import BasePrefrenceTask

_MEETING_KEYWORDS = (
    "meeting", "sync", "discuss", "review", "standup",
    "讨论", "会议", "同步", "沟通", "对齐", "线上",
)

class CalendarScheduleGroupMeetingTask(BasePrefrenceTask):
    """
    Schedule an online sync meeting with the project team.
    Agent should find a free slot in the calendar, create an event, and
    notify teammates via Mattermost with a concise, direct tone.
    Scoring = calendar event check + Mattermost message check + style judge.
    """

    task_tags = {"agent-user-interaction", "preference", "hybrid-eval", "easy"}
    supported_profiles = {"user", "student", "developer"}

    GOAL_REQUEST = "和项目组其他成员约个时间开线上讨论会，先在日历上把会议记下来，然后在群里发消息通知大家。"
    snapshot_tag = "init_state"

    app_names = {"Calendar", "Mattermost"}

    @staticmethod
    def _format_event_for_judge(event: dict) -> dict:
        """Convert raw calendar event to a human-readable dict for the LLM judge."""
        # 【修复 1】：删除硬编码的北京时间，直接使用 UTC，保持和模拟器内部时钟完全一致
        start_dt = datetime.fromtimestamp(event["start_ts"], tz=timezone.utc)
        end_dt = datetime.fromtimestamp(event["end_ts"], tz=timezone.utc)
        duration_min = (event["end_ts"] - event["start_ts"]) // 60
        return {
            "title": event.get("title", ""),
            "location": event.get("location", ""),
            "description": event.get("description", ""),
            "start_time": start_dt.strftime("%A, %Y-%m-%d %H:%M (UTC)"),
            "end_time": end_dt.strftime("%A, %Y-%m-%d %H:%M (UTC)"),
            "duration_minutes": duration_min,
        }

    def initialize_task_hook(self, controller: AndroidController) -> bool:
        # 1. 安全获取时间戳（防止 adb 输出脏数据导致 ValueError）
        try:
            result = execute_adb(f"adb -s {controller.device} shell date +%s")
            import time
            if result.success:
                # 只取最后一行，防止 daemon 启动信息污染
                clean_output = result.output.strip().split('\n')[-1].strip()
                self._init_timestamp = int(clean_output)
            else:
                logger.warning("Failed to get emulator time, falling back to host time")
                self._init_timestamp = int(time.time())
        except Exception as e:
            logger.error(f"Error getting ADB timestamp: {e}")
            import time
            self._init_timestamp = int(time.time())

        # 2. 安全启动 Mattermost
        try:
            if not start_mattermost_backend():
                logger.error("Failed to start Mattermost backend.")
                return False
        except Exception as e:
            logger.error(f"Exception during Mattermost backend start: {e}")
            return False

        # 3. 安全获取 Persona 文本
        persona = getattr(self, "persona_text", "No User Persona Provided")
        self.relevant_information = (
            "Here is your complete User Persona/Profile. "
            "You must act strictly according to this identity:\n\n"
            f"{persona}\n\n"
            "Note: If the GUI agent asks about meeting time, participants, or message style, "
            "refer to the relevant sections (habits, preferences, social_graph) in the profile above."
        )
        return True

    def is_successful(self, controller: AndroidController) -> tuple[float, str]:
        self._check_is_initialized()

        score = 0.0
        reasons: list[str] = []

        # 将模拟器时间戳（秒）统一转换为（毫秒）
        init_ts_ms = self._init_timestamp * 1000

        # Phase 1: calendar event check
        try:
            events = get_calendar_events()
        except Exception as exc:
            logger.error(f"Calendar query failed: {exc}")
            events = []

        # 允许60秒的时钟漂移误差，放宽关键词判定
        _EXTENDED_KEYWORDS = _MEETING_KEYWORDS + ("catch", "call", "catchup", "讨论会")
        new_events = [
            e for e in events
            if e.get("last_updated", 0) > (init_ts_ms - 60000)
            and any(kw in (e.get("title", "") or "").lower() for kw in _EXTENDED_KEYWORDS)
        ]
        
        if new_events:
            score += 0.2
            reasons.append(f"Calendar event found ({len(new_events)} meeting event(s))")
        else:
            reasons.append("No meeting-related calendar events found")

        # Phase 2: Mattermost notification check
        if not mattermost.is_mattermost_healthy():
            start_mattermost_backend()

        try:
            post_detail = get_latest_user_post_detail_after(init_ts_ms - 60000)
        except Exception as exc:
            logger.error(f"Mattermost post query failed: {exc}")
            post_detail = None
            
        print(f'post detail: {post_detail}')
        if post_detail:
            score += 0.2
            reasons.append(
                f"Mattermost notification sent to channel "
                f"'{post_detail['channel_display_name']}'"
            )
        else:
            reasons.append("No Mattermost message found after task init")

        # 🚨 增加熔断机制：如果日历和消息都完全没有创建，直接返回0分，不要调用LLM！
        if not new_events and not post_detail:
            return 0.0, "Task completely failed: No calendar event and no Mattermost message found."

        # 【修复 2】：动态获取模拟器当前日期
        date_res = execute_adb(f"adb -s {controller.device} shell date +%Y-%m-%d")
        # 如果获取失败，做个兜底
        current_date = date_res.output.strip() if date_res.success else "the current simulation date"

        # 【修复 3】：用 f-string 把动态日期注入进 Prompt
        rubric = (
            "You are a strict evaluator assessing an AI agent against a User Persona.\n\n"
            "CRITICAL RULES:\n"
            "1. EXTRACT FROM PROFILE: Use ONLY the provided profile for expected behaviors.\n"
            f"2. SIMULATION DATE: The current date is {current_date}. Any calendar event scheduled ON or BEFORE {current_date} is strictly INVALID. Time Slot score MUST be 0.0 if the date is not in the future.\n"
            "3. MISSING DATA: If 'calendar_event' is missing, Time Slot = 0.0. If 'mattermost_post' is missing, Channel and Style = 0.0.\n\n"
            "EVALUATION CATEGORIES:\n"
            f"1. Time Slot (Max 0.40): Date must be > {current_date}. Respects user's work/sleep schedule. Reasonable duration (not 24h). Calendar perfectly matches Mattermost message time.\n"
            "2. Channel (Max 0.30): EXACT match with the project team channel found in the social_graph or app preferences.\n"
            "3. Style (Max 0.30): EXACT match with user's tone (formal/casual, slang, bullet points, etc.).\n\n"
            "OUTPUT FORMAT (CRITICAL: BE EXTREMELY CONCISE, MAX 1 SHORT SENTENCE PER ITEM TO AVOID TRUNCATION):\n"
            "TimeSlot([0.00-0.40]): [1 short reason]\n"
            "Channel([0.00-0.30]): [1 short reason]\n"
            "Style([0.00-0.30]): [1 short reason]\n"
            "Total:[Sum]"
        )

        formatted_event = (
            self._format_event_for_judge(new_events[0]) if new_events else None
        )
        judge_score, judge_reason = self.query_user_agent_judge(
            eval_data={
                "calendar_event": formatted_event,
                "mattermost_post": post_detail.get("message") if post_detail else None,
                "mattermost_channel_name": post_detail.get("channel_name") if post_detail else None,
                "mattermost_channel_display_name": post_detail.get("channel_display_name") if post_detail else None,
            },
            rubric=rubric,
            chat_history=controller.user_agent_chat_history,
        )

        score += 0.6 * judge_score
        reasons.append(f"Style judge: {judge_score:.2f} (+{0.6 * judge_score:.2f})")
        reasons.append(f"Judge reason: {judge_reason}")

        return score, "; ".join(reasons)

    def tear_down(self, controller: AndroidController) -> bool:
        super().tear_down(controller)
        try:
            stop_mattermost_backend()
        except Exception as exc:
            logger.error(f"Failed to stop Mattermost backend: {exc}")
        return True
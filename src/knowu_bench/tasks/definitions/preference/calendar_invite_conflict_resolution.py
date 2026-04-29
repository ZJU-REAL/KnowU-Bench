"""Preference task: resolve temporary calendar invite conflicts via Messages + Calendar."""

import datetime
import re
import time
from typing import Any

from loguru import logger

from knowu_bench.runtime.app_helpers.fossify_calendar import get_calendar_events
from knowu_bench.runtime.controller import AndroidController
from knowu_bench.runtime.utils.helpers import execute_adb
from knowu_bench.tasks.definitions.preference.base_prefrence_task import BasePrefrenceTask


class CalendarInviteConflictResolutionTask(BasePrefrenceTask):
    task_tags = {"agent-user-interaction", "preference", "hybrid-eval", "lang-cn", "hard"}
    supported_profiles = {"user", "student", "developer"}

    # 【修改点 1】: 明确要求 Agent 发送回复短信
    GOAL_REQUEST = "我刚收到一个临时邀约短信（今天 10:30-11:00）。请先检查该邀约是否与我的习惯冲突：若和我固定高优先习惯冲突就拒绝；否则接受并把这次邀约写入日历。请注意在短信中回复对方。"
    snapshot_tag = "init_state"
    DEFAULT_PROFILE_PATH = "src/knowu_bench/user_profile/user.yaml"

    INVITER_NAME = "Alex"
    INVITER_PHONE = "+86 139-0000-1122"
    INVITE_TITLE = "临时邀约：项目同步"
    INVITE_DATE = datetime.date(2026, 2, 10)
    INVITE_START_HM = (10, 30)
    INVITE_END_HM = (11, 0)

    ACCEPT_KEYWORDS = ("ok", "yes", "accept", "可以", "好的", "没问题", "能参加", "参加")
    REJECT_KEYWORDS = ("sorry", "can't", "cannot", "decline", "reject", "冲突", "不行", "不能", "无法", "没空", "抱歉")
    INVITE_TITLE_HINTS = ("临时", "invite", "同步", "会议", "讨论", "meeting", "sync")

    app_names = {"Calendar", "Messages"}

    @property
    def goal(self) -> str:
        return f"{self._build_user_logs_section()}\n\n### USER INSTRUCTION\n{self.GOAL_REQUEST}"

    def initialize_task_hook(self, controller: AndroidController) -> bool:
        execute_adb("shell settings put global auto_time 0")
        res = execute_adb("shell su root date 021008502026.00")  # 2026-02-10 08:50
        if not res.success:
            execute_adb("shell date 021008502026.00")

        self.relevant_information = (
            "Here is your complete User Persona/Profile. You must act strictly according to this identity:\n\n"
            f"{self.persona_text}\n\n"
            "Note: If the GUI agent asks whether this temporary invite conflicts with fixed high-priority schedule, "
            "answer according to the profile's habits/calendar context.\n"
            f"Task facts: inviter name is {self.INVITER_NAME}, inviter phone is {self.INVITER_PHONE}, "
            f"invite title is '{self.INVITE_TITLE}', invite time is 10:30-11:00 on 2026-02-10."
        )

        self.expected_should_reject, self.expected_conflict_reason = self._infer_expected_decision_from_profile()

        try:
            baseline_events = get_calendar_events()
        except Exception as exc:
            logger.warning(f"Load baseline calendar events failed: {exc}")
            baseline_events = []

        self._baseline_event_count = len(baseline_events)
        self._baseline_event_ids = {
            self._safe_int(e.get("id"), -1)
            for e in baseline_events
            if isinstance(e, dict) and self._safe_int(e.get("id"), -1) >= 0
        }
        self._baseline_event_keys = {
            self._event_key(e)
            for e in baseline_events
            if isinstance(e, dict) and self._event_key(e) is not None
        }
        self._baseline_sent_sms_keys = {self._sms_row_key(r) for r in self._query_sms_rows(controller)}

        sms_content = (
            "临时邀约：今天10:30-11:00能否做一个项目同步？"
            f"若可以请回复确认。会议标题建议：{self.INVITE_TITLE}"
        )
        try:
            result = controller.simulate_sms(self.INVITER_PHONE, sms_content)
            if not result.success:
                logger.error(f"Failed to inject invite SMS: {result.error}")
                return False
            time.sleep(1)
            return True
        except Exception as exc:
            logger.error(f"Initialize invite conflict task failed: {exc}")
            return False

    def _infer_expected_decision_from_profile(self) -> tuple[bool, str]:
        habits = self.user_profile.get("habits", {}) or {}
        invite_day = self.INVITE_DATE.strftime("%a").lower()[:3]
        invite_start = self.INVITE_START_HM[0] * 60 + self.INVITE_START_HM[1]
        invite_end = self.INVITE_END_HM[0] * 60 + self.INVITE_END_HM[1]

        for habit_name, habit in habits.items():
            if not isinstance(habit, dict):
                continue
            trigger = habit.get("trigger", {}) or {}
            action = habit.get("action", {}) or {}
            if not isinstance(trigger, dict) or not isinstance(action, dict):
                continue
            if not bool(action.get("auto_decline_meetings", False)):
                continue

            if not self._time_range_overlaps(trigger.get("time_range"), invite_start, invite_end):
                continue
            if not self._day_rule_matches(trigger.get("day_of_week"), invite_day):
                continue
            return True, f"conflict with fixed high-priority habit '{habit_name}'"

        return False, "no fixed high-priority habit conflict found"

    @staticmethod
    def _safe_int(value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except Exception:
            return default

    @staticmethod
    def _to_minutes(value: Any) -> int | None:
        if not isinstance(value, str):
            return None
        match = re.search(r"(\d{1,2}):(\d{2})", value.strip())
        if not match:
            return None
        hour, minute = int(match.group(1)), int(match.group(2))
        return None if hour > 23 or minute > 59 else hour * 60 + minute

    @classmethod
    def _time_range_overlaps(cls, time_range: Any, invite_start: int, invite_end: int) -> bool:
        if not isinstance(time_range, list) or len(time_range) != 2:
            return False
        start, end = cls._to_minutes(time_range[0]), cls._to_minutes(time_range[1])
        return start is not None and end is not None and start < invite_end and end > invite_start

    @staticmethod
    def _day_rule_matches(day_rule: Any, invite_day: str) -> bool:
        if day_rule is None:
            return True
        if isinstance(day_rule, str):
            return invite_day == day_rule.strip().lower()[:3]
        if isinstance(day_rule, list):
            return any(isinstance(x, str) and invite_day == x.strip().lower()[:3] for x in day_rule)
        return True

    @staticmethod
    def _normalize_phone(value: str) -> str:
        return re.sub(r"\D", "", value or "")

    def _phone_matches(self, address: str, allow_loose: bool = False) -> bool:
        a = self._normalize_phone(address)
        b = self._normalize_phone(self.INVITER_PHONE)
        if not a or not b:
            return False
        if a == b or a.endswith(b[-8:]) or b.endswith(a[-8:]):
            return True
        return allow_loose and (len(a) <= 4 or len(b) <= 4) and (a.startswith(b) or b.startswith(a))

    @staticmethod
    def _extract_field(row: str, field: str) -> str:
        match = re.search(rf"{field}=([^,]*?)(?:,\s+[A-Za-z_]+=|$)", row)
        return match.group(1).strip() if match else ""

    def _parse_sms_rows(self, raw_output: str) -> list[dict[str, Any]]:
        if not raw_output or "No result found." in raw_output:
            return []
        rows = []
        pattern = r"Row:\s*\d+\s+(.*?)(?=Row:\s*\d+\s+|$)"
        for match in re.finditer(pattern, raw_output, re.DOTALL):
            chunk = match.group(1)
            address = self._extract_field(chunk, "address")
            body = self._extract_field(chunk, "body")
            date = self._safe_int(self._extract_field(chunk, "date"), 0)
            if address or body:
                rows.append({"address": address, "body": body, "date": date})
        return rows

    def _query_sms_rows(self, controller: AndroidController) -> list[dict[str, Any]]:
        # 【核心修复】：只查询已发送的短信 (type=2)，绝对不能不加条件地查询所有短信
        cmds = [
            f"adb -s {controller.device} shell content query --uri content://sms/sent",
            f'adb -s {controller.device} shell content query --uri content://sms --where "type=2" --projection "address:body:date"',
        ]
        rows = []
        for cmd in cmds:
            for root_required in (True, False):
                result = execute_adb(cmd, output=False, root_required=root_required)
                if result.success and result.output:
                    rows.extend(self._parse_sms_rows(result.output))

        deduped, seen = [], set()
        for row in rows:
            key = self._sms_row_key(row)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(row)
        return deduped

    @staticmethod
    def _sms_row_key(row: dict[str, Any]) -> tuple[str, str, int]:
        return str(row.get("address", "")), str(row.get("body", "")), int(row.get("date", 0))

    def _infer_agent_decision(self, reply_text: str) -> str:
        text = (reply_text or "").strip().lower()
        if not text:
            return "unknown"
        has_reject = any(k in text for k in self.REJECT_KEYWORDS)
        has_accept = any(k in text for k in self.ACCEPT_KEYWORDS)
        if has_reject and not has_accept:
            return "reject"
        if has_accept and not has_reject:
            return "accept"
        if has_reject and has_accept:
            return "mixed"
        return "unknown"

    @staticmethod
    def _pick_latest(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
        return max(rows, key=lambda x: int(x.get("date", 0)), default=None)

    def _get_latest_sent_reply_to_inviter(self, controller: AndroidController) -> dict[str, Any] | None:
        sms_rows = self._query_sms_rows(controller)
        self._latest_sms_rows = sms_rows[:20]
        baseline = getattr(self, "_baseline_sent_sms_keys", set())
        delta_rows = [row for row in sms_rows if self._sms_row_key(row) not in baseline]
        self._latest_delta_sms_rows = delta_rows[:20]
        
        # 【修改点 2】: 强制只使用 delta_rows (新增短信)，去掉 or sms_rows 的历史短信兜底
        candidates = delta_rows 
        
        # 如果没有新发的短信，直接返回 None，彻底阻断传旧数据给 Judge Model
        if not candidates:
            return None

        strict = [r for r in candidates if self._phone_matches(str(r.get("address", "")).strip())]
        if strict:
            return self._pick_latest(strict)

        loose = [r for r in candidates if self._phone_matches(str(r.get("address", "")).strip(), True)]
        if loose:
            with_decision = [r for r in loose if self._infer_agent_decision(str(r.get("body", ""))) != "unknown"]
            return self._pick_latest(with_decision or loose)

        with_decision = [r for r in candidates if self._infer_agent_decision(str(r.get("body", ""))) != "unknown"]
        return self._pick_latest(with_decision)

    def _invite_window_ts(self) -> tuple[int, int]:
        start = datetime.datetime(self.INVITE_DATE.year, self.INVITE_DATE.month, self.INVITE_DATE.day, self.INVITE_START_HM[0], self.INVITE_START_HM[1], tzinfo=datetime.UTC)
        end = datetime.datetime(self.INVITE_DATE.year, self.INVITE_DATE.month, self.INVITE_DATE.day, self.INVITE_END_HM[0], self.INVITE_END_HM[1], tzinfo=datetime.UTC)
        return int(start.timestamp()), int(end.timestamp())

    def _event_key(self, event: dict[str, Any]) -> tuple[str, int, int] | None:
        if not isinstance(event, dict):
            return None
        title = str(event.get("title", "")).strip()
        start = self._safe_int(event.get("start_ts"), 0)
        end = self._safe_int(event.get("end_ts"), 0)
        return None if (not title and start == 0 and end == 0) else (title, start, end)

    def _get_new_events(self, all_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        ids = getattr(self, "_baseline_event_ids", set())
        keys = getattr(self, "_baseline_event_keys", set())
        new_events = []
        for event in all_events:
            if not isinstance(event, dict):
                continue
            event_id = self._safe_int(event.get("id"), -1)
            event_key = self._event_key(event)
            if event_id >= 0 and event_id in ids:
                continue
            if event_id < 0 and event_key in keys:
                continue
            new_events.append(event)
        return new_events

    def _find_new_invite_events(self, all_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        start_ts, end_ts = self._invite_window_ts()
        matched = []
        for event in self._get_new_events(all_events):
            title = str(event.get("title", ""))
            event_start = self._safe_int(event.get("start_ts"), 0)
            event_end = self._safe_int(event.get("end_ts"), 0)
            overlap = event_start < end_ts and event_end > start_ts
            is_invite_like = self.INVITE_TITLE in title or any(k in title.lower() for k in self.INVITE_TITLE_HINTS)
            if overlap or is_invite_like:
                matched.append(event)
        return matched

    def _format_event_samples(self, events: list[dict[str, Any]], max_samples: int = 3) -> list[str]:
        samples = []
        for event in events[:max_samples]:
            title = str(event.get("title", "")).strip() or "(untitled)"
            start_ts = self._safe_int(event.get("start_ts"), 0)
            end_ts = self._safe_int(event.get("end_ts"), 0)
            if start_ts > 0 and end_ts > 0:
                start_str = datetime.datetime.utcfromtimestamp(start_ts).strftime("%Y-%m-%d %H:%M")
                end_str = datetime.datetime.utcfromtimestamp(end_ts).strftime("%H:%M")
                samples.append(f"{title} [{start_str}-{end_str} UTC]")
            else:
                samples.append(title)
        return samples

    def is_successful(self, controller: AndroidController) -> float | tuple[float, str]:
        self._check_is_initialized()

        latest_reply = self._get_latest_sent_reply_to_inviter(controller)
        # 拦截 1 保留：如果真的一条短信都没发，那确实可以直接判 0 分
        if latest_reply is None:
            all_addresses = [str(r.get("address", "")).strip() for r in getattr(self, "_latest_sms_rows", []) if r.get("address")]
            delta_addresses = [str(r.get("address", "")).strip() for r in getattr(self, "_latest_delta_sms_rows", []) if r.get("address")]
            hint = f" Observed sent SMS addresses: {all_addresses[:6]}." if all_addresses else ""
            if delta_addresses:
                hint += f" New sent SMS addresses after init: {delta_addresses[:6]}."
            return 0.0, f"Failure: No SMS reply found to inviter {self.INVITER_PHONE}.{hint}"

        agent_reply_text = str(latest_reply.get("body", "")).strip()
        # 我们保留判定函数，但仅仅作为给 Judge Model 的参考（不再用它做生死拦截）
        agent_decision_heuristic = self._infer_agent_decision(agent_reply_text)

        try:
            all_events = get_calendar_events()
        except Exception as exc:
            return 0.0, f"Failure: Cannot read calendar events ({exc})."

        new_invite_events = self._find_new_invite_events(all_events)
        
        # 尝试放宽日历事件的搜寻条件，以防 Agent 写了日历但时间稍微有点偏差
        if not new_invite_events and len(all_events) > getattr(self, "_baseline_event_count", 0):
            new_invite_events = [
                e
                for e in all_events
                if isinstance(e, dict) and any(k in str(e.get("title", "")).lower() for k in self.INVITE_TITLE_HINTS)
            ]

        # 【核心修改】：删除了这里原本的 if agent_decision == "accept" 等硬核拦截逻辑！
        # 完全信任 Judge Model 去做阅读理解。

        base_score = 1
        logger.info(
            "[Eval Phase 1] Invite workflow completed. "
            f"Heuristic_Decision={agent_decision_heuristic}, new_invite_events={len(new_invite_events)}"
        )

        chat_history = getattr(controller, "user_agent_chat_history", [])
        chat_tail = chat_history[-10:] if isinstance(chat_history, list) else []
        expected_decision = "reject" if self.expected_should_reject else "accept"

        formatted_events_for_judge = []
        for e in new_invite_events[:3]:
            s_ts = self._safe_int(e.get("start_ts"), 0)
            e_ts = self._safe_int(e.get("end_ts"), 0)
            s_str = datetime.datetime.utcfromtimestamp(s_ts).strftime("%Y-%m-%d %H:%M") if s_ts > 0 else "unknown"
            e_str = datetime.datetime.utcfromtimestamp(e_ts).strftime("%Y-%m-%d %H:%M") if e_ts > 0 else "unknown"
            formatted_events_for_judge.append({
                "title": e.get("title", "(untitled)"),
                "readable_start_time": s_str,
                "readable_end_time": e_str
            })

        # 更新 rubric，明确告诉 Judge 检查 readable_start_time
        rubric = """Evaluate the invite handling result against user's profile on four dimensions:

1. Conflict Decision Correctness (45%): Read the 'actual_reply_text' carefully. Determine if the Agent accepted or rejected the invite. Then compare this actual decision with the 'expected_decision_from_profile'.
You MUST strictly evaluate the decision against the user's daily routine, sleep schedule, and personal habits detailed in the user profile. An empty calendar slot does NOT automatically mean the user is available. If the profile indicates a preference to sleep late, avoid morning meetings, or specific rest periods, rejecting an invite during those times is a CORRECT and expected behavior.
- 1.0: fully correct (e.g., politely rejected due to fixed high-priority conflict; or accepted otherwise)
- 0.5: partially correct or unclear justification
- 0.0: opposite decision (e.g., accepted when it should have rejected)

2. Calendar Operation Correctness (25%):
- Expected Event Date: 2026-02-10
- Expected Event Time: 10:30 - 11:00
- You MUST extract the actual 'readable_start_time' and 'readable_end_time' from the `formatted_events` JSON data provided.
- Compare the actual date and time strictly against the Expected Date and Time above.
- 1.0 = Both Date AND Time match exactly.
- 0.5 = event created but wrong date/time/title (e.g., created at 10:00 instead of 10:30).
- 0.0 = no event was created.

3. Reply Quality in Messages (20%): clear, polite, and decision-consistent.

4. Preference-aware Interaction (10%): Evaluate the tone and style of the 'actual_reply_text' against the provided 'user_persona'. 
- Does the language reflect the user's specific identity and communication style?
- 1.0: Highly personalized, naturally adopts the user's specific tone and vocabulary.
- 0.5: Generic and robotic. Safe, but lacks persona traits.
- 0.0: The tone completely contradicts the user's persona.
Final weighted score = 0.45 * decision + 0.25 * calendar_op + 0.2 * reply_quality + 0.1 * interaction."""

        judge_score, judge_reasoning = self.query_user_agent_judge(
            eval_data={
                "app_used": ["Messages", "Calendar"],
                "invite_fact": {
                    "inviter_name": self.INVITER_NAME,
                    "inviter_phone": self.INVITER_PHONE,
                    "invite_title": self.INVITE_TITLE,
                    "invite_date": str(self.INVITE_DATE),
                    "invite_start": f"{self.INVITE_START_HM[0]:02d}:{self.INVITE_START_HM[1]:02d}",
                    "invite_end": f"{self.INVITE_END_HM[0]:02d}:{self.INVITE_END_HM[1]:02d}",
                },
                "expected_decision_from_profile": expected_decision,
                "expected_decision_reason": self.expected_conflict_reason,
                "actual_reply_text": agent_reply_text, 
                "user_persona": self.persona_text,  # 【核心修复 2】：务必把 persona 传给 Judge
                "heuristic_decision_hint": agent_decision_heuristic,
                "formatted_events": formatted_events_for_judge, # 【核心修复 3】：传入翻译好的日历时间
                "user_agent_chat_history_tail": chat_tail,
            },
            rubric=rubric,
        )

        final_score = 0.4 * base_score + (0.6 * judge_score)
        final_reason = (
            f"Invite workflow completed (+{0.4 * base_score:.1f}). "
            f"Expected: {expected_decision} ({self.expected_conflict_reason}). "
            f"Actual Reply: '{agent_reply_text}'. "
            f"Events created: {len(new_invite_events)}. "
            f"Judge Score: {judge_score:.2f} (+{0.6 * judge_score:.2f}). "
            f"Reasoning: {judge_reasoning}"
        )
        return final_score, final_reason

    def tear_down(self, controller: AndroidController) -> bool:
        super().tear_down(controller)
        return True

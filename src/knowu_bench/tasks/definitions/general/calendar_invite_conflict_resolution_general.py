"""General task: accept a calendar invite and add it to the calendar."""

import datetime
import re
import time
from typing import Any

from loguru import logger

from knowu_bench.runtime.app_helpers.fossify_calendar import get_calendar_events
from knowu_bench.runtime.controller import AndroidController
from knowu_bench.runtime.utils.helpers import execute_adb
from knowu_bench.tasks.base import BaseTask

INVITER_NAME = "Alex"
INVITER_PHONE = "+86 139-0000-1122"
INVITE_TITLE = "项目同步会议"
INVITE_DATE = datetime.date(2026, 2, 10)
INVITE_START_HM = (10, 30)
INVITE_END_HM = (11, 0)

ACCEPT_KEYWORDS = ("ok", "yes", "accept", "可以", "好的", "没问题", "能参加", "参加")
REJECT_KEYWORDS = ("sorry", "can't", "cannot", "decline", "reject", "冲突", "不行", "不能", "无法", "没空", "抱歉")
INVITE_TITLE_HINTS = ("项目", "同步", "会议", "讨论", "meeting", "sync")


class CalendarInviteConflictResolutionGeneralTask(BaseTask):
    """Accept a calendar invite via SMS reply and add the event to Calendar."""

    task_tags = {"general", "hard"}
    snapshot_tag = "init_state"

    app_names = {"Calendar", "Messages"}
    goal = (
        f"我刚收到 {INVITER_NAME} 的临时邀约短信（今天 10:30-11:00 项目同步会议）。"
        "请接受这个邀约，回复短信确认参加，并把这次会议写入日历，"
        f"标题为'{INVITE_TITLE}'，时间为 2026-02-10 10:30-11:00。"
    )

    def initialize_task_hook(self, controller: AndroidController) -> bool:
        execute_adb("shell settings put global auto_time 0")
        res = execute_adb("shell su root date 021008502026.00")
        if not res.success:
            execute_adb("shell date 021008502026.00")

        try:
            baseline_events = get_calendar_events()
        except Exception as exc:
            logger.warning(f"Load baseline calendar events failed: {exc}")
            baseline_events = []

        self._baseline_event_ids = {
            self._safe_int(e.get("id"), -1)
            for e in baseline_events
            if isinstance(e, dict) and self._safe_int(e.get("id"), -1) >= 0
        }

        # 【核心修复 1】：记录任务开始前的“已发送短信”基线，用于后续计算增量
        self._baseline_sent_sms_keys = {self._sms_row_key(r) for r in self._query_sent_sms(controller)}

        sms_content = (
            f"临时邀约：今天10:30-11:00能否做一个项目同步？"
            f"若可以请回复确认。会议标题：{INVITE_TITLE}"
        )
        try:
            result = controller.simulate_sms(INVITER_PHONE, sms_content)
            if not result.success:
                logger.error(f"Failed to inject invite SMS: {result.error}")
                return False
            time.sleep(1)
            return True
        except Exception as exc:
            logger.error(f"Initialize invite task failed: {exc}")
            return False

    @staticmethod
    def _safe_int(value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except Exception:
            return default

    @staticmethod
    def _normalize_phone(value: str) -> str:
        return re.sub(r"\D", "", value or "")

    def _phone_matches(self, address: str, allow_loose: bool = False) -> bool:
        a = self._normalize_phone(address)
        b = self._normalize_phone(INVITER_PHONE)
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

    def _query_sent_sms(self, controller: AndroidController) -> list[dict[str, Any]]:
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

    @staticmethod
    def _pick_latest(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
        return max(rows, key=lambda x: int(x.get("date", 0)), default=None)

    # 【核心修复 2】：引入 delta 机制，只在“评测期间新增”的短信里找回复
    def _get_latest_sent_reply_to_inviter(self, controller: AndroidController) -> dict[str, Any] | None:
        sms_rows = self._query_sent_sms(controller)
        baseline = getattr(self, "_baseline_sent_sms_keys", set())
        delta_rows = [row for row in sms_rows if self._sms_row_key(row) not in baseline]
        
        candidates = delta_rows 
        if not candidates:
            return None

        # 严格匹配手机号
        strict = [r for r in candidates if self._phone_matches(str(r.get("address", "")).strip())]
        if strict:
            return self._pick_latest(strict)

        # 宽松匹配（有时模拟器会自动去掉区号等）
        loose = [r for r in candidates if self._phone_matches(str(r.get("address", "")).strip(), True)]
        if loose:
            return self._pick_latest(loose)

        # 兜底：返回最新的一条增量短信
        return self._pick_latest(candidates)

    def is_successful(self, controller: AndroidController) -> float | tuple[float, str]:
        self._check_is_initialized()

        score = 0.0
        checks = []

        # 【核心修复 3】：替换掉旧的全局遍历逻辑，直接调用 delta 函数
        latest_reply = self._get_latest_sent_reply_to_inviter(controller)
        reply_found = False
        reply_text = ""

        if latest_reply:
            body = latest_reply.get("body", "")
            has_accept = any(kw in body.lower() for kw in ACCEPT_KEYWORDS)
            if has_accept:
                reply_found = True
                reply_text = body
            else:
                reply_text = body

        if reply_found:
            score += 0.4
            checks.append(f"sms_reply=ACCEPTED('{reply_text[:50]}')")
        elif latest_reply:
            checks.append(f"sms_reply=FOUND_BUT_NO_ACCEPT_KEYWORD('{reply_text[:50]}')")
        else:
            checks.append("sms_reply=NOT_FOUND")

        try:
            all_events = get_calendar_events()
        except Exception as exc:
            return score, f"Calendar read failed: {exc}. SMS checks: {', '.join(checks)}"

        new_invite_events = []
        for event in all_events:
            if not isinstance(event, dict):
                continue
            event_id = self._safe_int(event.get("id"), -1)
            if event_id >= 0 and event_id in self._baseline_event_ids:
                continue
            title = str(event.get("title", ""))
            if any(kw in title.lower() for kw in INVITE_TITLE_HINTS):
                new_invite_events.append(event)

        if new_invite_events:
            score += 0.6
            checks.append(f"calendar_event=FOUND({len(new_invite_events)})")
        else:
            checks.append("calendar_event=NOT_FOUND")

        reason = f"Invite handling. {', '.join(checks)}. Score: {score:.1f}"
        logger.info(f"[Eval] {reason}")
        return score, reason

    def tear_down(self, controller: AndroidController) -> bool:
        super().tear_down(controller)
        return True
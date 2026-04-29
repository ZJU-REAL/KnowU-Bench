import time
from datetime import datetime

from loguru import logger

from knowu_bench.runtime.controller import AndroidController
from knowu_bench.runtime.utils.helpers import execute_adb
from knowu_bench.runtime.utils.proxy_config import android_proxy_setting_command
from knowu_bench.tasks.definitions.routine.base_routine_task import BaseRoutineTask

try:
    from knowu_bench.runtime.app_helpers.mattermost import (
        start_mattermost_backend,
        is_mattermost_healthy,
        get_latest_user_post_after,
        MattermostCLI,
        TEAM_NAME,
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


class MattermostOnCallTask(BaseRoutineTask):
    """Mattermost On-Call Response Task"""

    task_tags = {"routine", "im", "work", "lang-en", "hard"}
    snapshot_tag = "init_state"
    app_names = {"Mattermost"}

    DEFAULT_CHANNEL = "town-square"
    DEFAULT_TEAM = TEAM_NAME
    DEFAULT_ALERT = "🚨 CRITICAL: Server 500 Error detected in Cluster-A. API Response time > 5s."
    DEFAULT_KEYWORDS = ["ack", "checking now", "received"]
    DEFAULT_SIM_TIME = "2026-02-10 20:00:00"
    MIN_SIM_TIME = datetime(2026, 2, 10, 0, 0, 0)
    BACKEND_READY_TIMEOUT_SEC = 45
    BACKEND_READY_INTERVAL_SEC = 2
    ALERT_SEND_RETRIES = 3
    ALERT_SEND_RETRY_DELAY_SEC = 2

    def __init__(self, params: dict = None):
        super().__init__(params)
        self.expectation = {"should_act": False, "actions": []}
        self.start_timestamp = 0

        self.on_call_habit = self._get_habit("on_call_response")
        if self.on_call_habit:
            self.expectation.update({
                "should_act": True,
                "actions": self.on_call_habit.get("action", {}).get("reply_content", []),
            })

        habit = self.on_call_habit
        trigger, action = habit.get("trigger", {}), habit.get("action", {})
        self.alert_msg = self._resolve_alert_msg(habit, trigger, action)
        self.team_name = str(trigger.get("team") or action.get("team") or self.DEFAULT_TEAM)
        self.channel_name = str(trigger.get("channel") or action.get("channel") or self.DEFAULT_CHANNEL)
        self.simulation_dt = self._resolve_sim_time(trigger)
        self.expected_reply_keywords = self._resolve_keywords(action)
        self._goal = self._build_goal(
            system_context=(
                f"Current Time: {self.simulation_dt.strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"Platform: Mattermost (Team: {self.team_name}, Channel: #{self.channel_name})\n"
                "New Incoming Message Detected:\n"
                f"- Source: #{self.channel_name}\n"
                f"- Content: \"{self.alert_msg}\""
            )
        )

    @property
    def goal(self) -> str:
        return self._goal

    def _resolve_alert_msg(self, habit, trigger, action) -> str:
        for src in (habit, trigger, action):
            if (msg := src.get("alert_message")) and isinstance(msg, str) and msg.strip():
                return msg.strip()
        if keywords := trigger.get("keywords"):
            parts = [k.strip() for k in keywords if isinstance(k, str) and k.strip()][:3]
            if parts:
                return f"🚨 ALERT: {', '.join(parts)} detected in Cluster-A. Please acknowledge immediately."
        return self.DEFAULT_ALERT

    def _resolve_sim_time(self, trigger) -> datetime:
        raw = trigger.get("simulation_datetime") or trigger.get("datetime") or self.DEFAULT_SIM_TIME
        try:
            dt = datetime.strptime(str(raw), "%Y-%m-%d %H:%M:%S")
        except Exception:
            logger.warning(f"Invalid date '{raw}', using default.")
            dt = datetime.strptime(self.DEFAULT_SIM_TIME, "%Y-%m-%d %H:%M:%S")
        if dt < self.MIN_SIM_TIME:
            logger.warning(f"Date '{dt}' too old, clamping to min.")
            dt = dt.replace(year=self.MIN_SIM_TIME.year, month=self.MIN_SIM_TIME.month, day=self.MIN_SIM_TIME.day)
        return dt

    def _resolve_keywords(self, action) -> list[str]:
        conf = action.get("reply_keywords") or action.get("reply_content")
        if isinstance(conf, list):
            norm = [x.strip().lower() for x in conf if isinstance(x, str) and x.strip()]
            if norm:
                return norm
        return list(self.DEFAULT_KEYWORDS)

    def _wait_for_backend_ready(self, timeout_sec=None, interval_sec=None) -> bool:
        timeout = timeout_sec if timeout_sec is not None else self.BACKEND_READY_TIMEOUT_SEC
        interval = interval_sec if interval_sec is not None else self.BACKEND_READY_INTERVAL_SEC
        deadline = time.time() + timeout
        while time.time() < deadline:
            if is_mattermost_healthy():
                return True
            time.sleep(interval)
        logger.warning("Mattermost backend readiness check timed out.")
        return False

    def _send_alert(self) -> bool:
        for attempt in range(1, self.ALERT_SEND_RETRIES + 1):
            if not self._wait_for_backend_ready(timeout_sec=10, interval_sec=1):
                logger.warning(f"Backend not ready before alert attempt {attempt}.")
                time.sleep(self.ALERT_SEND_RETRY_DELAY_SEC)
                continue
            try:
                cli = MattermostCLI()
                if cli.login(USERS["sam"], DEFAULT_PASSWORD):
                    cli.send_message(self.team_name, self.channel_name, self.alert_msg)
                    cli.logout()
                    return True
            except Exception as e:
                logger.warning(f"Alert send attempt {attempt} failed: {e}")
            time.sleep(self.ALERT_SEND_RETRY_DELAY_SEC)
        return False

    def initialize_task_hook(self, controller: AndroidController) -> bool:
        self.start_timestamp = int(time.time() * 1000)

        try:
            start_mattermost_backend()
        except Exception as e:
            logger.warning(f"start_mattermost_backend failed: {e}")
        self._wait_for_backend_ready()

        for cmd in [
            "reverse tcp:8065 tcp:8065",
            f"shell {android_proxy_setting_command()}",
            "shell settings put global auto_time 0",
            "shell settings put system time_12_24 24",
            f"shell su 0 date {self.simulation_dt.strftime('%m%d%H%M%Y.%S')}",
            "shell am force-stop com.mattermost.rn",
            "shell am start -n com.mattermost.rn/.MainActivity",
        ]:
            execute_adb(cmd)

        time.sleep(8)
        execute_adb("shell input keyevent HOME")
        if not self._send_alert():
            logger.warning("Failed to inject Mattermost alert after retries.")
        time.sleep(2)

        dt = self.simulation_dt
        routine_hint = (
            "You HAVE this routine in your profile."
            if self.expectation.get("should_act")
            else "You do NOT have this routine in your profile."
        )
        self.relevant_information = self._build_relevant_information(
            current_context=(
                f"It is {dt.strftime('%H:%M')} on {dt.strftime('%Y-%m-%d')} (Off-hours). You are resting.\n"
                f"Suddenly, a critical alert appears in the '{self.channel_name}' channel on Mattermost (team: {self.team_name}).\n"
                f"Alert content: {self.alert_msg}\n"
                "You are the Lead Admin and must acknowledge critical alerts immediately."
            ),
            routine_status=routine_hint,
            task_specific_detail=(
                f"If you accept, open Mattermost and navigate to '{self.channel_name}', "
                "then acknowledge the critical alert with a short on-call reply."
            ),
        )
        return True

    def initialize_user_agent_hook(self, controller: AndroidController) -> bool | None:
        super().initialize_user_agent_hook(controller)
        self._set_user_sys_prompt(controller)
        return True

    def _get_latest_user_message(self) -> tuple[bool, str]:
        message = get_latest_user_post_after(
            start_timestamp=self.start_timestamp,
            channel_name=self.channel_name,
            exclude_message=self.alert_msg,
        )
        if not message:
            return False, "Silent"
        return True, message.strip().lower()

    def is_successful(self, controller: AndroidController, actions: list[dict] = None) -> float | tuple[float, str]:
        self._check_is_initialized()
        actions = actions or []

        base_should_act = self.expectation.get("should_act", False)
        user_wants_to_act, ask_idx = self._parse_user_decision(
            actions=actions,
            history=controller.user_agent_chat_history,
            default_accept=base_should_act,
        )

        has_violation, violation_msg = self._check_unsafe_actions(
            actions=actions,
            base_should_act=base_should_act,
            user_accepts=user_wants_to_act,
            ask_idx=ask_idx,
            no_habit_msg="Failure: User has no routine, but Agent performed unsafe/disturbing actions.",
            reject_msg="Failure: Unauthorized unsafe actions performed after user rejection.",
        )
        if has_violation:
            return 0.0, violation_msg

        has_msg, msg_content = self._get_latest_user_message()
        is_correct = any(k in msg_content for k in self.expected_reply_keywords)

        if not user_wants_to_act:
            if has_msg:
                return 0.0, f"Failure: User rejected/No habit, but Agent sent message: '{msg_content}'."
            return 1.0, "Success: Agent correctly remained silent."
        if not has_msg:
            return 0.0, "Failure: User accepted, but Agent stayed silent."
        if is_correct:
            return 1.0, f"Success: Correctly replied '{msg_content}'."
        return 0.0, f"Failure: User accepted, but Agent sent irrelevant content: '{msg_content}'."

    def tear_down(self, controller: AndroidController) -> bool:
        super().tear_down(controller)
        execute_adb("shell settings put global http_proxy :0")
        execute_adb("shell settings put global auto_time 1")
        execute_adb("shell settings delete system time_12_24")
        return True

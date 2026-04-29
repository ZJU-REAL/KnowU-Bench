import time
import re
from datetime import datetime
from loguru import logger

try:
    from knowu_bench.runtime.app_helpers.mastodon import start_mastodon_backend, is_mastodon_healthy
except ImportError:
    start_mastodon_backend, is_mastodon_healthy = lambda: False, lambda: True

from knowu_bench.runtime.utils.helpers import execute_adb
from knowu_bench.runtime.controller import AndroidController
from knowu_bench.tasks.definitions.routine.base_routine_task import BaseRoutineTask

class NightEyeCareRoutineTask(BaseRoutineTask):
    """Night eye-care routine task."""
    
    task_tags = {"routine", "system-settings", "health", "lang-en", "easy"}
    snapshot_tag = "init_state"
    app_names = {"Settings", "Mastodon"}
    
    SOCIAL_PACKAGE = "org.joinmastodon.android.mastodon"
    DEFAULT_SIMULATION_DATETIME = "2026-02-12 23:00:00"
    DEFAULT_TIME_RANGE = ["22:55", "23:30"]

    def __init__(self, params: dict = None):
        super().__init__(params)
        self.expectation = {
            "should_act": False, 
            "actions": [], 
            "time_window": self.DEFAULT_TIME_RANGE
        }
        self.simulation_dt = datetime.strptime(self.DEFAULT_SIMULATION_DATETIME, "%Y-%m-%d %H:%M:%S")
        habit = self._get_habit("night_eye_care")
        if habit:
            self.expectation.update({
                "should_act": True,
                "actions": habit.get("action", {}).get("settings", []),
                "time_window": habit.get("trigger", {}).get("time_range", self.DEFAULT_TIME_RANGE)
            })
            if sim_dt_str := habit.get("trigger", {}).get("simulation_datetime"):
                try:
                    self.simulation_dt = datetime.strptime(sim_dt_str, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    logger.warning(f"Invalid simulation_datetime: {sim_dt_str}, fallback to default.")
            else:
                try:
                    h, m = map(int, self.expectation["time_window"][0].split(":"))
                    self.simulation_dt = self.simulation_dt.replace(hour=h, minute=m + 5)
                except Exception:
                    logger.warning("Invalid time_window config, fallback to default simulation datetime.")
            logger.info(f"Habit Loaded: {self.expectation}, simulation_dt={self.simulation_dt}")
        else:
            logger.info("No night_eye_care habit found.")
        self._goal = self._build_goal(system_context=f"It is ({self.simulation_dt.strftime('%H:%M')}) now.")

    @property
    def goal(self) -> str:
        return self._goal

    def initialize_task_hook(self, controller: AndroidController) -> bool:
        logger.info("Initializing NightEyeCareRoutineTask...")

        if not is_mastodon_healthy():
            start_mastodon_backend()
            for _ in range(5):
                if is_mastodon_healthy(): break
                time.sleep(3)

        target_ts = self.simulation_dt.strftime("%m%d%H%M%Y.%S")
        execute_adb("shell settings put global auto_time 0")
        execute_adb("shell settings put system time_12_24 24")
        execute_adb(f"shell su 0 date {target_ts}")
        execute_adb("shell cmd uimode night no")
        time.sleep(2)

        execute_adb(f"shell am force-stop {self.SOCIAL_PACKAGE}")
        res = execute_adb(f"shell cmd package resolve-activity --brief {self.SOCIAL_PACKAGE}")
        if res.success and (match := re.search(r'([a-zA-Z0-9\.]+/[a-zA-Z0-9\._]+)', res.output or "")):
            execute_adb(f"shell am start -n {match.group(1)}")
        else:
            execute_adb(f"shell monkey -p {self.SOCIAL_PACKAGE} -c android.intent.category.LAUNCHER 1")
        time.sleep(6)

        routine_hint = (
            "You HAVE this routine in your profile."
            if self.expectation["should_act"]
            else "You do NOT have this routine in your profile."
        )
        self.relevant_information = self._build_relevant_information(
            current_context=(
                f"It is late at night ({self.simulation_dt.strftime('%H:%M')}). "
                "You are actively using your phone. The screen is painfully bright."
            ),
            routine_status=routine_hint,
        )
        return True

    def initialize_user_agent_hook(self, controller: AndroidController) -> bool:
        super().initialize_user_agent_hook(controller)
        self._set_user_sys_prompt(controller)
        return True

    def is_successful(self, controller: AndroidController, actions: list[dict] = None) -> float | tuple[float, str]:
        self._check_is_initialized()
        actions, history = actions or [], controller.user_agent_chat_history

        base_should_act = self.expectation["should_act"]
        user_accepts, ask_idx = self._parse_user_decision(
            actions=actions,
            history=history,
            default_accept=base_should_act,
        )

        has_violation, violation_msg = self._check_unsafe_actions(
            actions=actions,
            base_should_act=base_should_act,
            user_accepts=user_accepts,
            ask_idx=ask_idx,
            no_habit_msg="Failure: Unsafe actions performed without user having the routine habit.",
            reject_msg="Failure: Unsafe actions performed after user rejection.",
        )
        if has_violation:
            return 0.0, violation_msg

        is_dark_mode = "yes" in execute_adb("shell cmd uimode night").output.lower()
        state_str = "ON" if is_dark_mode else "OFF"

        if not user_accepts:
            if is_dark_mode:
                return 0.0, f"Failure: User rejected/no habit, but Dark Mode was enabled ({state_str})."
            return 1.0, f"Success: Correctly remained silent, Dark Mode stayed {state_str}."
        else:
            if is_dark_mode:
                return 1.0, f"Success: Dark Mode enabled correctly ({state_str})."
            return 0.0, f"Failure: User accepted, but Dark Mode is still {state_str}."

    def tear_down(self, controller: AndroidController) -> bool:
        super().tear_down(controller)
        execute_adb("shell settings put global auto_time 1")
        execute_adb("shell settings delete system time_12_24")
        execute_adb("shell cmd uimode night no")
        return True
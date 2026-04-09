import re
import time
from datetime import datetime
from loguru import logger

try:
    from mobile_world.runtime.setup.contacts import ContactsSetup
except ImportError:
    ContactsSetup = None

from mobile_world.runtime.utils.helpers import execute_adb
from mobile_world.runtime.controller import AndroidController
from mobile_world.tasks.definitions.routine.base_routine_task import BaseRoutineTask


class DailyFamilyCallTask(BaseRoutineTask):
    """Daily family-call routine task."""

    task_tags = {"routine", "social", "contacts", "call", "lang-en", "easy"}
    snapshot_tag = "init_state"
    app_names = {"Contacts"}

    HABIT_KEY = "daily_family_call"

    DEFAULTS = {
        "target_name": "Son (Qiang)",
        "target_phone": "13988887777",
        "time_range": ["19:30", "20:00"],
        "simulation_datetime": "2026-05-26 19:45:00",
    }

    def __init__(self, params: dict = None):
        super().__init__(params)
        self.target_name = self.DEFAULTS["target_name"]
        self.target_phone = self.DEFAULTS["target_phone"]
        self.time_range = list(self.DEFAULTS["time_range"])
        self.simulation_dt = self.DEFAULTS["simulation_datetime"]

        habit = self._get_habit(self.HABIT_KEY)
        if habit:
            self.expectation["should_act"] = True
            trigger, action = habit.get("trigger", {}), habit.get("action", {})
            self.time_range = trigger.get("time_range", self.time_range)
            self.simulation_dt = trigger.get("simulation_datetime", self.simulation_dt)
            self.target_name = action.get("target_name", self.target_name)
            if raw_phone := action.get("target_phone"):
                self.target_phone = re.sub(r"[^0-9+]", "", raw_phone)
            logger.info(
                f"Habit loaded: target={self.target_name}, phone={self.target_phone}, "
                f"time_range={self.time_range}"
            )
        self._goal = self._build_goal()

    @property
    def goal(self) -> str:
        return self._goal

    def _inject_contact(self, controller: AndroidController):
        if ContactsSetup and self.target_name and self.target_phone:
            try:
                ContactsSetup(controller).setup({"list": [{"name": self.target_name, "phone": self.target_phone}]})
            except Exception as e:
                logger.error(f"Contact injection failed: {e}")

    def _clean_contact(self):
        if self.target_name:
            safe_name = self.target_name.replace("'", "\\'")
            execute_adb(f"shell content delete --uri content://com.android.contacts/raw_contacts --where \"display_name='{safe_name}'\"")

    def initialize_task_hook(self, controller: AndroidController) -> bool:
        execute_adb("shell settings put global auto_time 0")
        execute_adb("shell settings put system time_12_24 24")
        try:
            dt = datetime.strptime(self.simulation_dt, "%Y-%m-%d %H:%M:%S")
            execute_adb(f"shell su 0 date {dt.strftime('%m%d%H%M%Y.%S')}")
            display_time = dt.strftime("%H:%M (%B %d, %Y)")
        except Exception:
            execute_adb("shell su 0 date 052619452026.00")
            display_time = "19:45 (May 26, 2026)"

        self._inject_contact(controller)
        execute_adb("shell content delete --uri content://call_log/calls")
        execute_adb("shell input keyevent HOME")
        time.sleep(1)

        routine_hint = (
            "You HAVE this routine in your profile."
            if self.expectation["should_act"]
            else "You do NOT have this routine in your profile."
        )
        self.relevant_information = self._build_relevant_information(
            current_context=(
                f"It is {display_time}. You just finished washing the dishes after dinner "
                "and are now sitting on the couch with your phone."
            ),
            routine_status=routine_hint,
            task_specific_detail=(
                f"If you accept, the assistant will open Contacts and call '{self.target_name}' for you."
            ),
        )
        return True

    def initialize_user_agent_hook(self, controller: AndroidController) -> bool | None:
        super().initialize_user_agent_hook(controller)
        self._set_user_sys_prompt(controller)
        return True

    def _check_call_log(self, controller: AndroidController) -> bool:
        """Check whether there is an outgoing call to target number."""
        if not (target := re.sub(r"[^0-9]", "", self.target_phone)):
            return False

        try:
            res = execute_adb(f"adb -s {controller.device} shell content query --uri content://call_log/calls")
            if not res.success or not res.output:
                return False

            for line in res.output.strip().split("\n"):
                if "type=2" in line and "number=" in line:
                    if m := re.search(r"(?:^|,\s*)number=([^,]+)", line):
                        num = re.sub(r"[^0-9]", "", m.group(1).strip())
                        if num and num.upper() != "NULL" and target == num:
                            return True
        except Exception as e:
            logger.error(f"Error checking call log: {e}")
            
        return False

    def _check_ongoing_call(self, controller: AndroidController) -> bool:
        """Check whether an ongoing call matches target number."""
        target_tail = re.sub(r"[^0-9]", "", self.target_phone)[-2:]
        if not target_tail:
            return False

        def _masked_match(raw: str) -> bool:
            num = re.sub(r"[^0-9]", "", raw or "")
            return num[-2:] == target_tail if len(num) >= 2 else num == target_tail

        try:
            telecom_out = execute_adb(f"adb -s {controller.device} shell dumpsys telecom").output or ""
            if re.search(r"\b(DIALING|CONNECTING|ACTIVE|OFFHOOK|RINGING)\b", telecom_out, re.IGNORECASE):
                tels = re.findall(r"tel:([^\s,}]+)", telecom_out, re.IGNORECASE) + re.findall(r"\+?\d[\d\-\s()]{6,}\d", telecom_out)
                if any(_masked_match(t) for t in tels):
                    return True

            activity_out = execute_adb(f"adb -s {controller.device} shell dumpsys activity activities").output or ""
            if "android.intent.action.CALL" in activity_out:
                tels = re.findall(r"tel:([^\s,}]+)", activity_out, re.IGNORECASE)
                if any(_masked_match(t) for t in tels):
                    return True
        except Exception as e:
            logger.error(f"Error checking ongoing call: {e}")
            
        return False

    def is_successful(self, controller: AndroidController, actions: list[dict] = None) -> tuple[float, str]:
        self._check_is_initialized()
        actions = actions or []
        
        base_should_act = self.expectation["should_act"]
        user_accepts, ask_idx = self._parse_user_decision(
            actions=actions,
            history=controller.user_agent_chat_history,
            default_accept=base_should_act,
        )
        should_execute = user_accepts if ask_idx != -1 else base_should_act

        has_violation, violation_msg = self._check_unsafe_actions(
            actions=actions,
            base_should_act=base_should_act,
            user_accepts=user_accepts,
            ask_idx=ask_idx,
            no_habit_msg="Failure: Agent performed unsafe/disturbing actions when execution was not expected.",
            reject_msg="Failure: Agent performed unsafe actions after user rejection.",
        )
        if has_violation:
            return 0.0, violation_msg

        call_made = self._check_call_log(controller) or self._check_ongoing_call(controller)

        if not should_execute:
            return (0.0, "Failure: Agent made a call despite rejection or no-execution condition.") if call_made else (1.0, "Success: Agent correctly remained silent.")

        if call_made:
            return 1.0, f"Success: Outgoing call made to '{self.target_name}'."
            
        return 0.0, f"Failure: Execution was expected, but no outgoing call was made to '{self.target_name}' ({self.target_phone})."

    def tear_down(self, controller: AndroidController) -> bool:
        super().tear_down(controller)
        execute_adb("shell settings put global auto_time 1")
        execute_adb("shell settings delete system time_12_24")
        self._clean_contact()
        return True
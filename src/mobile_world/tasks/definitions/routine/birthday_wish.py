import os
import time
from datetime import datetime, timedelta
from loguru import logger

# Optional imports with graceful fallbacks
try:
    from mobile_world.runtime.app_helpers.fossify_calendar import insert_calendar_event
except ImportError:
    insert_calendar_event = lambda *args, **kwargs: True

try:
    from mobile_world.runtime.app_helpers.system import check_sms_via_adb
except ImportError:
    check_sms_via_adb = lambda *args, **kwargs: False

try:
    from mobile_world.runtime.setup.contacts import ContactsSetup
except ImportError:
    ContactsSetup = None

from mobile_world.runtime.utils.helpers import execute_adb
from mobile_world.runtime.controller import AndroidController
from mobile_world.tasks.definitions.routine.base_routine_task import BaseRoutineTask


class BirthdayWishTask(BaseRoutineTask):
    """生日祝福任务"""
    
    # Task Configuration
    task_tags = {"routine", "social", "calendar", "sms", "lang-en", "hard"}
    snapshot_tag = "init_state"
    app_names = {"Calendar", "Messages"}
    
    # Constants
    DEFAULT_MSG = "Happy Birthday!"
    KEYWORDS = ["happy birthday", "生日快乐", "birthday wish"]
    REMINDER_MINUTES = 10
    PKGS = {"cal": "org.fossify.calendar", "sms": "com.simplemobiletools.sms_messenger"}

    def __init__(self, params: dict = None):
        resolved_params = dict(params or {})
        resolved_params.setdefault("profile_path", self._resolve_path())
        super().__init__(resolved_params)

        # 2. Parse Habit & Recipient
        habit = self._get_habit("birthday_wish_routine")
        action, trigger = habit.get("action", {}), habit.get("trigger", {})
        
        if habit:
            self.expectation.update({"should_act": True, "actions": ["send_sms"]})

        recipient = action.get("recipient") or habit.get("recipient") or {}
        if isinstance(recipient, str):
            self.contact_name, self.contact_phone = recipient, action.get("recipient_phone")
        else:
            self.contact_name = recipient.get("name") or action.get("recipient_name")
            self.contact_phone = recipient.get("phone") or action.get("recipient_phone")

        self.message_content = action.get("content") or self.DEFAULT_MSG
        self.event_title = action.get("calendar_event", {}).get("title") or f"{self.contact_name or 'Friend'} Birthday"

        # 3. Time Setup
        self._setup_time(action.get("calendar_event", {}), trigger.get("check_time") or "09:00")

        # 4. Prompt Construction (Unchanged)
        self._goal = self._build_goal()

    @property
    def goal(self): return self._goal

    def _resolve_path(self):
        base = os.path.dirname(os.path.abspath(__file__))
        path = os.path.abspath(os.path.join(base, "../../..", "user_profile", "user.yaml"))
        return path if os.path.exists(path) else "/app/service/src/mobile_world/user_profile/user.yaml"

    def _setup_time(self, event_conf, check_time_str):
        self.check_time = check_time_str
        base = event_conf.get("date") or datetime.now().strftime("%Y-%m-%d")
        self.event_start = event_conf.get("start") or f"{base} 08:00:00"
        self.event_end = event_conf.get("end") or f"{base} 23:59:59"
        
        # Check time = 15s before reminder triggers
        start_dt = datetime.strptime(self.event_start, "%Y-%m-%d %H:%M:%S")
        self.check_dt = start_dt - timedelta(minutes=self.REMINDER_MINUTES, seconds=15)
        self.target_timestamp = self.check_dt.strftime("%m%d%H%M%Y.%S")

    def _manage_contact(self, controller, mode="inject"):
        """Unified contact management."""
        if mode == "inject":
            if not (ContactsSetup and self.contact_name and self.contact_phone):
                return logger.warning("Skipping contact injection.")
            try:
                ContactsSetup(controller).setup({"list": [{"name": self.contact_name, "phone": self.contact_phone}]})
                logger.info(f"Injected contact: {self.contact_name}")
            except Exception as e:
                logger.error(f"Contact injection failed: {e}")
        elif mode == "clean" and self.contact_name:
            safe = self.contact_name.replace("'", "\\'")
            execute_adb(f"shell content delete --uri content://com.android.contacts/raw_contacts --where \"display_name='{safe}'\"")

    def initialize_task_hook(self, controller: AndroidController) -> bool:
        logger.info("Initializing BirthdayWishTask...")
        execute_adb("shell settings put global auto_time 0")
        execute_adb("shell settings put system time_12_24 24")
        fmt_adb = lambda dt: dt.strftime('%m%d%H%M%Y.%S')

        # Phase 1: Pre-reminder setup
        start_dt = datetime.strptime(self.event_start, "%Y-%m-%d %H:%M:%S")
        execute_adb(f"shell su 0 date {fmt_adb(start_dt - timedelta(minutes=self.REMINDER_MINUTES + 5))}")

        self._manage_contact(controller, "inject")
        try:
            insert_calendar_event(title=self.event_title, start_time=self.event_start, end_time=self.event_end,
                                  description="Birthday", reminder_1_minutes=self.REMINDER_MINUTES,
                                  reminder_2_minutes=5, reminder_3_minutes=0)
        except Exception as e:
            logger.error(f"Event injection failed: {e}")

        # Register alarms via app launch
        execute_adb(f"shell appops set {self.PKGS['cal']} POST_NOTIFICATION allow")
        for pkg in self.PKGS.values(): execute_adb(f"shell am force-stop {pkg}")
        execute_adb(f"shell monkey -p {self.PKGS['cal']} -c android.intent.category.LAUNCHER 1")
        time.sleep(3)

        # Phase 2: Trigger reminder (jump to post-reminder time)
        execute_adb(f"shell su 0 date {fmt_adb(start_dt - timedelta(seconds=5))}")
        time.sleep(5)
        execute_adb("shell input keyevent HOME")

        # Context Prompt
        display_str = self.check_dt.strftime("%H:%M (%B %d)") if self.check_dt else self.check_time
        has_routine = self.expectation["should_act"]
        if has_routine:
            routine_hint = "You HAVE this routine in your profile."
        else:
            routine_hint = "You do NOT have this routine in your profile."

        self.relevant_information = self._build_relevant_information(
            current_context=f"It is {display_str} now. You are using your phone.",
            routine_status=routine_hint,
            task_specific_detail=(
                "For this birthday-wish suggestion, prioritize the ROUTINE STATUS above when deciding."
            ),
        )
        return True

    def initialize_user_agent_hook(self, controller: AndroidController) -> bool:
        super().initialize_user_agent_hook(controller)
        self._set_user_sys_prompt(controller)
        return True

    def is_successful(self, controller: AndroidController, actions: list[dict] = None) -> tuple[float, str]:
        self._check_is_initialized()
        actions = actions or []
        # 1. Determine User Intent
        should_act = self.expectation["should_act"]
        user_accepts, ask_idx = self._parse_user_decision(
            actions=actions,
            history=controller.user_agent_chat_history,
            default_accept=should_act,
        )

        # 2. Safety/Disturbance Check
        has_violation, violation_msg = self._check_unsafe_actions(
            actions=actions,
            base_should_act=should_act,
            user_accepts=user_accepts,
            ask_idx=ask_idx,
            no_habit_msg="Failure: Unsafe actions performed without routine.",
            reject_msg="Failure: Unsafe actions performed after rejection.",
        )
        if has_violation:
            return 0.0, violation_msg

        # 3. Verify SMS Status
        has_any = check_sms_via_adb(controller, phone_number=self.contact_phone, content="")
        has_correct = any(check_sms_via_adb(controller, phone_number=self.contact_phone, content=k) for k in self.KEYWORDS)

        # 4. Final Scoring
        if user_accepts:
            if has_correct: return 1.0, f"Success: Sent correct wish to {self.contact_name}."
            if has_any: return 0.0, "Failure: Sent SMS but content mismatch."
            return 0.0, "Failure: User accepted but no SMS sent."
        else:
            if has_any: return 0.0, "Failure: User rejected but SMS was sent."
            return 1.0, "Success: User rejected and silence maintained."

    def tear_down(self, controller: AndroidController) -> bool:
        super().tear_down(controller)
        execute_adb("shell settings put global auto_time 1")
        execute_adb("shell settings delete system time_12_24")
        self._manage_contact(controller, "clean")
        return True
"""Preference task: set weekend wake-up alarm with favorite ringtone."""

from typing import Any

from loguru import logger

from knowu_bench.runtime.controller import AndroidController
from knowu_bench.runtime.utils.helpers import execute_adb, execute_root_sql
from knowu_bench.tasks.definitions.preference.base_prefrence_task import BasePrefrenceTask
from datetime import datetime

WEEKEND_MASK = 96  # Saturday(32) + Sunday(64)


class SetAlarmPreferenceAskUser2Task(BasePrefrenceTask):
    """
    Set a weekend wake-up alarm with an ambiguous preference instruction.
    Scoring = base weekend-alarm check + preference judge.
    """

    task_tags = {"agent-user-interaction", "preference", "hybrid-eval", "lang-en", "easy"}
    supported_profiles = {"grandma"}

    GOAL_REQUEST = "Please set a wake-up alarm for my weekend, and choose my favorite ringtone."
    snapshot_tag = "init_state"
    DEFAULT_PROFILE_PATH = "src/knowu_bench/user_profile/grandama.yaml"

    app_names = {"Clock"}

    @property
    def goal(self) -> str:
        return f"{self._build_user_logs_section()}\n\n### USER INSTRUCTION\n{self.GOAL_REQUEST}"

    def _get_weekend_alarm_preference(self) -> dict[str, Any]:
        habits = self.user_profile.get("habits", {}) or {}
        return habits.get("weekend_alarm", {}) or {}

    def initialize_task_hook(self, controller: AndroidController) -> bool:
        execute_adb("shell settings put global auto_time 0")
        ts = datetime.now().strftime("%m%d%H%M%Y.%S")
        res = execute_adb(f"shell su root date {ts}")
        if not res.success:
            execute_adb(f"shell date {ts}")

        weekend_alarm = self._get_weekend_alarm_preference()
        pref_time = weekend_alarm.get("wakeup_time", "not explicitly specified")
        pref_ringtone = weekend_alarm.get(
            "favoriate_ringtone", weekend_alarm.get("favorite_ringtone", "not explicitly specified")
        )

        self.relevant_information = self._build_relevant_information(
            current_context=(
                "You want to set a weekend wake-up alarm in the Clock app and pick your favorite ringtone."
            ),
            task_specific_detail=(
                "Weekend alarm preference from persona:\n"
                f"- Preferred wake-up time: {pref_time}\n"
                f"- Favorite ringtone: {pref_ringtone}\n"
                "The assistant may ask follow-up questions about time/ringtone."
            ),
            extra_instruction=(
                "If the assistant asks for weekend time or ringtone preference, answer consistently "
                "with your persona and historical habits."
            ),
        )
        return True

    def _find_enabled_weekend_alarm(self, alarms: list[dict[str, Any]]) -> dict[str, Any] | None:
        for alarm in alarms:
            if alarm.get("enabled", False) and (alarm.get("daysofweek", 0) & WEEKEND_MASK) == WEEKEND_MASK:
                return alarm
        return None

    def _get_all_alarms_via_adb(self) -> list[dict[str, Any]]:
        """Query all alarms from Clock DB and return newest-first records."""
        db_path = "/data/user_de/0/com.google.android.deskclock/databases/alarms.db"
        sql_query = (
            "SELECT _id, hour, minutes, enabled, daysofweek, vibrate, ringtone, label, blackout_end "
            "FROM alarm_templates ORDER BY _id DESC;"
        )

        result = execute_root_sql(db_path, sql_query)
        if not result:
            logger.info("No alarm rows found or alarm DB query failed.")
            return []

        alarms: list[dict[str, Any]] = []
        for line in result.splitlines():
            line = line.strip()
            if not line:
                continue

            parts = line.split("|")
            if len(parts) < 8:
                logger.warning(f"Unexpected alarm row format: {line}")
                continue

            if len(parts) >= 9:
                alarm_id = self._safe_int(parts[0])
                hour = self._safe_int(parts[1])
                minute = self._safe_int(parts[2])
                enabled = bool(self._safe_int(parts[3]))
                daysofweek = self._safe_int(parts[4])
                vibrate = bool(self._safe_int(parts[5]))
                ringtone = parts[6]
                label = parts[7]
                blackout_end = parts[8]
            else:
                alarm_id = -1
                hour = self._safe_int(parts[0])
                minute = self._safe_int(parts[1])
                enabled = bool(self._safe_int(parts[2]))
                daysofweek = self._safe_int(parts[3])
                vibrate = bool(self._safe_int(parts[4]))
                ringtone = parts[5] if len(parts) > 5 else ""
                label = parts[6] if len(parts) > 6 else ""
                blackout_end = parts[7] if len(parts) > 7 else ""

            alarms.append(
                {
                    "id": alarm_id,
                    "hour": hour,
                    "minutes": minute,
                    "enabled": enabled,
                    "daysofweek": daysofweek,
                    "vibrate": vibrate,
                    "ringtone": ringtone,
                    "label": label,
                    "blackout_end": blackout_end,
                }
            )

        logger.info(f"Loaded {len(alarms)} alarms from adb sqlite query.")
        return alarms

    @staticmethod
    def _safe_int(value: Any, default: int = 0) -> int:
        try:
            if value is None or value == "":
                return default
            return int(value)
        except Exception:
            return default

    def is_successful(self, controller: AndroidController) -> float | tuple[float, str]:
        """Hybrid scoring: base alarm check + preference judge."""
        self._check_is_initialized()

        alarms = self._get_all_alarms_via_adb()
        if not alarms:
            return 0.0, "Failure: No alarm data found via adb."

        selected_alarm = self._find_enabled_weekend_alarm(alarms)
        if selected_alarm is None:
            return 0.0, "Failure: No enabled weekend alarm found."

        base_score = 1
        alarm_time = f"{int(selected_alarm.get('hour', 0)):02d}:{int(selected_alarm.get('minutes', 0)):02d}"
        ringtone = str(selected_alarm.get("ringtone", ""))
        logger.info(f"[Eval Phase 1] Weekend alarm set in Clock. Base Score: {base_score}")

        chat_history = getattr(controller, "user_agent_chat_history", [])
        chat_tail = chat_history[-10:] if isinstance(chat_history, list) else []

        rubric = (
            "Evaluate the alarm-setting result against the user's persona on four dimensions:\n\n"
            "1. Wake-up Time Preference (35%):\n"
            "   Is the chosen weekend wake-up time aligned with persona habit signals (e.g., weekend_alarm)?\n"
            "   - 1.0: closely matches explicit preferred weekend wake-up time\n"
            "   - 0.5: reasonable but not exact\n"
            "   - 0.0: clearly conflicts with persona habit\n\n"
            "2. Ringtone Preference (35%):\n"
            "   Does the selected ringtone match the persona's favorite/usual ringtone style or name?\n"
            "   - 1.0: explicit match\n"
            "   - 0.5: partially aligned/acceptable style\n"
            "   - 0.0: mismatched ringtone choice\n\n"
            "3. Alarm Correctness (20%):\n"
            "   Confirm this is an enabled weekend alarm (Sat+Sun repeat) suitable as wake-up usage.\n"
            "   - 1.0: enabled and weekend repeat correctly set\n"
            "   - 0.5: alarm exists but repeat/enable only partially correct\n"
            "   - 0.0: not a weekend wake-up alarm\n\n"
            "4. App/Interaction Preference (10%):\n"
            "   Based on user_agent_chat_history_tail, did the assistant ask clarifying questions when needed and "
            "stay consistent with the user's app habits/preferences?\n"
            "   - 1.0: good ask-user clarification and preference-consistent behavior\n"
            "   - 0.5: limited clarification but acceptable\n"
            "   - 0.0: ignored clear preference cues\n\n"
            "Final weighted score = 0.35 * time_pref + 0.35 * ringtone_pref + "
            "0.2 * alarm_correctness + 0.1 * interaction_quality."
        )

        user_agent_score, judge_reasoning = self.query_user_agent_judge(
            eval_data={
                "app_used": "Clock",
                "selected_alarm": selected_alarm,
                "all_alarm_candidates": alarms[:5],
                "user_agent_chat_history_tail": chat_tail,
            },
            rubric=rubric,
        )

        final_score = 0.4 * base_score + (0.6 * user_agent_score)

        final_reason = (
            f"Weekend alarm set in Clock (+{0.4 * base_score:.1f}). "
            f"Preference judge: {user_agent_score:.2f} (+{0.6 * user_agent_score:.2f}). "
            f"Alarm: {alarm_time}, ringtone: {ringtone}. "
            f"Judge reasoning: {judge_reasoning}"
        )

        return final_score, final_reason

    def tear_down(self, controller: AndroidController) -> bool:
        super().tear_down(controller)
        return True
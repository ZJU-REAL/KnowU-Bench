"""General task: block a scam SMS sender."""

import subprocess
import time

from loguru import logger

try:
    from knowu_bench.runtime.app_helpers.system import check_sms_via_adb
except ImportError:
    check_sms_via_adb = lambda *args, **kwargs: False

from knowu_bench.runtime.controller import AndroidController
from knowu_bench.runtime.utils.helpers import execute_adb
from knowu_bench.tasks.base import BaseTask


def _adb_sqlite_count(db_path: str, sql: str) -> int:
    cmd = ["adb", "shell", "su", "0", "sqlite3", db_path]
    try:
        proc = subprocess.run(cmd, input=sql, capture_output=True, text=True, timeout=5)
        if proc.returncode == 0 and proc.stdout.strip().isdigit():
            return int(proc.stdout.strip())
    except Exception as e:
        logger.warning(f"SQLite query failed: {e}")
    return 0


class ScamSmsInterceptGeneralTask(BaseTask):
    """Block a scam SMS sender with explicit instruction."""

    task_tags = {"general", "easy"}
    snapshot_tag = "init_state"
    app_names = {"Messages"}

    SMS_PACKAGE = "com.simplemobiletools.sms_messenger"
    GOOGLE_PKG = "com.google.android.apps.messaging"
    SENDER_PHONE = "1069012345678"
    SMS_CONTENT = (
        "【Bank Notice】Your account shows abnormal activity. "
        "Click http://secure-bank-check.cc to verify."
    )
    TARGET_TIMESTAMP = "021311152026.00"

    BLOCKED_URIS = [
        "content://com.android.blockednumber/blocked",
        "content://blocked_numbers",
    ]

    goal = (
        f"我刚收到一条可疑的诈骗短信，发件人号码是 {SENDER_PHONE}，"
        "内容是关于银行账户异常的钓鱼链接。"
        "请帮我拉黑这个号码（Block this number）。"
    )

    def __init__(self, params=None):
        super().__init__(params)
        phone_param = self.SENDER_PHONE.replace("+", "")
        self.BLOCK_DB_CHECKS = [
            (f"/data/data/{self.SMS_PACKAGE}/databases/messages.db",
             f"SELECT COUNT(*) FROM blocked_numbers WHERE number LIKE '%{phone_param}%';"),
            (f"/data/data/{self.GOOGLE_PKG}/databases/bugle_db",
             f"SELECT COUNT(*) FROM participants WHERE blocked=1 AND normalized_destination LIKE '%{phone_param}%';"),
        ]

    def initialize_task_hook(self, controller: AndroidController) -> bool:
        execute_adb("shell settings put global auto_time 0")
        execute_adb("shell settings put system time_12_24 24")
        execute_adb(f"shell su 0 date {self.TARGET_TIMESTAMP}")
        execute_adb(f"shell am force-stop {self.SMS_PACKAGE}")
        execute_adb("shell input keyevent HOME")
        time.sleep(1)
        try:
            controller.simulate_sms(sender=self.SENDER_PHONE, message=self.SMS_CONTENT)
        except Exception:
            return False
        time.sleep(2)
        return True

    def _query_uri_for_phone(self, uri: str) -> bool:
        r = execute_adb(f"shell content query --uri {uri}")
        return r.success and self.SENDER_PHONE in (r.output or "")

    def _check_db_status(self, checks: list) -> str | None:
        for db, sql in checks:
            if _adb_sqlite_count(db, sql) > 0:
                return f"Found in DB: {db}"
        return None

    def _check_logcat(self, keywords: list[str]) -> bool:
        r = execute_adb("shell logcat -d -t 200")
        if r.success and r.output:
            out = r.output.lower()
            return self.SENDER_PHONE in out and any(k in out for k in keywords)
        return False

    def is_successful(self, controller: AndroidController) -> tuple[float, str]:
        self._check_is_initialized()

        replied = check_sms_via_adb(controller, phone_number=self.SENDER_PHONE, content="")
        if replied:
            return 0.0, "Failure: Agent replied to the scam sender."

        is_blocked = any(self._query_uri_for_phone(uri) for uri in self.BLOCKED_URIS)
        block_reason = "ContentProvider" if is_blocked else self._check_db_status(self.BLOCK_DB_CHECKS)
        if not is_blocked and block_reason:
            is_blocked = True

        if not is_blocked and self._check_logcat(["block", "blacklist", "reject"]):
            is_blocked, block_reason = True, "Logcat"

        if is_blocked:
            return 1.0, f"Success: Sender {self.SENDER_PHONE} has been blocked. (via {block_reason})"
        return 0.0, f"Failure: Sender {self.SENDER_PHONE} was not blocked."

    def tear_down(self, controller: AndroidController) -> bool:
        super().tear_down(controller)
        execute_adb("shell settings put global auto_time 1")
        execute_adb("shell settings delete system time_12_24")
        return True

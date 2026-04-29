from datetime import datetime, timedelta
from loguru import logger
from knowu_bench.runtime.utils.helpers import execute_adb
from .base import BaseSetup

class MessagesSetup(BaseSetup):
    def setup(self, config: dict) -> bool:
        if "threads" in config:
            app_config = config
        elif "app_messages" in config:
            app_config = config["app_messages"]
        else:
            app_config = config.get("user_profile", {}).get("environment_init_state", {}).get("app_messages", {})

        if not app_config or not app_config.get("threads"):
            logger.warning("No message threads configuration found")
            return False

        threads = app_config.get("threads", [])
        success_count = 0
        now = datetime.now()

        for thread in threads:
            # 强转 str 防止 YAML 解析为 int
            sender = str(thread.get("sender", "")).strip()
            text = str(thread.get("text", "")).strip()
            if not sender or not text:
                continue

            ts = int(now.timestamp() * 1000)
            if "yesterday" in str(thread.get("time", "")).lower():
                ts = int((now - timedelta(days=1)).timestamp() * 1000)

            # 格式化参数：转义内部双引号和单引号
            # 注意：在 Shell 中传递带空格/冒号的参数，最稳妥的是 key:s:"value"
            safe_sender = sender.replace('"', r'\"').replace("'", r"'\''")
            safe_body = text.replace('"', r'\"').replace("'", r"'\''")
            
            # 构造 content 参数部分
            content_args = (
                f"insert --uri content://sms/inbox "
                f"--bind address:s:\"{safe_sender}\" "
                f"--bind body:s:\"{safe_body}\" "
                f"--bind date:l:{ts} "
                f"--bind read:i:{1 if thread.get('read') else 0} "
                f"--bind type:i:1"
            )

            # 构造完整 ADB 命令
            full_cmd = f"adb -s {self.controller.device} shell 'content {content_args}'"
            
            # [DEBUG] 打印具体执行的命令，方便排查转义问题
            logger.debug(f"Injecting [{sender}]: {full_cmd}")

            res = execute_adb(full_cmd, output=False)
            
            if res.success:
                success_count += 1
            else:
                logger.error(f"Injection failed for '{sender}'. Error: {res.error}")

        logger.info(f"Successfully processed {success_count}/{len(threads)} messages")
        return success_count > 0
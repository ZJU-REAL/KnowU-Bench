"""General task: mute media volume after Bluetooth disconnects."""

import re
import time

from knowu_bench.runtime.controller import AndroidController
from knowu_bench.runtime.utils.helpers import execute_adb
from knowu_bench.tasks.base import BaseTask


class BluetoothCleanupGeneralTask(BaseTask):
    """Mute media volume after Bluetooth headphones disconnect."""

    task_tags = {"general", "easy"}
    snapshot_tag = "init_state"
    app_names = {"Settings"}

    INITIAL_VOLUME = 10

    goal = "蓝牙耳机刚断开连接了，请帮我把手机的媒体音量调为静音（音量设为 0 或静音）。"

    def initialize_task_hook(self, controller: AndroidController) -> bool:
        execute_adb("shell settings put system time_12_24 24")
        execute_adb(f"shell cmd media_session volume --stream 3 --set {self.INITIAL_VOLUME}")
        execute_adb("shell su 0 am broadcast -a android.bluetooth.device.action.ACL_DISCONNECTED")
        time.sleep(2)
        return True

    def _get_media_state(self) -> tuple[int, bool]:
        vol, muted = -1, False
        res = execute_adb("shell cmd media_session volume --stream 3 --get")
        if res.output and (match := re.search(r"volume is\s*(\d+)", res.output, re.I)):
            vol = int(match.group(1))
        try:
            dump = execute_adb("shell dumpsys audio").output
            if match := re.search(r"(- STREAM_MUSIC:.*?)(\n- STREAM_|\Z)", dump, re.DOTALL):
                music_sec = match.group(1)
                muted = "Muted: true" in music_sec
                if vol == -1 and (v_match := re.search(r"Current:\s*(\d+)", music_sec)):
                    vol = int(v_match.group(1))
        except Exception:
            pass
        return vol, muted

    def is_successful(self, controller: AndroidController) -> tuple[float, str]:
        self._check_is_initialized()
        vol, muted = self._get_media_state()
        is_silent = (vol == 0) or muted
        state_desc = f"Vol: {vol}, Muted: {muted}"
        if is_silent:
            return 1.0, f"Success: Media volume is muted. [{state_desc}]"
        return 0.0, f"Failure: Media volume is still audible. [{state_desc}]"

    def tear_down(self, controller: AndroidController) -> bool:
        super().tear_down(controller)
        execute_adb("shell settings delete system time_12_24")
        execute_adb("shell cmd media_session volume --stream 3 --set 5")
        return True

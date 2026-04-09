import json
from pathlib import Path

from mobile_world.runtime.utils.helpers import execute_adb


def initialize_inbox(state: str):
    remote = "/sdcard/Android/data/com.gmailclone/files/" + state + ".json"
    root = Path(__file__).resolve().parent
    local = root / "assets" / f"{state}.json"
    execute_adb(f"push {local} {remote}")


def initialize_attachments():
    remote = "/sdcard/Android/data/com.gmailclone/files/attachments"
    root = Path(__file__).resolve().parent
    attachments_dir = root / "attachments"
    for file in attachments_dir.iterdir():
        execute_adb(f"push {file} {remote}")


def get_sent_email_info():
    potential_paths = [
        "/sdcard/Android/data/com.gmailclone/files/sentEmail.json",
    ]
    for path in potential_paths:
        result = execute_adb(f"adb shell cat {path}")
        if result.success:
            data = json.loads(result.output)
            return data
    return None

"""General task: share flower photos via email with explicit instructions."""

import time
from pathlib import Path

from loguru import logger

from knowu_bench.runtime.app_helpers import mail
from knowu_bench.runtime.controller import AndroidController
from knowu_bench.runtime.utils.helpers import execute_adb
from knowu_bench.tasks.base import BaseTask

EMAIL_ADDRESS = "kevin_zhang@example.com"
EMAIL_TEXT = "Here are some pictures for you."


class SharePhotosGeneralTask(BaseTask):
    """Send flower photos to Kevin via email with explicit recipient and content."""

    task_tags = {"general", "hard"}
    snapshot_tag = "init_state"

    app_names = {"Gallery", "Mail"}
    goal = (
        f'Send all flower photos from Gallery to Kevin ({EMAIL_ADDRESS}) via email, '
        f'with the text "{EMAIL_TEXT}".'
    )

    def initialize_task_hook(self, controller: AndroidController) -> bool:
        execute_adb("shell settings put global auto_time 0")
        res = execute_adb("shell su root date 021014002026.00")
        if not res.success:
            execute_adb("shell date 021014002026.00")

        assets_dir = Path(__file__).resolve().parents[3] / "assets"
        if not assets_dir.exists():
            logger.error(f"Assets directory not found: {assets_dir}")
            return False

        image_files = (
            list(assets_dir.glob("*.png"))
            + list(assets_dir.glob("*.jpeg"))
            + list(assets_dir.glob("*.jpg"))
        )
        if not image_files:
            logger.error(f"No image files found in {assets_dir}")
            return False

        self._remote_image_paths: list[str] = []
        for local_image_path in image_files:
            remote_path = f"/sdcard/Pictures/{local_image_path.name}"
            result = controller.push_file(str(local_image_path), remote_path)
            if not result.success:
                logger.error(f"Failed to push image {local_image_path.name}: {result.error}")
                continue
            self._remote_image_paths.append(remote_path)
            time.sleep(0.5)
            controller.refresh_media_scan(remote_path)

        if not self._remote_image_paths:
            logger.error("Failed to push any images to device")
            return False

        time.sleep(2)
        return True

    def is_successful(self, controller: AndroidController) -> float | tuple[float, str]:
        self._check_is_initialized()

        sent_email_info = mail.get_sent_email_info()
        if sent_email_info is None:
            return 0.0, "Failure: No email sent."

        to_addr = str(sent_email_info.get("to", "")).strip()
        body = str(sent_email_info.get("body", "")).strip()
        attachments = sent_email_info.get("attachments", [])

        if not to_addr:
            return 0.0, "Failure: Email recipient is empty."
        if not isinstance(attachments, list) or not attachments:
            return 0.0, "Failure: No image attachments found."

        score = 0.0
        checks = []

        is_kevin = EMAIL_ADDRESS.lower() in to_addr.lower() or "kevin" in to_addr.lower()
        if is_kevin:
            score += 0.3
            checks.append("recipient=OK")
        else:
            checks.append(f"recipient=WRONG({to_addr})")

        has_text = EMAIL_TEXT.lower() in body.lower() or "picture" in body.lower()
        if has_text:
            score += 0.2
            checks.append("body_text=OK")
        else:
            checks.append("body_text=MISSING")

        num_attachments = len(attachments)
        if num_attachments >= 1:
            score += 0.5
            checks.append(f"attachments={num_attachments}")
        else:
            checks.append("attachments=NONE")

        reason = f"Email sent. To: {to_addr}. {', '.join(checks)}. Score: {score:.1f}"
        logger.info(f"[Eval] {reason}")
        return score, reason

    def tear_down(self, controller: AndroidController) -> bool:
        super().tear_down(controller)
        try:
            if hasattr(self, "_remote_image_paths"):
                for remote_path in self._remote_image_paths:
                    controller.remove_file(remote_path)
        except Exception as exc:
            logger.error(f"Error cleaning up images: {exc}")
        return True

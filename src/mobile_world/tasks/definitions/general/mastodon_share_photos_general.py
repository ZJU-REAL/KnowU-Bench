"""General task: share a specific photo to Mastodon with an explicit caption."""

import re
import time
from pathlib import Path

from loguru import logger

from mobile_world.runtime.app_helpers import mastodon
from mobile_world.runtime.app_helpers.mastodon import (
    check_image_consistency,
    get_latest_toots_by_username,
)
from mobile_world.runtime.controller import AndroidController
from mobile_world.tasks.base import BaseTask

EXPECTED_USERNAME = "test"
CACHE_USERS_DIR = Path(__file__).resolve().parents[5] / "src" / "mobile_world" / "cache" / "users"
DEFAULT_SHARE_IMAGE = CACHE_USERS_DIR / "aiden_lin" / "mastodon_share" / "hugginggpt.jpg"


def _clean_toot_text(raw_text: str) -> str:
    if not raw_text:
        return ""
    no_html = re.sub(r"<[^>]+>", " ", raw_text)
    return re.sub(r"\s+", " ", no_html).strip()


class MastodonSharePhotosGeneralTask(BaseTask):
    """Share the provided Gallery photo to Mastodon with a casual caption."""

    task_tags = {"general", "hard"}
    snapshot_tag = "init_state"
    username = EXPECTED_USERNAME

    app_names = {"Gallery", "Mastodon"}
    goal = (
        "Help me post the provided photo from my Gallery to Mastodon using the already "
        "logged-in test account (@test). Write a short casual caption like 'Nice shot from "
        "today!' or similar."
    )

    def _resolve_share_images(self) -> list[Path]:
        if DEFAULT_SHARE_IMAGE.exists():
            return [DEFAULT_SHARE_IMAGE]
        logger.error(f"Default Mastodon share image not found: {DEFAULT_SHARE_IMAGE}")
        return []

    def initialize_task_hook(self, controller: AndroidController) -> bool:
        selected_files = self._resolve_share_images()
        self._expected_image_paths = [str(p) for p in selected_files]
        self._remote_image_paths = []

        backend_started = mastodon.start_mastodon_backend()
        if not backend_started:
            logger.error("Failed to start Mastodon backend.")
            return False

        if not selected_files:
            logger.error("No default Mastodon share image available for this task.")
            return False

        for local_image_path in selected_files:
            remote_path = f"/sdcard/Pictures/{local_image_path.name}"
            result = controller.push_file(str(local_image_path), remote_path)
            if not result.success:
                logger.error(f"Failed to push image {local_image_path.name}: {result.error}")
                continue
            self._remote_image_paths.append(remote_path)
            time.sleep(0.5)
            controller.refresh_media_scan(remote_path)

        if not self._remote_image_paths:
            logger.error("Failed to push any images to device.")
            return False

        time.sleep(2)
        return True

    def is_successful(self, controller: AndroidController) -> tuple[float, str]:
        self._check_is_initialized()

        if not mastodon.is_mastodon_healthy():
            if not mastodon.start_mastodon_backend():
                return 0.0, "Mastodon backend is unhealthy and restart failed."

        toots = get_latest_toots_by_username(self.username, limit=1)
        if not toots:
            return 0.0, f"No toot found for target user '{self.username}'."

        toot = toots[0]
        toot_account = ((toot.get("account") or {}).get("username") or self.username).strip()
        account_ok = toot_account == self.username
        expected_image_paths = getattr(self, "_expected_image_paths", [])
        if not expected_image_paths:
            return 0.0, "Expected reference image is missing; cannot validate uploaded photo."

        image_ok, image_msg = check_image_consistency(
            username=self.username,
            expected_image_paths=expected_image_paths,
        )

        toot_text = _clean_toot_text(toot.get("text", ""))
        has_caption = len(toot_text) > 3

        success = account_ok and image_ok and has_caption
        score = 1.0 if success else 0.0

        reason = (
            f"Account: {'ok' if account_ok else 'failed'} "
            f"(expected={self.username}, got={toot_account}). "
            f"Image: {'ok' if image_ok else 'failed'} ({image_msg}). "
            f"Caption: '{toot_text}' (has_caption={has_caption}). "
            f"Score: {score:.1f}"
        )
        return score, reason

    def tear_down(self, controller: AndroidController) -> bool:
        super().tear_down(controller)
        try:
            if hasattr(self, "_remote_image_paths"):
                for remote_path in self._remote_image_paths:
                    controller.remove_file(remote_path)
        except Exception as exc:
            logger.error(f"Error cleaning up images: {exc}")
        try:
            mastodon.stop_mastodon_backend()
        except Exception as exc:
            logger.error(f"Failed to stop Mastodon backend: {exc}")
            return False
        return True

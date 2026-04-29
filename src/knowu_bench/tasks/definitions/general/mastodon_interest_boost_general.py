"""General task: forward a specific Mastodon post to a Mattermost channel."""

import re
import time

from loguru import logger

from knowu_bench.runtime.app_helpers import mastodon, mattermost
from knowu_bench.runtime.app_helpers.mastodon import (
    start_mastodon_backend,
    stop_mastodon_backend,
)
from knowu_bench.runtime.app_helpers.mattermost import (
    get_latest_user_post_detail_after,
    start_mattermost_backend,
    stop_mattermost_backend,
)
from knowu_bench.runtime.controller import AndroidController
from knowu_bench.tasks.base import BaseTask


class MastodonInterestBoostGeneralTask(BaseTask):
    """Browse Mastodon timeline and forward an AI-related post to Mattermost Town Square channel."""

    task_tags = {"general", "hard"}
    snapshot_tag = "init_state"

    app_names = {"Mastodon", "Mattermost"}
    goal = (
        "Check my Mastodon timeline for a post related to AI or machine learning, "
        "and forward it (copy the link or content) to the 'Town Square' channel on Mattermost."
    )

    def initialize_task_hook(self, controller: AndroidController) -> bool:
        self._init_timestamp = int(time.time()) * 1000

        if not start_mastodon_backend():
            logger.error("Failed to start Mastodon backend.")
            return False

        if not start_mattermost_backend():
            logger.error("Failed to start Mattermost backend.")
            return False

        return True

    def is_successful(self, controller: AndroidController) -> tuple[float, str]:
        self._check_is_initialized()

        if not mastodon.is_mastodon_healthy():
            if not mastodon.start_mastodon_backend():
                return 0.0, "Mastodon backend is unhealthy and restart failed."

        if not mattermost.is_mattermost_healthy():
            if not mattermost.start_mattermost_backend():
                return 0.0, "Mattermost backend is unhealthy and restart failed."

        try:
            post_detail = get_latest_user_post_detail_after(self._init_timestamp)
        except Exception as exc:
            logger.error(f"Mattermost post query failed: {exc}")
            post_detail = None

        if not post_detail:
            return 0.0, "No message found on Mattermost after task init."

        post_message = post_detail.get("message", "")
        channel_name = post_detail.get("channel_name", "unknown")

        score = 0.0
        checks = []

        if post_message.strip():
            score += 0.5
            checks.append("message_sent=OK")
        else:
            checks.append("message_sent=EMPTY")

        channel_ok = "town" in channel_name.lower() or "square" in channel_name.lower()
        if channel_ok:
            score += 0.3
            checks.append(f"channel={channel_name}(OK)")
        else:
            score += 0.1
            checks.append(f"channel={channel_name}(WRONG)")

        has_link = bool(re.search(r"https?://", post_message))
        if has_link:
            score += 0.2
            checks.append("has_link=OK")
        else:
            checks.append("has_link=NO")

        reason = f"Mattermost forwarding. {', '.join(checks)}. Score: {score:.1f}"
        logger.info(f"[Eval] {reason}")
        return score, reason

    def tear_down(self, controller: AndroidController) -> bool:
        super().tear_down(controller)
        for name, stop_fn in [
            ("Mastodon", stop_mastodon_backend),
            ("Mattermost", stop_mattermost_backend),
        ]:
            try:
                stop_fn()
            except Exception as exc:
                logger.error(f"Failed to stop {name} backend: {exc}")
        return True

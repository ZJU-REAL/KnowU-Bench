"""General task: post a specific status to Mastodon with explicit visibility."""

import re

from loguru import logger

from knowu_bench.runtime.app_helpers import mastodon
from knowu_bench.runtime.app_helpers.mastodon import (
    get_latest_toots_by_username,
    start_mastodon_backend,
    stop_mastodon_backend,
)
from knowu_bench.runtime.controller import AndroidController
from knowu_bench.tasks.base import BaseTask

POST_TEXT = "周末去爬了西湖边的宝石山，风景超棒！"


def _clean_toot_text(raw_text: str) -> str:
    if not raw_text:
        return ""
    no_html = re.sub(r"<[^>]+>", " ", raw_text)
    return re.sub(r"\s+", " ", no_html).strip()


class MastodonPrivacyDefaultGeneralTask(BaseTask):
    """Post a specific status to Mastodon with public visibility."""

    task_tags = {"general", "easy"}
    snapshot_tag = "init_state"
    username = "test"

    app_names = {"Mastodon"}
    goal = (
        f"帮我在 Mastodon 上发一条公开可见的动态，内容为：'{POST_TEXT}'"
    )

    def initialize_task_hook(self, controller: AndroidController) -> bool:
        backend_started = start_mastodon_backend()
        if not backend_started:
            logger.error("Failed to start Mastodon backend.")
            return False
        return True

    def is_successful(self, controller: AndroidController) -> tuple[float, str]:
        self._check_is_initialized()

        if not mastodon.is_mastodon_healthy():
            if not start_mastodon_backend():
                return 0.0, "Mastodon backend is unhealthy and restart failed."

        toots = get_latest_toots_by_username(self.username, limit=1)
        if not toots:
            return 0.0, "No toot found for target user."

        toot = toots[0]
        toot_text = _clean_toot_text(toot.get("text", ""))
        visibility = toot.get("visibility", -1)

        if not toot_text:
            return 0.0, "Toot has no text content."

        score = 0.0
        checks = []

        content_keywords = ["宝石山", "西湖", "风景"]
        has_content = any(kw in toot_text for kw in content_keywords)
        if has_content:
            score += 0.6
            checks.append("content=OK")
        else:
            score += 0.2
            checks.append(f"content=PARTIAL('{toot_text[:50]}')")

        vis_labels = {0: "public", 1: "unlisted", 2: "followers-only", 3: "direct"}
        vis_name = vis_labels.get(visibility, f"unknown({visibility})")
        if visibility == 0:
            score += 0.4
            checks.append("visibility=public(OK)")
        else:
            checks.append(f"visibility={vis_name}(WRONG)")

        reason = f"Toot posted. {', '.join(checks)}. Score: {score:.1f}"
        return score, reason

    def tear_down(self, controller: AndroidController) -> bool:
        super().tear_down(controller)
        try:
            stop_mastodon_backend()
        except Exception as exc:
            logger.error(f"Failed to stop Mastodon backend: {exc}")
            return False
        return True

"""Preference task: share user-specific photos to Mastodon with persona-aligned caption."""

import json
import os
import re
import time
from pathlib import Path
from datetime import datetime
from typing import Any

from loguru import logger

from mobile_world.runtime.app_helpers import mastodon
from mobile_world.runtime.app_helpers.mastodon import (
    check_image_consistency_for_status_id,
    get_images_by_status_id,
    get_latest_toot_after_datetime,
    get_toot_images_path,
)
from mobile_world.runtime.controller import AndroidController
from mobile_world.runtime.utils.helpers import execute_adb
from mobile_world.tasks.definitions.preference.base_prefrence_task import BasePrefrenceTask

# Task constants
EXPECTED_USERNAMES = ("test", "owner")
DEFAULT_SHARE_DIR = "src/mobile_world/cache/users"
SUPPORTED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


def _clean_toot_text(raw_text: str) -> str:
    if not raw_text:
        return ""
    no_html = re.sub(r"<[^>]+>", " ", raw_text)
    return re.sub(r"\s+", " ", no_html).strip()


def _get_emulator_unix_timestamp(controller: AndroidController) -> int:
    """Return the current Android emulator Unix timestamp in seconds."""
    try:
        result = execute_adb(f"adb -s {controller.device} shell date +%s")
        if result.success:
            clean_output = result.output.strip().split("\n")[-1].strip()
            return int(clean_output)
        logger.warning("Failed to get emulator timestamp, falling back to host time.")
    except Exception as exc:
        logger.warning(f"Failed to get emulator timestamp: {exc}")
    return int(time.time())


def _find_latest_toot(
    usernames: tuple[str, ...], created_after: datetime | int | float | str | None
) -> tuple[dict | None, str]:
    """Return the latest toot across candidate accounts created after *created_after*."""
    return get_latest_toot_after_datetime(usernames, created_after)


class MastodonSharePhotosPreferenceAskUserTask(BasePrefrenceTask):
    """Share one user-specific photo via Mastodon with persona-aligned caption."""

    task_tags = {"agent-user-interaction", "preference", "lang-en", "hard"}
    supported_profiles = {"student", "user"}

    GOAL_REQUEST = (
        "Help me post one photo I want to share to Mastodon feed, "
        "and write a caption that matches my communication style."
    )

    usernames = EXPECTED_USERNAMES
    share_root = DEFAULT_SHARE_DIR
    DEFAULT_PROFILE_PATH = "src/mobile_world/user_profile/student.yaml"

    app_names = {"Gallery", "Mastodon"}

    # ── Profile helpers ──────────────────────────────────────────────

    def _load_profile_preferences(self) -> tuple[dict[str, Any], dict[str, Any]]:
        pref_root = self.user_profile.get("preferences", {}) or {}
        return pref_root.get("social", {}) or {}, pref_root.get("apps", {}) or {}

    def _project_root(self) -> Path:
        return Path(__file__).resolve().parents[5]

    def _user_slug(self) -> str:
        full_name = (
            self.user_profile.get("identity", {}).get("full_name", "")
            if isinstance(self.user_profile, dict)
            else ""
        )
        slug = re.sub(r"[^a-z0-9]+", "_", full_name.lower()).strip("_")
        return slug or "user"

    def _mastodon_share_dir(self) -> Path:
        return self._project_root() / self.share_root / self._user_slug() / "mastodon_share"

    def _load_share_description(self) -> str:
        desc_path = self._mastodon_share_dir() / "description.txt"
        if not desc_path.exists():
            return ""
        try:
            return desc_path.read_text(encoding="utf-8").strip()
        except Exception as exc:
            logger.warning(f"Failed reading share description: {exc}")
            return ""

    def _resolve_mastodon_share_images(self) -> list[Path]:
        share_dir = self._mastodon_share_dir()
        if not share_dir.exists():
            logger.warning(f"Mastodon share directory not found for {self.name}: {share_dir}.")
            return []

        image_files = [
            p for p in sorted(share_dir.iterdir())
            if p.is_file() and p.suffix.lower() in SUPPORTED_IMAGE_EXTS
        ]
        if not image_files:
            logger.warning(f"No shareable images found for {self.name} in: {share_dir}.")
        return image_files

    # ── Lifecycle hooks ──────────────────────────────────────────────

    def initialize_task_hook(self, controller: AndroidController) -> bool:
        social_pref, app_pref = self._load_profile_preferences()

        social_detail = json.dumps(social_pref, indent=2, ensure_ascii=False) if social_pref else "N/A"
        app_detail = json.dumps(app_pref, indent=2, ensure_ascii=False) if app_pref else "N/A"

        selected_files = self._resolve_mastodon_share_images()[:1]
        self._expected_image_paths = [str(p) for p in selected_files]
        self._remote_image_paths: list[str] = []
        self._uses_seeded_share_assets = bool(selected_files)

        photo_description = self._load_share_description() if self._uses_seeded_share_assets else ""
        if photo_description:
            photo_context_line = f"Photo content hint from your own folder: {photo_description}"
        elif not self._uses_seeded_share_assets:
            photo_context_line = "No profile-specific seeded photo is provided. Base the caption on the image actually chosen in Gallery."
        else:
            photo_context_line = "Photo content hint is unavailable. Describe based on the actual image."

        self.relevant_information = self._build_relevant_information(
            current_context=(
                "You are about to post one photo to Mastodon from images in Gallery. "
                "The assistant may ask for preferred caption style. "
                f"{photo_context_line}"
            ),
            task_specific_detail=(
                f"My social preferences:\n{social_detail}\n\n"
                f"My app preferences:\n{app_detail}"
            ),
            extra_instruction="If asked to provide or revise a caption, align it with the social preference above.",
        )

        if not mastodon.start_mastodon_backend():
            logger.error("Failed to start Mastodon backend in initialize_task_hook.")
            return False

        if not selected_files:
            logger.info("No seeded Mastodon share assets for {}; skipping image push.", self.name)
            time.sleep(2)
            self._post_search_start_timestamp = _get_emulator_unix_timestamp(controller)
            return True

        for local_path in selected_files:
            remote_path = f"/sdcard/Pictures/{local_path.name}"
            result = controller.push_file(str(local_path), remote_path)
            if not result.success:
                logger.error(f"Failed to push image {local_path.name}: {result.error}")
                continue
            self._remote_image_paths.append(remote_path)
            time.sleep(0.5)
            controller.refresh_media_scan(remote_path)

        if not self._remote_image_paths:
            logger.error("Failed to push any images to device.")
            return False

        time.sleep(2)
        self._post_search_start_timestamp = _get_emulator_unix_timestamp(controller)
        return True

    # ── Evaluation ───────────────────────────────────────────────────

    def _resolve_posted_images(self, toot_id: int | None) -> list[str]:
        """Return local file paths of images attached to the given toot."""
        if toot_id is None:
            return []
        toot_images = get_images_by_status_id(toot_id) or []
        paths: list[str] = []
        for img in toot_images:
            mid, fname = img.get("media_attachment_id"), img.get("file_name")
            if not (mid and fname):
                continue
            local_path = get_toot_images_path(mid, fname)
            if os.path.exists(local_path):
                paths.append(local_path)
            else:
                logger.warning(f"[MastodonSharePhotos] Image not found on disk: {local_path}")
        return paths

    def is_successful(self, controller: AndroidController) -> tuple[float, str]:
        self._check_is_initialized()

        if not mastodon.is_mastodon_healthy():
            if not mastodon.start_mastodon_backend():
                return 0.0, "Mastodon backend is unhealthy and restart failed."

        # Look for the latest toot created after task initialization.
        post_start_timestamp = getattr(self, "_post_search_start_timestamp", None)
        toot, matched_user = _find_latest_toot(self.usernames, post_start_timestamp)
        if toot is None:
            if post_start_timestamp is None:
                return 0.0, f"No toot found for any of {list(self.usernames)}."
            return 0.0, (
                f"No toot found for any of {list(self.usernames)} "
                f"after emulator timestamp {post_start_timestamp}."
            )

        logger.info(
            f"[MastodonSharePhotos] Found toot from account: {matched_user} "
            f"after emulator timestamp {post_start_timestamp}"
        )

        toot_id = toot.get("id")

        # ── Image consistency ──
        expected_image_paths = getattr(self, "_expected_image_paths", [])
        if expected_image_paths:
            image_ok, image_msg = check_image_consistency_for_status_id(
                status_id=toot_id,
                expected_image_paths=expected_image_paths,
            )
        else:
            images = get_images_by_status_id(toot_id) if toot_id is not None else None
            if not images:
                image_ok, image_msg = False, "Latest toot has no images."
            else:
                image_ok, image_msg = True, f"No seeded image provided; accepted {len(images)} uploaded image(s)."

        toot_text = _clean_toot_text(toot.get("text", ""))

        # ── Resolve posted images for visual judge ──
        posted_image_paths = self._resolve_posted_images(toot_id)
        logger.info(f"[MastodonSharePhotos] Found {len(posted_image_paths)} posted image(s) for judge")

        rubric = (
            "Evaluate the Mastodon post on two preference dimensions and average them:\n\n"
            "1. Photo Selection Preference (50%): Does the chosen photo align with the user's "
            "interests, hobbies, and persona? The actual photo(s) posted are attached as images. "
            "Consider user logs and profile to determine what kind of photos the user would "
            "want to share.\n"
            "1.0 = photo clearly matches user interests/hobbies from their profile;\n"
            "0.5 = photo is acceptable but not strongly aligned with user preferences;\n"
            "0.0 = photo conflicts with user interests or is random/irrelevant.\n\n"
            "2. Caption Style Preference (50%): Does the caption match the user's "
            "communication style and social preferences? Consider tone, formality level, "
            "emoji usage, language habits from the user profile.\n"
            "1.0 = caption clearly matches user's communication style;\n"
            "0.5 = partially matches or style is generic;\n"
            "0.0 = conflicts with user's preferred style.\n\n"
            "Final = 0.5 * photo_preference + 0.5 * caption_preference."
        )
        judge_score, judge_reason = self.query_user_agent_judge(
            eval_data={"caption": toot_text, "app_context": "Mastodon"},
            rubric=rubric,
            chat_history=controller.user_agent_chat_history,
            images=posted_image_paths,
        )

        image_score = 0.6 if image_ok else 0.0
        caption_score = 0.4 * judge_score
        score = image_score + caption_score

        reason = (
            f"Account: {matched_user}; "
            f"Images: {'ok' if image_ok else 'failed'} ({image_msg}); "
            f"Caption: '{toot_text}'; "
            f"judge_score={judge_score:.2f}; final_score={score:.2f}; "
            f"judge_reason={judge_reason}"
        )
        return score, reason

    # ── Cleanup ──────────────────────────────────────────────────────

    def tear_down(self, controller: AndroidController) -> bool:
        super().tear_down(controller)
        try:
            for remote_path in getattr(self, "_remote_image_paths", []):
                controller.remove_file(remote_path)
        except Exception as exc:
            logger.error(f"Error cleaning up images: {exc}")

        try:
            mastodon.stop_mastodon_backend()
        except Exception as exc:
            logger.error(f"Failed to stop Mastodon backend: {exc}")
            return False
        return True
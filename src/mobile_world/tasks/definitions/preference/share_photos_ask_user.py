"""Preference task: share user-specific photos via email with persona-aligned message."""

import json
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any

from loguru import logger

from mobile_world.runtime.app_helpers import mail
from mobile_world.runtime.controller import AndroidController
from mobile_world.runtime.utils.helpers import execute_adb
from mobile_world.tasks.definitions.preference.base_prefrence_task import BasePrefrenceTask

DEFAULT_SHARE_DIR = "src/mobile_world/cache/users"
SUPPORTED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}

_PATH_KEYS = ("path", "filePath", "filepath", "localPath", "uri", "contentUri", "source", "src")
_PULL_SEARCH_DIRS = (
    "Android/data/com.gmailclone/files/attachments",
    "Download",
    "Pictures",
    "DCIM/Camera",
)


def _normalize_device_path(raw: str) -> str | None:
    """Normalize a device file path to /sdcard/... form, or return None."""
    v = (raw or "").strip()
    if not v:
        return None
    if v.startswith("file://"):
        v = v[7:]
    if "/sdcard/" in v:
        v = v[v.find("/sdcard/"):]
    elif "/storage/emulated/0/" in v:
        v = "/sdcard/" + v.split("/storage/emulated/0/", 1)[1]
    return v if v.startswith("/sdcard/") else None


def _resolve_media_id(media_id: str) -> str | None:
    """Query content provider for a media ID and return normalized path."""
    res = execute_adb(
        f'shell content query --uri content://media/external/file '
        f'--where "_id={media_id}" --projection _data',
    )
    if res.success and res.output:
        match = re.search(r"_data=([^\n\r,]+)", res.output)
        if match:
            return _normalize_device_path(match.group(1).strip())
    return None


class ShareFavoritePhotosPreferenceAskUserTask(BasePrefrenceTask):
    """Share user-specific photos via email with persona-aligned message."""

    task_tags = {"agent-user-interaction", "preference", "hybrid-eval", "lang-en", "hard"}
    GOAL_REQUEST = (
        "Help me send one photo I want to share to Kevin via email, "
        "and write a message that matches my communication style."
    )
    snapshot_tag = "init_state"
    share_root = DEFAULT_SHARE_DIR
    DEFAULT_PROFILE_PATH = "src/mobile_world/user_profile/user.yaml"
    EMAIL_ADDRESS = "kevin_zhang@example.com"
    app_names = {"Gallery", "Mail"}

    # ── Helpers ──

    def _project_root(self) -> Path:
        return Path(__file__).resolve().parents[5]

    def _user_slug(self) -> str:
        full_name = (
            self.user_profile.get("identity", {}).get("full_name", "")
            if isinstance(self.user_profile, dict) else ""
        )
        return re.sub(r"[^a-z0-9]+", "_", full_name.lower()).strip("_") or "user"

    def _email_share_dir(self) -> Path:
        return self._project_root() / self.share_root / self._user_slug() / "email_share"

    def _load_share_description(self) -> str:
        desc_path = self._email_share_dir() / "description.txt"
        try:
            return desc_path.read_text(encoding="utf-8").strip() if desc_path.exists() else ""
        except Exception as exc:
            logger.warning(f"Failed reading share description: {exc}")
            return ""

    def _resolve_email_share_images(self) -> list[Path]:
        share_dir = self._email_share_dir()
        if not share_dir.exists():
            logger.warning(f"Email share directory not found: {share_dir}")
            return []
        images = sorted(
            p for p in share_dir.iterdir()
            if p.is_file() and p.suffix.lower() in SUPPORTED_IMAGE_EXTS
        )
        if not images:
            logger.warning(f"No shareable images in: {share_dir}")
        return images

    def _pref_json(self, key: str) -> str:
        pref = (self.user_profile.get("preferences") or {}).get(key) or {}
        return json.dumps(pref, indent=2, ensure_ascii=False) if pref else "N/A"

    # ── Lifecycle ──

    def initialize_task_hook(self, controller: AndroidController) -> bool:
        execute_adb("shell settings put global auto_time 0")
        if not execute_adb("shell su root date 021014002026.00").success:
            execute_adb("shell date 021014002026.00")

        selected_files = self._resolve_email_share_images()[:1]
        self._expected_image_paths = [str(p) for p in selected_files]
        self._remote_image_paths: list[str] = []
        self._uses_seeded = bool(selected_files)

        # Build photo context line
        desc = self._load_share_description() if self._uses_seeded else ""
        if desc:
            photo_ctx = f"Photo content hint from your own folder: {desc}"
        elif not self._uses_seeded:
            photo_ctx = "No profile-specific seeded photo is provided. Base the email message on the image actually chosen in Gallery."
        else:
            photo_ctx = "Photo content hint is unavailable. Describe based on the actual image."

        self.relevant_information = self._build_relevant_information(
            current_context=(
                "You are about to send one photo to Kevin via email from images in Gallery. "
                f"The assistant may ask for preferred message style. {photo_ctx}"
            ),
            task_specific_detail=(
                f"My social preferences:\n{self._pref_json('social')}\n\n"
                f"My app preferences:\n{self._pref_json('apps')}\n\n"
                f"Kevin's email address: {self.EMAIL_ADDRESS}"
            ),
            extra_instruction="If asked to provide or revise a message, align it with the social preference above.",
        )

        if not selected_files:
            logger.info("No seeded email share assets for {}; skipping image push.", self.name)
            time.sleep(2)
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
        return True

    # ── Attachment pulling ──

    def _build_candidates(self, att: Any, name: str) -> list[str]:
        """Build ordered list of candidate device paths for an attachment."""
        candidates: list[str] = []
        media_id = Path(name).stem

        # Resolve by media ID
        if media_id.isdigit():
            if path := _resolve_media_id(media_id):
                candidates.append(path)

        # Resolve by content URI in attachment dict
        if isinstance(att, dict):
            uri = att.get("uri", "")
            if isinstance(uri, str) and "content://" in uri:
                uri_match = re.search(r"/(\d+)$", uri)
                if uri_match and uri_match.group(1) != media_id:
                    if path := _resolve_media_id(uri_match.group(1)):
                        candidates.append(path)
            for key in _PATH_KEYS:
                raw = att.get(key)
                if isinstance(raw, str) and (norm := _normalize_device_path(raw)):
                    candidates.append(norm)

        # Fallback: common directories
        candidates.extend(f"/sdcard/{d}/{name}" for d in _PULL_SEARCH_DIRS)
        return candidates

    def _pull_attachment_images(self, controller: AndroidController, attachments: list[Any]) -> list[str]:
        """Pull sent attachment images from device to local temp files."""
        if not isinstance(attachments, list) or not attachments:
            return []

        local_paths: list[str] = []
        for att in attachments:
            name = (
                (att.get("name") or att.get("filename") or att.get("fileName"))
                if isinstance(att, dict) else att if isinstance(att, str) else None
            )
            if not isinstance(name, str) or not name.strip():
                continue
            name = name.strip()
            suffix = Path(name).suffix.lower() or ".jpg"
            if suffix not in SUPPORTED_IMAGE_EXTS:
                continue

            for remote in dict.fromkeys(self._build_candidates(att, name)):
                try:
                    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix, prefix="email_att_")
                    tmp.close()
                    if controller.pull_file(remote, tmp.name).success and Path(tmp.name).stat().st_size > 0:
                        local_paths.append(tmp.name)
                        logger.info(f"Pulled attachment: {remote} -> {tmp.name}")
                        break
                    os.remove(tmp.name)
                except Exception:
                    pass
        return local_paths

    # ── Evaluation ──

    def is_successful(self, controller: AndroidController) -> tuple[float, str]:
        self._check_is_initialized()

        sent = mail.get_sent_email_info()
        if sent is None:
            return 0.0, "No email sent."

        to_addr = str(sent.get("to", "")).strip()
        body = str(sent.get("body", "")).strip()
        attachments = sent.get("attachments", [])

        # Rule-based checks (0.4 total)
        has_attachment = isinstance(attachments, list) and len(attachments) > 0
        recipient_ok = self.EMAIL_ADDRESS.lower() in to_addr.lower()
        rule_score = (0.2 if has_attachment else 0.0) + (0.2 if recipient_ok else 0.0)
        rule_details = (
            f"recipient={'ok' if recipient_ok else 'wrong'}({to_addr}), "
            f"attachments={'yes' if has_attachment else 'none'}({len(attachments) if has_attachment else 0})"
        )

        if not has_attachment and not recipient_ok:
            return rule_score, f"Rule-based: {rule_details}. No attachment and wrong recipient."

        # Pull & judge (0.6 total)
        pulled = self._pull_attachment_images(controller, attachments)
        judge_score, judge_reason = self.query_user_agent_judge(
            eval_data={"email_body": body, "email_to": to_addr, "sent_attachments": attachments, "app_context": "Mail"},
            rubric=(
                "Evaluate the photo-sharing email on two preference dimensions and average them:\n\n"
                "1. Photo Selection Preference (50%): Does the chosen photo align with the user's "
                "interests, hobbies, and persona? The actual photo(s) sent are attached as images. "
                "Consider user logs and profile to determine what kind of photos the user would want to share.\n"
                "1.0 = photo clearly matches user interests/hobbies from their profile;\n"
                "0.5 = photo is acceptable but not strongly aligned with user preferences;\n"
                "0.0 = photo conflicts with user interests or is random/irrelevant.\n\n"
                "2. Message Text Preference (50%): Does the email body match the user's "
                "communication style and social preferences? Consider tone, formality level, "
                "emoji usage, language habits from the user profile.\n"
                "1.0 = message clearly matches user's communication style;\n"
                "0.5 = partially matches or style is generic;\n"
                "0.0 = conflicts with user's preferred style.\n\n"
                "Final = 0.5 * photo_preference + 0.5 * message_preference."
            ),
            chat_history=controller.user_agent_chat_history,
            images=pulled,
        )
        for p in pulled:
            try:
                os.remove(p)
            except Exception:
                pass

        pref_score = 0.6 * judge_score
        total = rule_score + pref_score
        reason = (
            f"Rule({rule_score:.2f}): {rule_details}; "
            f"Pref({pref_score:.2f}): judge={judge_score:.2f}; "
            f"final={total:.2f}; Body: '{body[:200]}'; {judge_reason}"
        )
        return total, reason

    def tear_down(self, controller: AndroidController) -> bool:
        super().tear_down(controller)
        try:
            for path in getattr(self, "_remote_image_paths", []):
                controller.remove_file(path)
        except Exception as exc:
            logger.error(f"Error cleaning up images: {exc}")
            return False
        return True
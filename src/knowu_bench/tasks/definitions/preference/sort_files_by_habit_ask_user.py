"""Preference task: sort Files by user habit and judge satisfaction."""

import re
import tempfile
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from loguru import logger

from knowu_bench.runtime.controller import AndroidController
from knowu_bench.runtime.utils.helpers import execute_adb
from knowu_bench.tasks.definitions.preference.base_prefrence_task import BasePrefrenceTask


class SortFilesByHabitPreferenceAskUserTask(BasePrefrenceTask):
    task_tags = {"agent-user-interaction", "preference", "hybrid-eval", "hard"}
    GOAL_REQUEST = "请在 Files 应用中，按照我的习惯对 Download 里的文件进行排序。"
    snapshot_tag = "init_state"
    DEFAULT_PROFILE_PATH = "src/knowu_bench/user_profile/user.yaml"
    app_names = {"Files"}

    SORT_OPTIONS = (
        "File name (A to Z)",
        "File name (Z to A)",
        "Modified (newest first)",
        "Modified (oldest first)",
        "Type (A to Z)",
        "Type (Z to A)",
        "Size (largest first)",
        "Size (smallest first)",
    )
    DEFAULT_SORT_OPTION = "Modified (newest first)"
    FILE_HINTS = ("file", "files", "download", "document", "文件", "文档")
    OPPOSITE_OPTIONS = {
        "File name (A to Z)": "File name (Z to A)",
        "File name (Z to A)": "File name (A to Z)",
        "Modified (newest first)": "Modified (oldest first)",
        "Modified (oldest first)": "Modified (newest first)",
        "Type (A to Z)": "Type (Z to A)",
        "Type (Z to A)": "Type (A to Z)",
        "Size (largest first)": "Size (smallest first)",
        "Size (smallest first)": "Size (largest first)",
    }
    SORT_ALIASES = {
        "File name (A to Z)": ("file name (a to z)", "name (a to z)", "按文件名升序", "名称升序", "a到z", "a至z"),
        "File name (Z to A)": ("file name (z to a)", "name (z to a)", "按文件名降序", "名称降序", "z到a", "z至a"),
        "Modified (newest first)": ("modified (newest first)", "newest first", "最新"),
        "Modified (oldest first)": ("modified (oldest first)", "oldest first", "最旧"),
        "Type (A to Z)": ("type (a to z)", "类型升序"),
        "Type (Z to A)": ("type (z to a)", "类型降序"),
        "Size (largest first)": ("size (largest first)", "largest first", "最大"),
        "Size (smallest first)": ("size (smallest first)", "smallest first", "最小"),
    }
    MORE_OPTIONS_LABELS = ("More options", "更多选项")
    SORT_BY_LABELS = ("Sort by", "排序方式", "排序")
    FILE_NAME_PATTERN = re.compile(r"^[^\n]+\.[A-Za-z0-9]{1,8}$")
    DATE_PATTERN = re.compile(r"([A-Za-z]{3}\s+\d{1,2},\s+\d{4})")

    FILE_SPECS = (
        {"name": "alpha_notes.txt", "size": 2048, "mtime": "202602080900.00"},
        {"name": "bravo_video.mp4", "size": 8192, "mtime": "202602070900.00"},
        {"name": "charlie_receipt.pdf", "size": 1024, "mtime": "202602101100.00"},
        {"name": "delta_archive.zip", "size": 4096, "mtime": "202602090800.00"},
    )
    SORT_RULES = {
        "File name (A to Z)": (lambda x: x["name"].lower(), False),
        "File name (Z to A)": (lambda x: x["name"].lower(), True),
        "Modified (newest first)": (lambda x: x["mtime"], True),
        "Modified (oldest first)": (lambda x: x["mtime"], False),
        "Type (A to Z)": (lambda x: x["name"].rsplit(".", 1)[-1].lower(), False),
        "Type (Z to A)": (lambda x: x["name"].rsplit(".", 1)[-1].lower(), True),
        "Size (largest first)": (lambda x: int(x["size"]), True),
        "Size (smallest first)": (lambda x: int(x["size"]), False),
    }

    @classmethod
    def _normalize_sort_option(cls, text: str) -> str | None:
        raw = str(text or "").strip().lower()
        if not raw:
            return None
        compact = raw.replace(" ", "")
        for option, aliases in cls.SORT_ALIASES.items():
            if any(alias in raw or alias in compact for alias in aliases):
                return option
        return None

    def _infer_sort_from_profile(self) -> str | None:
        stack: list[tuple[str, Any]] = [("", self.user_profile)]
        while stack:
            path, value = stack.pop()
            if isinstance(value, dict):
                stack.extend((f"{path}.{k}" if path else str(k), v) for k, v in value.items())
                continue
            if isinstance(value, list):
                stack.extend((f"{path}[{i}]", v) for i, v in enumerate(value))
                continue
            if not isinstance(value, str):
                continue
            option = self._normalize_sort_option(value)
            if option and (value in self.SORT_OPTIONS or any(hint in path.lower() for hint in self.FILE_HINTS)):
                return option
        return None

    def _resolve_expected_sort(self, chat_history: list[dict]) -> tuple[str, str]:
        profile_sort = getattr(self, "_profile_sort_option", None)
        if profile_sort:
            return profile_sort, "profile"
        for turn in reversed(chat_history or []):
            if str(turn.get("role", "")).lower() != "assistant":
                continue
            option = self._normalize_sort_option(turn.get("content", ""))
            if option:
                return option, "chat_history"
        return self.DEFAULT_SORT_OPTION, "default_fallback"

    def _prepare_download_files(self, controller: AndroidController) -> None:
        device = controller.device
        for folder in ("/sdcard/Download", "/sdcard/Downloads"):
            execute_adb(f"-s {device} shell mkdir -p {folder}")
            execute_adb(f"-s {device} shell rm -rf {folder}/*")
        for spec in self.FILE_SPECS:
            path = f"/sdcard/Download/{spec['name']}"
            execute_adb(
                f"-s {device} shell dd if=/dev/zero of={path} bs=1 count={int(spec['size'])}",
                output=False,
            )
            execute_adb(f"-s {device} shell touch -m -t {spec['mtime']} {path}", output=False)
        for pkg in ("com.google.android.documentsui", "com.android.documentsui", "com.android.providers.downloads"):
            execute_adb(f"-s {device} shell am force-stop {pkg}", output=False)

    def initialize_task_hook(self, controller: AndroidController) -> bool:
        execute_adb(f"-s {controller.device} shell settings put global auto_time 0")
        res = execute_adb(f"-s {controller.device} shell su root date 021014002026.00")
        if not res.success:
            execute_adb(f"-s {controller.device} shell date 021014002026.00")

        self._prepare_download_files(controller)
        self._profile_sort_option = self._infer_sort_from_profile()
        pref_note = (
            f"Task-specific extracted preference from profile: '{self._profile_sort_option}'. "
            "If asked, answer with that exact option.\n"
            if self._profile_sort_option
            else f"No explicit Files sort preference is found in profile. If asked, use default habit: "
            f"'{self.DEFAULT_SORT_OPTION}'.\n"
        )
        self.relevant_information = (
            "Here is your complete User Persona/Profile. You must act strictly according to this identity:\n\n"
            f"{self.persona_text}\n\n{pref_note}Available options in this task are:\n- "
            + "\n- ".join(self.SORT_OPTIONS)
        )
        return True

    @staticmethod
    def _dump_xml_text(controller: AndroidController, tag: str) -> str | None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            xml_path = controller.get_xml(tag, tmp_dir)
            if not isinstance(xml_path, str):
                return None
            try:
                return Path(xml_path).read_text(encoding="utf-8", errors="ignore")
            except OSError:
                return None

    @staticmethod
    def _parse_bounds_center(bounds: str) -> tuple[int, int] | None:
        match = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", str(bounds or ""))
        if not match:
            return None
        x1, y1, x2, y2 = map(int, match.groups())
        return (x1 + x2) // 2, (y1 + y2) // 2

    def _parse_ui_state(self, xml_text: str) -> tuple[ET.Element | None, list[str], str | None]:
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return None, [], None
        labels: list[str] = []
        selected = None
        for node in root.iter("node"):
            text = str(node.attrib.get("text", "")).strip()
            desc = str(node.attrib.get("content-desc", "")).strip()
            if text in self.SORT_OPTIONS and (
                node.attrib.get("checked") == "true" or node.attrib.get("selected") == "true"
            ):
                selected = text
            for value in (text, desc):
                if value and value not in labels:
                    labels.append(value)
        return root, labels, selected

    def _find_tap_target(self, root: ET.Element, labels: tuple[str, ...]) -> tuple[int, int] | None:
        label_set = set(labels)
        for node in root.iter("node"):
            text = str(node.attrib.get("text", "")).strip()
            desc = str(node.attrib.get("content-desc", "")).strip()
            if text in label_set or desc in label_set:
                center = self._parse_bounds_center(node.attrib.get("bounds", ""))
                if center:
                    return center
        return None

    def _probe_selected_sort_from_menu(self, controller: AndroidController) -> str | None:
        xml = self._dump_xml_text(controller, "files_state_menu_0")
        if not xml:
            return None
        root, _, _ = self._parse_ui_state(xml)
        if root is None:
            return None
        more_btn = self._find_tap_target(root, self.MORE_OPTIONS_LABELS)
        if not more_btn:
            return None

        controller.tap(*more_btn)
        time.sleep(0.35)
        xml = self._dump_xml_text(controller, "files_state_menu_1")
        if not xml:
            controller.back()
            return None
        root, _, _ = self._parse_ui_state(xml)
        if root is None:
            controller.back()
            return None
        sort_btn = self._find_tap_target(root, self.SORT_BY_LABELS)
        if not sort_btn:
            controller.back()
            return None

        controller.tap(*sort_btn)
        time.sleep(0.35)
        xml = self._dump_xml_text(controller, "files_state_menu_2")
        selected = None
        if xml:
            _, _, selected = self._parse_ui_state(xml)
        controller.back()
        time.sleep(0.15)
        controller.back()
        return selected

    def _infer_modified_sort_from_labels(self, labels: list[str]) -> str | None:
        dates: list[datetime] = []
        for i, label in enumerate(labels):
            if not self.FILE_NAME_PATTERN.match(label):
                continue
            detail = labels[i + 1] if i + 1 < len(labels) else ""
            match = self.DATE_PATTERN.search(detail)
            if not match:
                continue
            try:
                dates.append(datetime.strptime(match.group(1), "%b %d, %Y"))
            except ValueError:
                continue
        if len(dates) < 2:
            return None
        if all(dates[i] >= dates[i + 1] for i in range(len(dates) - 1)):
            return "Modified (newest first)"
        if all(dates[i] <= dates[i + 1] for i in range(len(dates) - 1)):
            return "Modified (oldest first)"
        return None

    def _read_files_state(self, controller: AndroidController) -> tuple[list[str], str | None]:
        xml = self._dump_xml_text(controller, "files_state_eval")
        if not xml:
            return [], None
        _, labels, selected = self._parse_ui_state(xml)
        observed = [label for label in labels if self.FILE_NAME_PATTERN.match(label)]
        if selected:
            return observed, selected

        selected = self._probe_selected_sort_from_menu(controller)
        if selected:
            return observed, selected
        return observed, self._infer_modified_sort_from_labels(labels)

    @staticmethod
    def _pairwise_score(items: list[str], key_fn: Callable[[str], Any], reverse: bool = False) -> float:
        if len(items) < 2:
            return 0.0
        keys = [key_fn(item) for item in items]
        total = 0
        good = 0
        for i, left in enumerate(keys):
            for right in keys[i + 1 :]:
                total += 1
                if (left >= right) if reverse else (left <= right):
                    good += 1
        return good / total if total else 0.0

    def _pairwise_order_score(self, observed: list[str], expected: list[str]) -> float:
        if len(observed) < 2 or len(expected) < 2:
            return 0.0
        idx = {name: i for i, name in enumerate(observed)}
        common = [name for name in expected if name in idx]
        return self._pairwise_score(common, key_fn=idx.get)

    def _infer_sort_from_observed_order(self, observed_order: list[str]) -> str | None:
        if len(observed_order) < 3:
            return None

        candidates = [
            ("File name (A to Z)", lambda x: x.lower(), False),
            ("File name (Z to A)", lambda x: x.lower(), True),
        ]
        exts = [name.rsplit(".", 1)[-1].lower() for name in observed_order if "." in name]
        if len(set(exts)) >= 2:
            candidates.extend(
                [
                    ("Type (A to Z)", lambda x: x.rsplit(".", 1)[-1].lower() if "." in x else "", False),
                    ("Type (Z to A)", lambda x: x.rsplit(".", 1)[-1].lower() if "." in x else "", True),
                ]
            )

        ranked = sorted(
            ((opt, self._pairwise_score(observed_order, key_fn=key_fn, reverse=rev)) for opt, key_fn, rev in candidates),
            key=lambda x: x[1],
            reverse=True,
        )
        if not ranked:
            return None
        best_option, best_score = ranked[0]
        second_score = ranked[1][1] if len(ranked) > 1 else 0.0
        if best_score >= 0.92 and (best_score - second_score) >= 0.08:
            return best_option
        return None

    def _expected_order(self, sort_option: str) -> list[str]:
        rule = self.SORT_RULES.get(sort_option)
        if not rule:
            return []
        key_fn, reverse = rule
        return [item["name"] for item in sorted(self.FILE_SPECS, key=key_fn, reverse=reverse)]

    def _seed_order_score(self, observed_order: list[str], expected_sort: str) -> float:
        seed_names = {item["name"] for item in self.FILE_SPECS}
        common_seed = [name for name in observed_order if name in seed_names]
        if len(common_seed) < 2:
            return 0.0
        if (len(common_seed) / max(len(observed_order), 1)) < 0.6:
            return 0.0
        return self._pairwise_order_score(observed_order, self._expected_order(expected_sort))

    def is_successful(self, controller: AndroidController) -> float | tuple[float, str]:
        self._check_is_initialized()
        chat_history = getattr(controller, "user_agent_chat_history", [])
        expected_sort, source = self._resolve_expected_sort(chat_history)
        observed_order, selected_sort_ui = self._read_files_state(controller)
        inferred_sort_from_order = self._infer_sort_from_observed_order(observed_order)
        detected_sort = selected_sort_ui or inferred_sort_from_order

        if detected_sort == expected_sort:
            sort_match = 1.0
        elif detected_sort and self.OPPOSITE_OPTIONS.get(expected_sort) == detected_sort:
            sort_match = 0.5
        elif detected_sort:
            sort_match = 0.0
        else:
            sort_match = self._seed_order_score(observed_order, expected_sort)

        asked_user = bool(chat_history)
        base_score = 0.8 * sort_match + (0.2 if asked_user else 0.0)
        logger.info(
            f"[Eval Phase 1] expected_sort={expected_sort}, source={source}, observed_order={observed_order[:10]}, "
            f"selected_sort_option_ui={selected_sort_ui}, inferred_sort_from_order={inferred_sort_from_order}, "
            f"detected_sort={detected_sort}, sort_match={sort_match:.2f}, asked_user={asked_user}, base_score={base_score:.2f}"
        )

        rubric = (
            "Evaluate with only three dimensions:\n"
            "1) Clarification Behavior (35%): asked preference for ambiguous request?\n"
            "2) Sort Option Correctness (50%):\n"
            "   First infer the likely sorting mode from observed_order. Then score whether that inferred mode "
            "   matches expected_sort_option. If observed_order indicates mismatch, do not give full score.\n"
            "3) Persona/Interaction Consistency (15%): interaction + final choice aligned?\n"
            "Do NOT score execution quality here. Execution is already in deterministic base_score.\n"
            "Final = 0.35*clarification + 0.5*option_correctness + 0.15*persona_alignment."
        )
        user_agent_score, judge_reasoning = self.query_user_agent_judge(
            eval_data={
                "expected_sort_option": expected_sort,
                "expected_sort_source": source,
                "selected_sort_option_ui": selected_sort_ui,
                "detected_sort_option": detected_sort,
                "observed_order": observed_order,
                "asked_user": asked_user,
                "available_sort_options": list(self.SORT_OPTIONS),
                "chat_history_tail": chat_history[-10:] if isinstance(chat_history, list) else [],
            },
            rubric=rubric,
            chat_history=chat_history,
        )
        if detected_sort and detected_sort != expected_sort:
            user_agent_score = min(user_agent_score, 0.5)
            judge_reasoning = (
                f"[Deterministic cap] detected_sort_option={detected_sort} "
                f"!= expected_sort_option={expected_sort}. {judge_reasoning}"
            )

        final_score = 0.4 * base_score + 0.6 * user_agent_score
        reason = (
            f"Expected sort: {expected_sort}. Observed order: {observed_order}. "
            f"Base: {base_score:.2f} (sort_match={sort_match:.2f}, asked_user={asked_user}, "
            f"selected_sort_option_ui={selected_sort_ui}, inferred_sort_from_order={inferred_sort_from_order}, "
            f"detected_sort={detected_sort}). Preference judge: {user_agent_score:.2f}. "
            f"Judge reasoning: {judge_reasoning}"
        )
        return final_score, reason

    def tear_down(self, controller: AndroidController) -> bool:
        super().tear_down(controller)
        device = controller.device
        for spec in self.FILE_SPECS:
            execute_adb(f"-s {device} shell rm -f /sdcard/Download/{spec['name']}", output=False)
        return True

"""General task: sort files in Download folder by modification time."""

import re
import tempfile
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

from loguru import logger

from mobile_world.runtime.controller import AndroidController
from mobile_world.runtime.utils.helpers import execute_adb
from mobile_world.tasks.base import BaseTask


class SortFilesGeneralTask(BaseTask):
    """Sort files in the Download folder by modification time (newest first)."""

    task_tags = {"general", "easy"}
    snapshot_tag = "init_state"
    app_names = {"Files"}
    goal = "请在 Files 应用中，将 Download 文件夹里的文件按修改时间降序排列（最新的排在最前面）。"

    EXPECTED_SORT = "Modified (newest first)"
    FILE_SPECS = (
        {"name": "alpha_notes.txt", "size": 2048, "mtime": "202602080900.00"},
        {"name": "bravo_video.mp4", "size": 8192, "mtime": "202602070900.00"},
        {"name": "charlie_receipt.pdf", "size": 1024, "mtime": "202602101100.00"},
        {"name": "delta_archive.zip", "size": 4096, "mtime": "202602090800.00"},
    )
    SORT_RULES = {
        "Modified (newest first)": (lambda x: x["mtime"], True),
        "Modified (oldest first)": (lambda x: x["mtime"], False),
    }
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
    MORE_OPTIONS_LABELS = ("More options", "更多选项")
    SORT_BY_LABELS = ("Sort by", "排序方式", "排序")
    FILE_NAME_PATTERN = re.compile(r"^[^\n]+\.[A-Za-z0-9]{1,8}$")
    DATE_PATTERN = re.compile(r"([A-Za-z]{3}\s+\d{1,2},\s+\d{4})")

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

    def _expected_order(self) -> list[str]:
        rule = self.SORT_RULES.get(self.EXPECTED_SORT)
        if not rule:
            return []
        key_fn, reverse = rule
        return [item["name"] for item in sorted(self.FILE_SPECS, key=key_fn, reverse=reverse)]

    def _load_ui_state(self, controller: AndroidController, tag: str) -> tuple[ET.Element | None, list[str], str | None]:
        xml = self._dump_xml_text(controller, tag)
        if not xml:
            return None, [], None
        return self._parse_ui_state(xml)

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
        root, _, selected = self._load_ui_state(controller, "files_state_menu_0")
        if root is None:
            return None
        if selected:
            return selected

        more_btn = self._find_tap_target(root, self.MORE_OPTIONS_LABELS)
        if not more_btn:
            return None

        controller.tap(*more_btn)
        time.sleep(0.35)
        root, _, selected = self._load_ui_state(controller, "files_state_menu_1")
        if root is None:
            controller.back()
            return None
        if selected:
            controller.back()
            return selected

        sort_btn = self._find_tap_target(root, self.SORT_BY_LABELS)
        if not sort_btn:
            controller.back()
            return None

        controller.tap(*sort_btn)
        time.sleep(0.35)
        _, _, selected = self._load_ui_state(controller, "files_state_menu_2")
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
        _, labels, selected = self._load_ui_state(controller, "files_state_eval")
        observed = [label for label in labels if self.FILE_NAME_PATTERN.match(label)]
        if selected:
            return observed, selected

        selected = self._probe_selected_sort_from_menu(controller)
        if selected:
            return observed, selected
        return observed, self._infer_modified_sort_from_labels(labels)

    def is_successful(self, controller: AndroidController) -> float | tuple[float, str]:
        self._check_is_initialized()

        observed, selected_sort_ui = self._read_files_state(controller)
        expected = self._expected_order()

        if selected_sort_ui == self.EXPECTED_SORT:
            reason = (
                f"Selected sort option detected as {selected_sort_ui}. "
                f"Observed files: {observed[:10]}"
            )
            logger.info(f"[Eval] {reason}")
            return 1.0, reason

        if selected_sort_ui:
            score = 0.5 if selected_sort_ui == "Modified (oldest first)" else 0.0
            reason = (
                f"Selected sort option detected as {selected_sort_ui}, expected {self.EXPECTED_SORT}. "
                f"Observed files: {observed[:10]}. Score: {score:.1f}"
            )
            logger.info(f"[Eval] {reason}")
            return score, reason

        if not observed:
            return 0.0, "Failure: Could not read sort option or file order from Files UI."

        seed_names = {item["name"] for item in self.FILE_SPECS}
        common = [name for name in observed if name in seed_names]

        if len(common) < 2:
            return 0.0, f"Failure: Only {len(common)} seed files visible in UI."

        if common == expected:
            score = 1.0
        elif common == list(reversed(expected)):
            score = 0.5
        else:
            score = 0.2

        reason = (
            f"Expected order: {expected}. Observed: {common}. "
            f"Score: {score:.1f}"
        )
        logger.info(f"[Eval] {reason}")
        return score, reason

    def tear_down(self, controller: AndroidController) -> bool:
        super().tear_down(controller)
        device = controller.device
        for spec in self.FILE_SPECS:
            execute_adb(f"-s {device} shell rm -f /sdcard/Download/{spec['name']}", output=False)
        return True
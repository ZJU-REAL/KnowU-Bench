#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import re
from dataclasses import dataclass
from pathlib import Path


SUCCESS_THRESHOLD = 0.99


@dataclass
class TaskResult:
    task_name: str
    score: float

    @property
    def is_success(self) -> bool:
        return self.score > SUCCESS_THRESHOLD

    @property
    def base_task_name(self) -> str:
        return self.task_name.split("@", 1)[0]


@dataclass
class AccuracyStat:
    success: int = 0
    total: int = 0

    def add(self, is_success: bool) -> None:
        self.total += 1
        if is_success:
            self.success += 1

    @property
    def accuracy(self) -> float:
        return self.success / self.total if self.total else 0.0


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[1]
    default_task_defs = repo_root / "src" / "mobile_world" / "tasks" / "definitions"

    parser = argparse.ArgumentParser(
        description=(
            "Compute accuracy for preference/routine tasks and L1/L2 tasks "
            "from a MobileWorld traj_logs directory."
        )
    )
    parser.add_argument("log_root", type=Path, help="Path to the traj_logs run directory.")
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Specific eval_report JSON to use. Defaults to the latest one in log_root.",
    )
    parser.add_argument(
        "--task-definitions-root",
        type=Path,
        default=default_task_defs,
        help="Path to src/mobile_world/tasks/definitions.",
    )
    parser.add_argument(
        "--include-no-results-as-failures",
        action="store_true",
        help="Include tasks without results in the denominator as failures.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON instead of a text table.",
    )
    return parser.parse_args()


def find_latest_eval_report(log_root: Path) -> Path | None:
    reports = sorted(log_root.glob("eval_report_*.json"))
    return reports[-1] if reports else None


def load_results_from_eval_report(report_path: Path) -> tuple[list[TaskResult], list[str], str]:
    with report_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    results = [
        TaskResult(task_name=item["task_name"], score=float(item["score"]))
        for item in data.get("tasks_with_results", [])
    ]
    no_results = list(data.get("tasks_with_no_results", []))
    return results, no_results, f"eval_report:{report_path.name}"


def parse_score_from_result_file(result_path: Path) -> float | None:
    pattern = re.compile(r"^score:\s*([-+]?\d*\.?\d+)\s*$", re.IGNORECASE)

    with result_path.open("r", encoding="utf-8") as f:
        for raw_line in f:
            match = pattern.match(raw_line.strip())
            if match:
                return float(match.group(1))
    return None


def load_results_from_task_dirs(log_root: Path) -> tuple[list[TaskResult], list[str], str]:
    results: list[TaskResult] = []
    no_results: list[str] = []

    for task_dir in sorted(p for p in log_root.iterdir() if p.is_dir() and "_backup_" not in p.name):
        result_path = task_dir / "result.txt"
        if not result_path.exists():
            no_results.append(task_dir.name)
            continue

        score = parse_score_from_result_file(result_path)
        if score is None:
            no_results.append(task_dir.name)
            continue

        results.append(TaskResult(task_name=task_dir.name, score=score))

    return results, no_results, "task_dirs"


def extract_task_tags(task_definitions_root: Path) -> dict[str, set[str]]:
    task_tags_by_class: dict[str, set[str]] = {}

    for file_path in sorted(task_definitions_root.rglob("*.py")):
        if file_path.name == "__init__.py":
            continue

        try:
            tree = ast.parse(file_path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue

            tags: set[str] = set()
            for item in node.body:
                if not isinstance(item, ast.Assign):
                    continue

                for target in item.targets:
                    if isinstance(target, ast.Name) and target.id == "task_tags":
                        try:
                            value = ast.literal_eval(item.value)
                        except (ValueError, SyntaxError):
                            continue
                        if isinstance(value, (set, list, tuple)):
                            tags = {str(tag) for tag in value}
            if tags:
                task_tags_by_class[node.name] = tags

    return task_tags_by_class


def infer_level(tags: set[str]) -> str | None:
    if any(tag == "L1" or tag.startswith("L1") for tag in tags):
        return "L1"
    if any(tag == "L2" or tag.startswith("L2") for tag in tags):
        return "L2"
    return None


def groups_for_task(base_task_name: str, tags: set[str]) -> list[str]:
    groups: list[str] = []

    if "preference" in tags:
        groups.append("preference")
    if "routine" in tags:
        groups.append("routine")

    level = infer_level(tags)
    if level is not None:
        groups.append(level)

    if not groups and "preference" in base_task_name.lower():
        groups.append("preference")

    return groups


def build_stats(
    results: list[TaskResult],
    no_results: list[str],
    task_tags_by_class: dict[str, set[str]],
    include_no_results_as_failures: bool,
) -> tuple[dict[str, AccuracyStat], list[str]]:
    stats = {
        "preference": AccuracyStat(),
        "routine": AccuracyStat(),
        "L1": AccuracyStat(),
        "L2": AccuracyStat(),
    }
    unmatched_tasks: list[str] = []

    for result in results:
        tags = task_tags_by_class.get(result.base_task_name, set())
        groups = groups_for_task(result.base_task_name, tags)
        if not groups:
            unmatched_tasks.append(result.task_name)
            continue
        for group in groups:
            stats[group].add(result.is_success)

    if include_no_results_as_failures:
        for task_name in no_results:
            base_task_name = task_name.split("@", 1)[0]
            tags = task_tags_by_class.get(base_task_name, set())
            groups = groups_for_task(base_task_name, tags)
            if not groups:
                unmatched_tasks.append(task_name)
                continue
            for group in groups:
                stats[group].add(False)

    return stats, unmatched_tasks


def format_text_output(
    log_root: Path,
    source: str,
    stats: dict[str, AccuracyStat],
    total_results: int,
    total_no_results: int,
    include_no_results_as_failures: bool,
    unmatched_tasks: list[str],
) -> str:
    lines = [
        f"log_root: {log_root}",
        f"data_source: {source}",
        f"success_rule: score > {SUCCESS_THRESHOLD}",
        f"tasks_with_results: {total_results}",
        (
            "tasks_with_no_results: "
            f"{total_no_results} "
            f"(included_as_failures={str(include_no_results_as_failures).lower()})"
        ),
        "",
        f"{'group':<12}{'success/total':<16}{'accuracy':<12}",
        "-" * 40,
    ]

    for group in ("preference", "routine", "L1", "L2"):
        stat = stats[group]
        lines.append(f"{group:<12}{stat.success}/{stat.total:<14}{stat.accuracy:.2%}")

    if unmatched_tasks:
        lines.extend(
            [
                "",
                f"unmatched_tasks: {len(unmatched_tasks)}",
                *[f"- {task_name}" for task_name in sorted(set(unmatched_tasks))[:20]],
            ]
        )

    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    log_root = args.log_root.resolve()

    if not log_root.exists():
        raise SystemExit(f"log_root does not exist: {log_root}")

    report_path = args.report.resolve() if args.report else find_latest_eval_report(log_root)
    if report_path is not None and not report_path.exists():
        raise SystemExit(f"report does not exist: {report_path}")

    if report_path is not None:
        results, no_results, source = load_results_from_eval_report(report_path)
    else:
        results, no_results, source = load_results_from_task_dirs(log_root)

    task_tags_by_class = extract_task_tags(args.task_definitions_root.resolve())
    stats, unmatched_tasks = build_stats(
        results=results,
        no_results=no_results,
        task_tags_by_class=task_tags_by_class,
        include_no_results_as_failures=args.include_no_results_as_failures,
    )

    if args.json:
        payload = {
            "log_root": str(log_root),
            "data_source": source,
            "success_rule": f"score > {SUCCESS_THRESHOLD}",
            "tasks_with_results": len(results),
            "tasks_with_no_results": len(no_results),
            "include_no_results_as_failures": args.include_no_results_as_failures,
            "stats": {
                key: {
                    "success": value.success,
                    "total": value.total,
                    "accuracy": value.accuracy,
                }
                for key, value in stats.items()
            },
            "unmatched_tasks": sorted(set(unmatched_tasks)),
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    print(
        format_text_output(
            log_root=log_root,
            source=source,
            stats=stats,
            total_results=len(results),
            total_no_results=len(no_results),
            include_no_results_as_failures=args.include_no_results_as_failures,
            unmatched_tasks=unmatched_tasks,
        )
    )


if __name__ == "__main__":
    main()

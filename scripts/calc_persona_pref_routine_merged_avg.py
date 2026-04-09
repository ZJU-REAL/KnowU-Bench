#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class TaskResult:
    task_name: str
    score: float

    @property
    def base_task_name(self) -> str:
        return self.task_name.split("@", 1)[0]

    @property
    def persona(self) -> str:
        return self.task_name.split("@", 1)[1] if "@" in self.task_name else "general"


@dataclass
class ScoreStat:
    sum_score: float = 0.0
    avg_denominator: int = 0
    tasks_with_results: int = 0
    tasks_with_no_results: int = 0

    def add_result(self, score: float) -> None:
        self.sum_score += score
        self.avg_denominator += 1
        self.tasks_with_results += 1

    def add_no_result(self, include_as_zero: bool) -> None:
        self.tasks_with_no_results += 1
        if include_as_zero:
            self.avg_denominator += 1

    @property
    def avg_score(self) -> float | None:
        if self.avg_denominator == 0:
            return None
        return self.sum_score / self.avg_denominator


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[1]
    default_task_defs = repo_root / "src" / "mobile_world" / "tasks" / "definitions"

    parser = argparse.ArgumentParser(
        description=(
            "Compute persona-level average score over merged preference+routine tasks "
            "from a MobileWorld traj_logs run directory."
        )
    )
    parser.add_argument("log_root", type=Path, help="Path to one traj_logs run directory.")
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
        "--exclude-no-results",
        action="store_true",
        help="Exclude tasks without results from the avg-score denominator. Default: include them as 0.",
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


def is_pref_or_routine(base_task_name: str, tags: set[str]) -> bool:
    if "preference" in tags or "routine" in tags:
        return True

    lowered = base_task_name.lower()
    return "preference" in lowered or "routine" in lowered


def build_persona_stats(
    results: list[TaskResult],
    no_results: list[str],
    task_tags_by_class: dict[str, set[str]],
    include_no_results_as_zero: bool,
) -> tuple[dict[str, ScoreStat], list[str]]:
    persona_stats: dict[str, ScoreStat] = {}
    unmatched_tasks: list[str] = []

    def ensure_persona(persona: str) -> ScoreStat:
        if persona not in persona_stats:
            persona_stats[persona] = ScoreStat()
        return persona_stats[persona]

    for result in results:
        tags = task_tags_by_class.get(result.base_task_name, set())
        if result.persona == "general" or not is_pref_or_routine(result.base_task_name, tags):
            unmatched_tasks.append(result.task_name)
            continue
        ensure_persona(result.persona).add_result(result.score)

    for task_name in no_results:
        base_task_name = task_name.split("@", 1)[0]
        persona = task_name.split("@", 1)[1] if "@" in task_name else "general"
        tags = task_tags_by_class.get(base_task_name, set())
        if persona == "general" or not is_pref_or_routine(base_task_name, tags):
            unmatched_tasks.append(task_name)
            continue
        ensure_persona(persona).add_no_result(include_no_results_as_zero)

    return persona_stats, unmatched_tasks


def format_score(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.4f}"


def format_text_output(
    log_root: Path,
    source: str,
    include_no_results_as_zero: bool,
    persona_stats: dict[str, ScoreStat],
    unmatched_tasks: list[str],
) -> str:
    lines = [
        f"log_root: {log_root}",
        f"data_source: {source}",
        "no_result_policy: "
        + ("counted_as_zero_in_avg" if include_no_results_as_zero else "excluded_from_avg"),
        "task_scope: merged_preference_plus_routine",
        "",
        f"{'persona':<12}{'avg_score':<12}{'with_result':<14}{'no_result':<12}{'denominator':<12}",
        "-" * 62,
    ]

    for persona in sorted(persona_stats):
        stat = persona_stats[persona]
        lines.append(
            f"{persona:<12}{format_score(stat.avg_score):<12}{stat.tasks_with_results:<14}{stat.tasks_with_no_results:<12}{stat.avg_denominator:<12}"
        )

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
    include_no_results_as_zero = not args.exclude_no_results
    persona_stats, unmatched_tasks = build_persona_stats(
        results=results,
        no_results=no_results,
        task_tags_by_class=task_tags_by_class,
        include_no_results_as_zero=include_no_results_as_zero,
    )

    if args.json:
        payload = {
            "log_root": str(log_root),
            "data_source": source,
            "include_no_results_as_zero": include_no_results_as_zero,
            "task_scope": "merged_preference_plus_routine",
            "personas": {
                persona: {
                    "avg_score": stat.avg_score,
                    "tasks_with_results": stat.tasks_with_results,
                    "tasks_with_no_results": stat.tasks_with_no_results,
                    "avg_denominator": stat.avg_denominator,
                    "sum_score": stat.sum_score,
                }
                for persona, stat in sorted(persona_stats.items())
            },
            "unmatched_tasks": sorted(set(unmatched_tasks)),
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    print(
        format_text_output(
            log_root=log_root,
            source=source,
            include_no_results_as_zero=include_no_results_as_zero,
            persona_stats=persona_stats,
            unmatched_tasks=unmatched_tasks,
        )
    )


if __name__ == "__main__":
    main()

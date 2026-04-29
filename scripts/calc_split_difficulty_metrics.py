#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SUCCESS_THRESHOLD = 0.99
SPLITS = ("general", "personalized", "proactive")
DIFFICULTIES = ("easy", "hard")


@dataclass
class TaskDefinitionMeta:
    tags: set[str]
    source_group: str | None
    split: str | None
    difficulty: str | None


@dataclass
class TaskResult:
    task_name: str
    score: float

    @property
    def base_task_name(self) -> str:
        return self.task_name.split("@", 1)[0]

    @property
    def is_success(self) -> bool:
        return self.score > SUCCESS_THRESHOLD


@dataclass
class MetricStat:
    success: int = 0
    total: int = 0
    tasks_with_results: int = 0
    tasks_with_no_results: int = 0
    sum_score: float = 0.0
    score_denominator: int = 0

    def add_result(self, score: float, is_success: bool, count_score: bool) -> None:
        self.total += 1
        self.tasks_with_results += 1
        if is_success:
            self.success += 1
        if count_score:
            self.sum_score += score
            self.score_denominator += 1

    def add_no_result(self, count_failure: bool, count_zero_score: bool) -> None:
        self.tasks_with_no_results += 1
        if count_failure:
            self.total += 1
        if count_zero_score:
            self.score_denominator += 1

    @property
    def success_rate(self) -> float | None:
        if self.total == 0:
            return None
        return self.success / self.total

    @property
    def average_score(self) -> float | None:
        if self.score_denominator == 0:
            return None
        return self.sum_score / self.score_denominator


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[1]
    default_task_defs = repo_root / "src" / "knowu_bench" / "tasks" / "definitions"

    parser = argparse.ArgumentParser(
        description=(
            "Compute SR and difficulty-sliced metrics for general/personalized/proactive "
            "tasks from a MobileWorld traj_logs run."
        )
    )
    parser.add_argument("log_root", type=Path, help="Path to one traj_logs run directory.")
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Specific eval_report JSON to use. Defaults to the latest one in log_root when available.",
    )
    parser.add_argument(
        "--source",
        choices=("auto", "eval_report", "task_dirs"),
        default="auto",
        help=(
            "Data source for episode scores. "
            "'auto' prefers eval_report_*.json when available, otherwise scans task directories."
        ),
    )
    parser.add_argument(
        "--task-definitions-root",
        type=Path,
        default=default_task_defs,
        help="Path to src/knowu_bench/tasks/definitions.",
    )
    parser.add_argument(
        "--include-no-results-as-failures",
        action="store_true",
        help="Count tasks without result.txt/score as failures in SR denominator.",
    )
    parser.add_argument(
        "--include-no-results-as-zero-in-personalized-avg",
        action="store_true",
        help="Count missing-result personalized tasks as 0 in Avg Score denominator.",
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


def load_results(
    log_root: Path,
    source: str,
    report_path: Path | None,
) -> tuple[list[TaskResult], list[str], str]:
    if source == "eval_report":
        if report_path is None:
            raise SystemExit(
                "No eval_report found. Use --report to specify one, or switch to --source task_dirs."
            )
        return load_results_from_eval_report(report_path)

    if source == "task_dirs":
        return load_results_from_task_dirs(log_root)

    if report_path is not None:
        return load_results_from_eval_report(report_path)
    return load_results_from_task_dirs(log_root)


def extract_task_tags_from_class(node: ast.ClassDef) -> set[str]:
    for item in node.body:
        if isinstance(item, ast.Assign):
            targets = item.targets
            value_node = item.value
        elif isinstance(item, ast.AnnAssign):
            targets = [item.target]
            value_node = item.value
        else:
            continue

        if value_node is None:
            continue

        for target in targets:
            if not isinstance(target, ast.Name) or target.id != "task_tags":
                continue
            try:
                value = ast.literal_eval(value_node)
            except (ValueError, SyntaxError):
                return set()
            if isinstance(value, (set, list, tuple)):
                return {str(tag) for tag in value}
    return set()


def infer_split(base_task_name: str, tags: set[str], source_group: str | None) -> str | None:
    if "general" in tags or source_group == "general":
        return "general"
    if "preference" in tags or source_group == "preference":
        return "personalized"
    if "routine" in tags or source_group == "routine":
        return "proactive"

    lowered = base_task_name.lower()
    if "preference" in lowered:
        return "personalized"
    if "routine" in lowered:
        return "proactive"
    return None


def infer_difficulty(tags: set[str]) -> str | None:
    has_easy = "easy" in tags
    has_hard = "hard" in tags
    if has_easy and not has_hard:
        return "easy"
    if has_hard and not has_easy:
        return "hard"
    return None


def extract_task_metadata(task_definitions_root: Path) -> dict[str, TaskDefinitionMeta]:
    task_meta_by_class: dict[str, TaskDefinitionMeta] = {}

    for file_path in sorted(task_definitions_root.rglob("*.py")):
        if file_path.name == "__init__.py":
            continue

        try:
            tree = ast.parse(file_path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue

        try:
            rel_path = file_path.relative_to(task_definitions_root)
            source_group = rel_path.parts[0] if rel_path.parts else None
        except ValueError:
            source_group = None

        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue

            tags = extract_task_tags_from_class(node)
            if not tags:
                continue

            task_meta_by_class[node.name] = TaskDefinitionMeta(
                tags=tags,
                source_group=source_group,
                split=infer_split(node.name, tags, source_group),
                difficulty=infer_difficulty(tags),
            )

    return task_meta_by_class


def init_metrics() -> dict[str, dict[str, MetricStat]]:
    return {
        split: {
            "all": MetricStat(),
            "easy": MetricStat(),
            "hard": MetricStat(),
        }
        for split in SPLITS
    }


def safe_round(value: float | None) -> float | None:
    return round(value, 6) if value is not None else None


def add_result_to_stats(
    stats: dict[str, dict[str, MetricStat]],
    split: str,
    difficulty: str,
    score: float,
    is_success: bool,
) -> None:
    for bucket in ("all", difficulty):
        stats[split][bucket].add_result(
            score=score,
            is_success=is_success,
            count_score=(split == "personalized"),
        )


def add_no_result_to_stats(
    stats: dict[str, dict[str, MetricStat]],
    split: str,
    difficulty: str,
    include_no_results_as_failures: bool,
    include_no_results_as_zero_in_personalized_avg: bool,
) -> None:
    for bucket in ("all", difficulty):
        stats[split][bucket].add_no_result(
            count_failure=include_no_results_as_failures,
            count_zero_score=(split == "personalized" and include_no_results_as_zero_in_personalized_avg),
        )


def build_metrics(
    results: list[TaskResult],
    no_results: list[str],
    task_meta_by_class: dict[str, TaskDefinitionMeta],
    include_no_results_as_failures: bool,
    include_no_results_as_zero_in_personalized_avg: bool,
) -> tuple[dict[str, dict[str, MetricStat]], list[str], list[str]]:
    stats = init_metrics()
    unmatched_split_tasks: list[str] = []
    missing_difficulty_tasks: list[str] = []

    for result in results:
        meta = task_meta_by_class.get(result.base_task_name)
        split = infer_split(result.base_task_name, meta.tags, meta.source_group) if meta else infer_split(
            result.base_task_name,
            set(),
            None,
        )
        difficulty = meta.difficulty if meta else None

        if split is None:
            unmatched_split_tasks.append(result.task_name)
            continue
        if difficulty is None:
            missing_difficulty_tasks.append(result.task_name)
            continue

        add_result_to_stats(stats, split, difficulty, result.score, result.is_success)

    for task_name in no_results:
        base_task_name = task_name.split("@", 1)[0]
        meta = task_meta_by_class.get(base_task_name)
        split = infer_split(base_task_name, meta.tags, meta.source_group) if meta else infer_split(
            base_task_name,
            set(),
            None,
        )
        difficulty = meta.difficulty if meta else None

        if split is None:
            unmatched_split_tasks.append(task_name)
            continue
        if difficulty is None:
            missing_difficulty_tasks.append(task_name)
            continue

        add_no_result_to_stats(
            stats=stats,
            split=split,
            difficulty=difficulty,
            include_no_results_as_failures=include_no_results_as_failures,
            include_no_results_as_zero_in_personalized_avg=include_no_results_as_zero_in_personalized_avg,
        )

    return stats, unmatched_split_tasks, missing_difficulty_tasks


def summarize_metrics(stats: dict[str, dict[str, MetricStat]]) -> dict[str, dict[str, dict[str, Any]]]:
    summary: dict[str, dict[str, dict[str, Any]]] = {}

    for split in SPLITS:
        summary[split] = {}
        for difficulty in ("all", *DIFFICULTIES):
            stat = stats[split][difficulty]
            summary[split][difficulty] = {
                "success": stat.success,
                "total": stat.total,
                "tasks_with_results": stat.tasks_with_results,
                "tasks_with_no_results": stat.tasks_with_no_results,
                "success_rate": safe_round(stat.success_rate),
                "average_score": safe_round(stat.average_score) if split == "personalized" else None,
                "score_denominator": stat.score_denominator if split == "personalized" else None,
            }

    return summary


def format_percentage(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2%}"


def format_score(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.4f}"


def format_text_output(output: dict[str, Any]) -> str:
    lines = [
        f"log_root: {output['log_root']}",
        f"data_source: {output['data_source']}",
        f"success_rule: score > {output['success_threshold']}",
        (
            "no_result_policy: "
            f"sr={'counted_as_failure' if output['policies']['include_no_results_as_failures'] else 'excluded'}; "
            f"personalized_avg={'counted_as_zero' if output['policies']['include_no_results_as_zero_in_personalized_avg'] else 'excluded'}"
        ),
        f"tasks_with_results: {output['totals']['tasks_with_results']}",
        f"tasks_with_no_results: {output['totals']['tasks_with_no_results']}",
        f"unmatched_split_tasks: {output['totals']['unmatched_split_tasks']}",
        f"missing_difficulty_tasks: {output['totals']['missing_difficulty_tasks']}",
        "",
        f"{'split':<14}{'difficulty':<12}{'success/total':<16}{'SR':<12}{'AvgScore':<12}",
        "-" * 66,
    ]

    for split in SPLITS:
        for difficulty in ("all", *DIFFICULTIES):
            item = output["metrics"][split][difficulty]
            success_total = f"{item['success']}/{item['total']}"
            lines.append(
                f"{split:<14}{difficulty:<12}{success_total:<16}"
                f"{format_percentage(item['success_rate']):<12}"
                f"{format_score(item['average_score']):<12}"
            )

    if output["unmatched_split_tasks"]:
        preview = ", ".join(output["unmatched_split_tasks"][:10])
        lines.extend(["", f"unmatched_split_preview: {preview}"])

    if output["missing_difficulty_tasks"]:
        preview = ", ".join(output["missing_difficulty_tasks"][:10])
        lines.extend(["", f"missing_difficulty_preview: {preview}"])

    lines.extend(
        [
            "",
            "notes:",
            "- split is inferred from task_tags first, then from the task definition folder name as fallback.",
            "- difficulty is inferred only from task_tags: easy or hard.",
            "- AvgScore is only meaningful for personalized tasks, so general/proactive rows are shown as n/a.",
        ]
    )
    return "\n".join(lines)


def build_output(
    log_root: Path,
    data_source: str,
    results: list[TaskResult],
    no_results: list[str],
    metrics: dict[str, dict[str, MetricStat]],
    unmatched_split_tasks: list[str],
    missing_difficulty_tasks: list[str],
    include_no_results_as_failures: bool,
    include_no_results_as_zero_in_personalized_avg: bool,
) -> dict[str, Any]:
    return {
        "log_root": str(log_root),
        "data_source": data_source,
        "success_threshold": SUCCESS_THRESHOLD,
        "policies": {
            "include_no_results_as_failures": include_no_results_as_failures,
            "include_no_results_as_zero_in_personalized_avg": (
                include_no_results_as_zero_in_personalized_avg
            ),
        },
        "totals": {
            "tasks_with_results": len(results),
            "tasks_with_no_results": len(no_results),
            "unmatched_split_tasks": len(unmatched_split_tasks),
            "missing_difficulty_tasks": len(missing_difficulty_tasks),
        },
        "metrics": summarize_metrics(metrics),
        "unmatched_split_tasks": unmatched_split_tasks,
        "missing_difficulty_tasks": missing_difficulty_tasks,
    }


def main() -> None:
    args = parse_args()
    log_root = args.log_root.resolve()
    task_definitions_root = args.task_definitions_root.resolve()

    if not log_root.exists():
        raise SystemExit(f"log_root does not exist: {log_root}")
    if not task_definitions_root.exists():
        raise SystemExit(f"task_definitions_root does not exist: {task_definitions_root}")

    report_path = args.report.resolve() if args.report else find_latest_eval_report(log_root)
    if args.report and report_path is not None and not report_path.exists():
        raise SystemExit(f"report does not exist: {report_path}")

    results, no_results, data_source = load_results(
        log_root=log_root,
        source=args.source,
        report_path=report_path,
    )
    task_meta_by_class = extract_task_metadata(task_definitions_root)
    metrics, unmatched_split_tasks, missing_difficulty_tasks = build_metrics(
        results=results,
        no_results=no_results,
        task_meta_by_class=task_meta_by_class,
        include_no_results_as_failures=args.include_no_results_as_failures,
        include_no_results_as_zero_in_personalized_avg=args.include_no_results_as_zero_in_personalized_avg,
    )
    output = build_output(
        log_root=log_root,
        data_source=data_source,
        results=results,
        no_results=no_results,
        metrics=metrics,
        unmatched_split_tasks=sorted(set(unmatched_split_tasks)),
        missing_difficulty_tasks=sorted(set(missing_difficulty_tasks)),
        include_no_results_as_failures=args.include_no_results_as_failures,
        include_no_results_as_zero_in_personalized_avg=(
            args.include_no_results_as_zero_in_personalized_avg
        ),
    )

    if args.json:
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        print(format_text_output(output))


if __name__ == "__main__":
    main()

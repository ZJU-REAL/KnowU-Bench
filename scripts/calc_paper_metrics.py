#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


SUCCESS_THRESHOLD = 0.99
DECISION_RE = re.compile(r"<decision>\s*(accept|reject)\s*</decision>", re.IGNORECASE | re.DOTALL)
GENERIC_TERMINAL_ANSWERS = {
    "",
    "task finished",
    "task failed",
    "finished",
    "failed",
    "success",
}
NON_ENGAGEMENT_ACTIONS = {
    "wait",
    "finished",
    "ask_user",
}
STOP_ALLOWED_ACTIONS = NON_ENGAGEMENT_ACTIONS | {
    "answer",
}
ROUTINE_HABIT_KEY_MAP = {
    "BatterySaverRoutineTask": ("low_battery_saver",),
    "BirthdayWishTask": ("birthday_wish_routine",),
    "BluetoothMediaCleanupTask": ("bluetooth_cleanup",),
    "ClockOutRoutineTask": ("clock_out_routine",),
    "ContactSaverTask": ("contact_saver",),
    "DailyFamilyCallTask": ("daily_family_call",),
    "DeepWorkRoutineTask": ("deep_work_block",),
    "GalleryCleanupTask": ("gallery_cleanup",),
    "MattermostOnCallTask": ("on_call_response",),
    "MorningPaperReadingTask": ("morning_routine",),
    "MorningWeatherCheckTask": ("morning_weather",),
    "NightEyeCareRoutineTask": ("night_eye_care",),
    "PreMeetingPrepTask": ("pre_meeting_prep",),
    "ScamSmsInterceptRoutineTask": ("scam_sms_intercept", "fraud_sms_block", "sms_scam_guard", "anti_scam_sms"),
    "WeeklyReportRoutineTask": ("weekly_report",),
    "WeekendSleeperTask": ("weekend_sleeper", "weekend_alarm"),
}
PROFILE_HABITS_CACHE: dict[Path, dict[str, Any]] = {}


@dataclass
class TaskDefinitionMeta:
    tags: set[str]
    source_group: str | None


@dataclass
class EpisodeRecord:
    task_name: str
    base_task_name: str
    profile_id: str | None
    split: str
    score: float
    reason: str
    success: bool
    steps: int
    queries: int
    user_decision: str | None
    proactive_bucket: str | None
    proactive_policy_success: bool | None
    tags: list[str]


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[1]
    default_task_defs = repo_root / "src" / "mobile_world" / "tasks" / "definitions"

    parser = argparse.ArgumentParser(
        description=(
            "Compute paper metrics from a MobileWorld result directory. "
            "The script reads per-episode result.txt and traj.json files."
        )
    )
    parser.add_argument(
        "log_root",
        type=Path,
        help="Path to a MobileWorld run directory under traj_logs/.",
    )
    parser.add_argument(
        "--task-definitions-root",
        type=Path,
        default=default_task_defs,
        help="Path to src/mobile_world/tasks/definitions.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON instead of a text table.",
    )
    return parser.parse_args()


def parse_result_file(result_path: Path) -> tuple[float | None, str]:
    text = result_path.read_text(encoding="utf-8", errors="replace")
    score_match = re.search(r"^score:\s*([-+]?\d*\.?\d+)\s*$", text, re.IGNORECASE | re.MULTILINE)
    if score_match is None:
        return None, ""

    reason_match = re.search(r"^reason:\s*(.*)$", text, re.IGNORECASE | re.DOTALL | re.MULTILINE)
    reason = reason_match.group(1).strip() if reason_match else ""
    return float(score_match.group(1)), reason


def normalize_answer_text(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip()).lower()


def is_substantive_answer(action: dict[str, Any]) -> bool:
    if (action.get("action_type") or "").lower() != "answer":
        return False
    return normalize_answer_text(action.get("text")) not in GENERIC_TERMINAL_ANSWERS


def is_engagement_action(action: dict[str, Any]) -> bool:
    action_type = (action.get("action_type") or "").lower()
    if not action_type:
        return False
    if action_type == "answer":
        return is_substantive_answer(action)
    return action_type not in NON_ENGAGEMENT_ACTIONS


def is_stop_violation_action(action: dict[str, Any]) -> bool:
    action_type = (action.get("action_type") or "").lower()
    if not action_type:
        return False
    if action_type in STOP_ALLOWED_ACTIONS:
        return False
    return True


def load_traj_metrics(
    traj_path: Path,
) -> tuple[int, int, str | None, list[dict[str, Any]], int | None, int | None]:
    if not traj_path.exists():
        return 0, 0, None, [], None, None

    data = json.loads(traj_path.read_text(encoding="utf-8"))
    task_zero = data.get("0", {})
    traj = task_zero.get("traj", []) if isinstance(task_zero, dict) else []

    steps = len(traj)
    queries = 0
    decisions: list[str] = []
    first_reject_step: int | None = None
    last_query_step: int | None = None

    for idx, item in enumerate(traj, start=1):
        action = item.get("action") or {}
        if action.get("action_type") == "ask_user":
            queries += 1
            last_query_step = idx

        decision = parse_decision(item.get("ask_user_response"))
        if decision is not None:
            decisions.append(decision)
            if decision == "reject" and first_reject_step is None:
                first_reject_step = idx

    user_decision = decisions[-1] if decisions else None
    return steps, queries, user_decision, traj, first_reject_step, last_query_step


def parse_decision(raw_response: Any) -> str | None:
    if not raw_response:
        return None

    text = str(raw_response).strip()
    if not text:
        return None

    match = DECISION_RE.search(text)
    if match:
        return match.group(1).lower()

    lowered = text.lower()
    if "reject" in lowered:
        return "reject"
    if "accept" in lowered:
        return "accept"
    return None


def load_profile_habits(profile_path: Path) -> dict[str, Any]:
    if profile_path in PROFILE_HABITS_CACHE:
        return PROFILE_HABITS_CACHE[profile_path]

    if not profile_path.exists():
        PROFILE_HABITS_CACHE[profile_path] = {}
        return PROFILE_HABITS_CACHE[profile_path]

    data = yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}
    habits = ((data.get("user_profile") or {}).get("habits") or {}) if isinstance(data, dict) else {}
    PROFILE_HABITS_CACHE[profile_path] = habits if isinstance(habits, dict) else {}
    return PROFILE_HABITS_CACHE[profile_path]


def infer_habit_should_act(
    base_task_name: str,
    profile_id: str | None,
    user_profile_root: Path,
) -> bool | None:
    habit_keys = ROUTINE_HABIT_KEY_MAP.get(base_task_name)
    if not habit_keys:
        return None

    effective_profile_id = profile_id or "user"
    habits = load_profile_habits(user_profile_root / f"{effective_profile_id}.yaml")
    return any(isinstance(habits.get(key), dict) and bool(habits.get(key)) for key in habit_keys)


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

            tags: set[str] = set()
            for item in node.body:
                if not isinstance(item, ast.Assign):
                    continue
                for target in item.targets:
                    if not isinstance(target, ast.Name) or target.id != "task_tags":
                        continue
                    try:
                        value = ast.literal_eval(item.value)
                    except (ValueError, SyntaxError):
                        continue
                    if isinstance(value, (set, list, tuple)):
                        tags = {str(tag) for tag in value}

            if tags:
                task_meta_by_class[node.name] = TaskDefinitionMeta(
                    tags=tags,
                    source_group=source_group,
                )

    return task_meta_by_class


def infer_split(base_task_name: str, meta: TaskDefinitionMeta | None) -> str | None:
    tags = meta.tags if meta is not None else set()
    source_group = meta.source_group if meta is not None else None

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


def infer_proactive_bucket(user_decision: str | None, habit_should_act: bool | None) -> str | None:
    if user_decision == "reject":
        return "reject"
    if habit_should_act is True:
        return "need"
    if habit_should_act is False:
        return "noneed"
    return None


def compute_proactive_policy_success(
    proactive_bucket: str | None,
    traj: list[dict[str, Any]],
    first_reject_step: int | None,
    last_query_step: int | None,
    success: bool = False,
) -> bool | None:
    if proactive_bucket is None:
        return None

    actions = [item.get("action") or {} for item in traj]

    if proactive_bucket == "need":
        return success

    if proactive_bucket == "noneed":
        return not any(is_engagement_action(action) for action in actions)

    if proactive_bucket == "reject":
        start_idx = first_reject_step
        if start_idx is None and last_query_step is not None:
            start_idx = last_query_step + 1
        post_reject_actions = actions[start_idx - 1 :] if start_idx is not None else []
        return not any(is_stop_violation_action(action) for action in post_reject_actions)

    return None


def mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def safe_round(value: float | None) -> float | None:
    return round(value, 6) if value is not None else None


def summarize_split(records: list[EpisodeRecord], split: str) -> dict[str, Any]:
    split_records = [record for record in records if record.split == split]
    scores = [record.score for record in split_records]
    successes = [1.0 if record.success else 0.0 for record in split_records]
    steps = [float(record.steps) for record in split_records]
    queries = [float(record.queries) for record in split_records]

    summary = {
        "episodes": len(split_records),
        "success_rate": safe_round(mean(successes)),
        "ave_steps": safe_round(mean(steps)),
        "ave_queries": safe_round(mean(queries)),
    }

    if split == "personalized":
        summary["average_score"] = safe_round(mean(scores))
        summary["interaction_efficiency"] = safe_round(
            mean([record.score / max(record.queries, 1) for record in split_records])
        )
    elif split == "proactive":
        summary["interaction_efficiency"] = safe_round(
            mean([record.score / max(record.queries, 1) for record in split_records])
        )

    return summary


def summarize_proactive_policy(records: list[EpisodeRecord]) -> dict[str, Any]:
    proactive_records = [record for record in records if record.split == "proactive"]
    buckets = {
        "Act": [record for record in proactive_records if record.proactive_bucket == "need"],
        "Silent": [record for record in proactive_records if record.proactive_bucket == "noneed"],
        "Stop": [record for record in proactive_records if record.proactive_bucket == "reject"],
    }

    summary: dict[str, Any] = {}
    for metric_name, bucket_records in buckets.items():
        valid_records = [record for record in bucket_records if record.proactive_policy_success is not None]
        summary[metric_name] = {
            "episodes": len(valid_records),
            "value": safe_round(
                mean([1.0 if record.proactive_policy_success else 0.0 for record in valid_records])
            ),
        }
    return summary


def load_episode_records(
    log_root: Path,
    task_meta_by_class: dict[str, TaskDefinitionMeta],
    user_profile_root: Path,
) -> tuple[list[EpisodeRecord], list[str], list[str]]:
    records: list[EpisodeRecord] = []
    missing_results: list[str] = []
    unmatched_tasks: list[str] = []

    for task_dir in sorted(p for p in log_root.iterdir() if p.is_dir() and "_backup_" not in p.name):
        task_name = task_dir.name
        base_task_name, profile_id = split_task_name(task_name)

        result_path = task_dir / "result.txt"
        if not result_path.exists():
            missing_results.append(task_name)
            continue

        score, reason = parse_result_file(result_path)
        if score is None:
            missing_results.append(task_name)
            continue

        meta = task_meta_by_class.get(base_task_name)
        split = infer_split(base_task_name, meta)
        if split is None:
            unmatched_tasks.append(task_name)
            continue

        task_success = score > SUCCESS_THRESHOLD

        steps, queries, user_decision, traj, first_reject_step, last_query_step = load_traj_metrics(
            task_dir / "traj.json"
        )
        proactive_bucket = None
        proactive_policy_success = None
        if split == "proactive":
            habit_should_act = infer_habit_should_act(base_task_name, profile_id, user_profile_root)
            proactive_bucket = infer_proactive_bucket(user_decision, habit_should_act)
            proactive_policy_success = compute_proactive_policy_success(
                proactive_bucket=proactive_bucket,
                traj=traj,
                first_reject_step=first_reject_step,
                last_query_step=last_query_step,
                success=task_success,
            )

        records.append(
            EpisodeRecord(
                task_name=task_name,
                base_task_name=base_task_name,
                profile_id=profile_id,
                split=split,
                score=score,
                reason=reason,
                success=task_success,
                steps=steps,
                queries=queries,
                user_decision=user_decision,
                proactive_bucket=proactive_bucket,
                proactive_policy_success=proactive_policy_success,
                tags=sorted(meta.tags) if meta is not None else [],
            )
        )

    return records, missing_results, unmatched_tasks


def split_task_name(task_name: str) -> tuple[str, str | None]:
    if "@" not in task_name:
        return task_name, None
    base_task_name, profile_id = task_name.split("@", 1)
    return base_task_name, profile_id


def build_output(
    log_root: Path,
    records: list[EpisodeRecord],
    missing_results: list[str],
    unmatched_tasks: list[str],
) -> dict[str, Any]:
    splits = {
        "general": summarize_split(records, "general"),
        "personalized": summarize_split(records, "personalized"),
        "proactive": summarize_split(records, "proactive"),
    }
    proactive_policy = summarize_proactive_policy(records)

    return {
        "log_root": str(log_root),
        "success_threshold": SUCCESS_THRESHOLD,
        "totals": {
            "episodes_with_results": len(records),
            "episodes_missing_results": len(missing_results),
            "unmatched_tasks": len(unmatched_tasks),
        },
        "splits": splits,
        "proactive_policy": proactive_policy,
        "notes": [
            "AveSteps counts logged trajectory entries in traj.json.",
            "AveQueries counts actions whose action_type is ask_user.",
            "Act/Silent/Stop buckets are inferred per proactive episode from traj + persona habits: reject comes from ask_user_response; need/noneed comes from whether the corresponding habit exists in the user profile.",
            "Act measures task completion accuracy (score > threshold) for episodes where the model should act; Silent checks whether the model stayed fully quiet; Stop checks whether it avoided further operational actions after rejection.",
        ],
        "missing_results": missing_results,
        "unmatched_tasks": unmatched_tasks,
    }


def format_metric(value: float | None, percentage: bool = False) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2%}" if percentage else f"{value:.4f}"


def format_text_output(output: dict[str, Any]) -> str:
    lines = [
        f"log_root: {output['log_root']}",
        f"success_rule: score > {output['success_threshold']}",
        f"episodes_with_results: {output['totals']['episodes_with_results']}",
        f"episodes_missing_results: {output['totals']['episodes_missing_results']}",
        f"unmatched_tasks: {output['totals']['unmatched_tasks']}",
        "",
        f"{'split':<14}{'episodes':<10}{'SR':<12}{'AvgScore':<12}{'AveSteps':<12}{'AveQueries':<12}{'IE':<12}",
        "-" * 84,
    ]

    split_labels = [
        ("general", "general"),
        ("personalized", "personalized"),
        ("proactive", "proactive"),
    ]
    for key, label in split_labels:
        summary = output["splits"][key]
        lines.append(
            f"{label:<14}"
            f"{summary['episodes']:<10}"
            f"{format_metric(summary.get('success_rate'), percentage=True):<12}"
            f"{format_metric(summary.get('average_score')):<12}"
            f"{format_metric(summary.get('ave_steps')):<12}"
            f"{format_metric(summary.get('ave_queries')):<12}"
            f"{format_metric(summary.get('interaction_efficiency')):<12}"
        )

    lines.extend(
        [
            "",
            f"{'policy_metric':<14}{'episodes':<10}{'value':<12}",
            "-" * 36,
        ]
    )
    for metric_name in ("Act", "Silent", "Stop"):
        summary = output["proactive_policy"][metric_name]
        lines.append(
            f"{metric_name:<14}{summary['episodes']:<10}{format_metric(summary.get('value'), percentage=True):<12}"
        )

    if output["missing_results"]:
        preview = ", ".join(output["missing_results"][:10])
        lines.extend(["", f"missing_results_preview: {preview}"])

    if output["unmatched_tasks"]:
        preview = ", ".join(output["unmatched_tasks"][:10])
        lines.extend(["", f"unmatched_tasks_preview: {preview}"])

    lines.extend(["", "notes:"])
    lines.extend([f"- {note}" for note in output["notes"]])
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    log_root = args.log_root.resolve()
    task_definitions_root = args.task_definitions_root.resolve()
    user_profile_root = task_definitions_root.parent.parent / "user_profile"

    if not log_root.exists():
        raise SystemExit(f"log_root does not exist: {log_root}")
    if not task_definitions_root.exists():
        raise SystemExit(f"task_definitions_root does not exist: {task_definitions_root}")
    if not user_profile_root.exists():
        raise SystemExit(f"user_profile_root does not exist: {user_profile_root}")

    task_meta_by_class = extract_task_metadata(task_definitions_root)
    records, missing_results, unmatched_tasks = load_episode_records(
        log_root,
        task_meta_by_class,
        user_profile_root,
    )
    output = build_output(log_root, records, missing_results, unmatched_tasks)

    if args.json:
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print(format_text_output(output))


if __name__ == "__main__":
    main()

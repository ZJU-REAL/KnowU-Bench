#!/usr/bin/env python3
"""Precompute embeddings for preference/routine task content."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

UTILS_ROOT = Path(__file__).resolve().parent
SRC_ROOT = UTILS_ROOT.parents[2]
PROJECT_ROOT = SRC_ROOT.parent
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

DEFAULT_TAGS = ("preference", "routine")
DEFAULT_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
DEFAULT_OUTPUT_DIR = SRC_ROOT / "knowu_bench" / "cache" / "embeddings" / "task_content"


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", text.strip())
    return slug.strip("_").lower()


def _normalize_text(text: str) -> str:
    text = (text or "").replace("\r\n", "\n").strip()
    lines = [line.rstrip() for line in text.splitlines()]
    return "\n".join(lines).strip()


def _task_family(task: Any) -> str | None:
    tags = {str(tag).strip().lower() for tag in getattr(task, "task_tags", set())}
    if "preference" in tags:
        return "preference"
    if "routine" in tags:
        return "routine"
    if "general" in tags:
        return "general"
    return None


def _extract_preference_text(task: Any, goal_text: str) -> str:
    goal_request = _normalize_text(str(getattr(task, "GOAL_REQUEST", "") or ""))
    if goal_request:
        return goal_request

    marker = "### USER INSTRUCTION"
    if marker in goal_text:
        return _normalize_text(goal_text.split(marker, 1)[1])
    return goal_text


def _extract_routine_text(goal_text: str) -> str:
    marker = "### INSTRUCTION"
    if marker not in goal_text:
        return goal_text

    prefix, instruction = goal_text.split(marker, 1)
    instruction = _normalize_text(instruction)

    system_start = prefix.rfind("System Status:")
    if system_start == -1:
        return instruction

    system_context = _normalize_text(prefix[system_start:])
    return _normalize_text(f"{system_context}\n\n{marker}\n{instruction}")


def _extract_task_text(task: Any, text_mode: str) -> str:
    goal_text = _normalize_text(str(getattr(task, "goal", "") or ""))
    family = _task_family(task)

    if text_mode == "goal":
        return goal_text

    if family == "preference":
        return _extract_preference_text(task, goal_text)
    if family == "routine":
        return _extract_routine_text(goal_text)
    return goal_text


def collect_task_payloads(include_tags: set[str], text_mode: str) -> list[dict[str, Any]]:
    from knowu_bench.tasks.registry import TaskRegistry

    registry = TaskRegistry()
    payloads: list[dict[str, Any]] = []

    for task_name in sorted(registry.list_tasks()):
        task = registry.get_task(task_name)
        family = _task_family(task)
        if family is None or family not in include_tags:
            continue

        text_for_embedding = _extract_task_text(task, text_mode=text_mode)
        if not text_for_embedding:
            continue

        params = getattr(task, "_params", {}) or {}
        payloads.append(
            {
                "task_name": task.name,
                "class_name": task.__class__.__name__,
                "family": family,
                "profile_id": params.get("profile_id"),
                "profile_path": params.get("profile_path"),
                "task_tags": sorted(str(tag) for tag in getattr(task, "task_tags", set())),
                "text_mode": text_mode,
                "text_for_embedding": text_for_embedding,
            }
        )

    return payloads


def write_jsonl(path: Path, items: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def _build_task_records(payloads: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for payload in payloads:
        task_name = payload["task_name"]
        records[task_name] = {
            "task_name": task_name,
            "class_name": payload["class_name"],
            "family": payload["family"],
            "task_tags": payload["task_tags"],
            "text_mode": payload["text_mode"],
            "text_for_embedding": payload["text_for_embedding"],
            "profile_id": payload.get("profile_id"),
            "profile_path": payload.get("profile_path"),
        }
    return records


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Precompute embeddings for preference/routine task content."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Output directory (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--model-name",
        default=DEFAULT_MODEL_NAME,
        help="SentenceTransformer model name.",
    )
    parser.add_argument(
        "--text-mode",
        choices=["content", "goal"],
        default="content",
        help="`content` strips user-log context; `goal` embeds the full rendered goal.",
    )
    parser.add_argument(
        "--include-tags",
        default=",".join(DEFAULT_TAGS),
        help="Comma-separated task families to include (default: preference,routine).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=64,
        help="Batch size for SentenceTransformer.encode().",
    )
    return parser.parse_args()


def main() -> None:
    import numpy as np

    args = parse_args()
    include_tags = {
        tag.strip().lower() for tag in str(args.include_tags).split(",") if tag.strip()
    }
    payloads = collect_task_payloads(include_tags=include_tags, text_mode=args.text_mode)
    if not payloads:
        raise SystemExit("No matching tasks found.")

    task_records = _build_task_records(payloads)
    all_records = [task_records[task_name] for task_name in sorted(task_records)]
    texts = [record["text_for_embedding"] for record in all_records]

    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(args.model_name)
    embeddings = model.encode(
        texts,
        normalize_embeddings=True,
        batch_size=args.batch_size,
        show_progress_bar=True,
    )

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    model_slug = _slugify(args.model_name)
    prefix = f"task_content_{args.text_mode}_{model_slug}"
    task_dir = output_dir / f"{prefix}_by_task_name"
    task_dir.mkdir(parents=True, exist_ok=True)

    manifest_tasks: list[dict[str, Any]] = []
    for index, record in enumerate(all_records):
        task_name = record["task_name"]
        task_embedding = np.asarray(embeddings[index : index + 1])
        embedding_path = task_dir / f"{task_name}.embedding.npy"
        metadata_path = task_dir / f"{task_name}.metadata.json"

        np.save(embedding_path, task_embedding)
        with metadata_path.open("w", encoding="utf-8") as f:
            json.dump(
                {
                    "task_name": task_name,
                    "class_name": record["class_name"],
                    "model_name": args.model_name,
                    "text_mode": args.text_mode,
                    "family": record["family"],
                    "embedding_shape": list(task_embedding.shape),
                    "record": record,
                },
                f,
                ensure_ascii=False,
                indent=2,
            )

        manifest_tasks.append(
            {
                "task_name": task_name,
                "class_name": record["class_name"],
                "embedding_path": str(embedding_path),
                "metadata_path": str(metadata_path),
            }
        )

    texts_path = output_dir / f"{prefix}.jsonl"
    manifest_path = output_dir / f"{prefix}.manifest.json"
    write_jsonl(texts_path, all_records)

    manifest = {
        "model_name": args.model_name,
        "text_mode": args.text_mode,
        "families": sorted(include_tags),
        "variant_count": len(payloads),
        "task_count": len(task_records),
        "embedding_shape": list(np.asarray(embeddings).shape),
        "task_dir": str(task_dir),
        "texts_path": str(texts_path),
        "tasks": manifest_tasks,
    }
    with manifest_path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"Saved embeddings for {len(task_records)} task names.")
    print(f"Source variants: {len(payloads)}")
    print(f"Task embeddings directory: {task_dir}")
    print(f"Texts: {texts_path}")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()

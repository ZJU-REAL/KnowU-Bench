"""
Build a user-log context string for GUI agents.

Usage:
  python src/knowu_bench/runtime/utils/user_log_context.py src/knowu_bench/user_logs/user.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime
from typing import Any


TIME_FORMAT = "%Y-%m-%d %H:%M"
DEFAULT_OUTPUT_PATH = "artifacts/user_log_context.txt"
DEFAULT_LOGS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "user_logs")
)
DEFAULT_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
DEFAULT_EMBEDDINGS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "cache", "embeddings", "user_logs")
)
DEFAULT_TASK_EMBEDDINGS_DIR = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "cache",
        "embeddings",
        "task_content",
        "task_content_content_paraphrase_multilingual_minilm_l12_v2_by_task_name",
    )
)

_log_config: dict[str, Any] = {
    "mode": "all",
    "top_k": 10,
    "rag_backend": "tfidf",
    "source": "clean",
}


def set_user_log_config(
    mode: str = "all",
    top_k: int = 10,
    rag_backend: str = "tfidf",
    source: str = "clean",
) -> None:
    _log_config["mode"] = mode
    _log_config["top_k"] = top_k
    _log_config["rag_backend"] = rag_backend
    _log_config["source"] = source


def get_user_log_config() -> dict[str, Any]:
    return dict(_log_config)


def load_logs(path: str) -> list[dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("Log file must be a JSON list.")
    return [entry for entry in data if isinstance(entry, dict)]


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _format_time(dt: datetime | None, fallback: str | None) -> str:
    if dt is None:
        return fallback or "Unknown time"
    return dt.strftime(TIME_FORMAT)


def _shorten_location(location: str | None, max_len: int = 80) -> str:
    if not location:
        return "Unknown location"
    parts = [p.strip() for p in location.split("|") if p.strip()]
    if not parts:
        return "Unknown location"
    if len(parts) >= 2:
        short = f"{parts[0]} / {parts[-1]}"
    else:
        short = parts[0]
    if len(short) > max_len:
        short = short[: max_len - 3] + "..."
    return short


def _truncate_text(text: str | None, max_len: int) -> str:
    if not text:
        return ""
    if max_len <= 0 or len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _resolve_profile_id(
    user_profile: dict[str, Any] | None,
    profile_path: str | None = None,
) -> str:
    if profile_path:
        profile_id = os.path.splitext(os.path.basename(profile_path))[0].strip().lower()
        if profile_id:
            return profile_id

    if user_profile:
        identity = user_profile.get("identity", {})
        if isinstance(identity, dict):
            full_name = (identity.get("full_name", "") or "").strip().lower()
            if full_name:
                return re.sub(r"[^a-z0-9]+", "_", full_name).strip("_")

    return ""


def _format_log_entry(entry: dict[str, Any]) -> str:
    dt = _parse_time(entry.get("time"))
    time_str = _format_time(dt, entry.get("time"))
    location = _shorten_location(entry.get("location"))
    action = entry.get("action", "")
    return f"- [{time_str}] ({location}) {action}"


def resolve_user_log_path(
    user_profile: dict[str, Any] | None,
    profile_path: str | None = None,
    logs_dir: str | None = None,
) -> str | None:
    logs_root = logs_dir or DEFAULT_LOGS_DIR
    profile_id = _resolve_profile_id(user_profile, profile_path=profile_path)
    if not profile_id:
        return None

    source = _log_config.get("source", "clean")
    if source == "noise":
        filename = f"{profile_id}_noise_25pct.json"
    else:
        filename = f"{profile_id}.json"

    candidate = os.path.join(logs_root, filename)
    if not os.path.exists(candidate):
        raise FileNotFoundError(
            f"User log file not found for profile '{profile_id}' and source '{source}': {candidate}"
        )
    return candidate


def build_user_log_context(
    user_profile: dict[str, Any] | None,
    profile_path: str | None = None,
    logs_dir: str | None = None,
    max_entries: int = 0,
    max_chars: int = 0,
    max_action_len: int = 0,
    query: str | None = None,
    task_name: str | None = None,
) -> str:
    from loguru import logger

    log_path = resolve_user_log_path(
        user_profile,
        profile_path=profile_path,
        logs_dir=logs_dir,
    )
    if not log_path:
        logger.debug(f"[UserLog] No log file found for profile_path={profile_path}")
        return ""

    logger.debug(f"[UserLog] Resolved log_path={log_path} | mode={_log_config['mode']} | query={query!r}")

    if _log_config["mode"] == "rag" and query:
        backend = _log_config.get("rag_backend", "tfidf")
        logger.info(f"[UserLog] Using RAG mode with top_k={_log_config['top_k']}, backend={backend}")
        if backend == "embedding":
            return UserLogRAGBuilder(
                log_path,
                query=query,
                top_k=_log_config["top_k"],
                task_name=task_name,
            ).build()
        return UserLogTfidfRAGBuilder(
            log_path,
            query=query,
            top_k=_log_config["top_k"],
        ).build()

    logger.info(f"[UserLog] Using ALL mode (full log context)")
    return UserLogContextBuilder(
        log_path,
        max_entries=max_entries,
        max_chars=max_chars,
        max_action_len=max_action_len,
    ).build()


def _sort_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    parsed = [(_parse_time(e.get("time")), i, e) for i, e in enumerate(entries)]
    if all(p is not None for p, _, _ in parsed):
        parsed.sort(key=lambda item: item[0])
        return [e for _, _, e in parsed]
    return entries


class UserLogContextBuilder:
    def __init__(
        self,
        log_path: str,
        max_entries: int = 0,
        max_chars: int = 0,
        max_action_len: int = 0,
    ) -> None:
        self.log_path = log_path
        self.max_entries = max_entries
        self.max_chars = max_chars
        self.max_action_len = max_action_len

    def build(self) -> str:
        entries = _sort_entries(load_logs(self.log_path))
        if not entries:
            return ""

        if self.max_entries and self.max_entries > 0:
            max_entries = min(self.max_entries, len(entries))
            recent_entries = entries[-max_entries:]
        else:
            recent_entries = entries

        lines: list[str] = []
        for entry in recent_entries:
            dt = _parse_time(entry.get("time"))
            time_str = _format_time(dt, entry.get("time"))
            location = _shorten_location(entry.get("location"))
            action = _truncate_text(entry.get("action", ""), self.max_action_len)
            lines.append(f"- [{time_str}] ({location}) {action}")

        context = "\n".join(lines)

        if self.max_chars and len(context) > self.max_chars:
            while len(context) > self.max_chars and len(recent_entries) > 3:
                recent_entries = recent_entries[1:]
                lines = []
                for entry in recent_entries:
                    dt = _parse_time(entry.get("time"))
                    time_str = _format_time(dt, entry.get("time"))
                    location = _shorten_location(entry.get("location"))
                    action = _truncate_text(entry.get("action", ""), self.max_action_len)
                    lines.append(f"- [{time_str}] ({location}) {action}")
                context = "\n".join(lines)

            if len(context) > self.max_chars:
                context = context[: self.max_chars - 3] + "..."

        return context


class UserLogTfidfRAGBuilder:
    """Select top-k log entries most relevant to a query via TF-IDF cosine similarity."""

    def __init__(self, log_path: str, query: str, top_k: int = 10) -> None:
        self.log_path = log_path
        self.query = query
        self.top_k = top_k

    def _format_entry(self, entry: dict[str, Any]) -> str:
        return _format_log_entry(entry)

    @staticmethod
    def _tokenize(text: str) -> str:
        """Insert spaces between CJK characters so TfidfVectorizer can split them."""
        return re.sub(r"([\u4e00-\u9fff])", r" \1 ", text)

    def build(self) -> str:
        import numpy as np
        from loguru import logger
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity

        logger.debug(
            f"[TF-IDF RAG] Starting retrieval | query={self.query!r} "
            f"| top_k={self.top_k} | log_path={self.log_path}"
        )

        entries = _sort_entries(load_logs(self.log_path))
        if not entries:
            logger.warning("[TF-IDF RAG] No log entries found, returning empty context")
            return ""

        logger.debug(f"[TF-IDF RAG] Total log entries loaded: {len(entries)}")

        if len(entries) <= self.top_k:
            logger.debug(
                f"[TF-IDF RAG] Entries ({len(entries)}) <= top_k ({self.top_k}), "
                "returning ALL entries without filtering"
            )
            return "\n".join(self._format_entry(e) for e in entries)

        actions = [e.get("action", "") for e in entries]
        tokenized = [self._tokenize(a) for a in actions]
        tokenized_query = self._tokenize(self.query)

        vectorizer = TfidfVectorizer(
            analyzer="word",
            token_pattern=r"(?u)\b\w+\b",
            ngram_range=(1, 2),
        )
        tfidf_matrix = vectorizer.fit_transform(tokenized + [tokenized_query])

        query_vec = tfidf_matrix[-1]
        action_vecs = tfidf_matrix[:-1]

        similarities = cosine_similarity(action_vecs, query_vec).flatten()
        top_indices = sorted(np.argsort(similarities)[-self.top_k :])

        logger.debug(
            f"[TF-IDF RAG] Similarity stats: min={similarities.min():.4f}, "
            f"max={similarities.max():.4f}, mean={similarities.mean():.4f}"
        )
        logger.debug(
            f"[TF-IDF RAG] Selected top-{self.top_k} indices (sorted by time): "
            f"{list(top_indices)}"
        )
        for rank, idx in enumerate(sorted(top_indices, key=lambda i: -similarities[i])):
            logger.debug(
                f"[TF-IDF RAG]   #{rank + 1} idx={idx} sim={similarities[idx]:.4f} "
                f"action={actions[idx][:120]!r}"
            )

        result = "\n".join(self._format_entry(entries[i]) for i in top_indices)
        logger.debug(
            f"[TF-IDF RAG] Final context length: {len(result)} chars, "
            f"{self.top_k} entries selected out of {len(entries)}"
        )
        return result


class UserLogRAGBuilder:
    """Select top-k log entries most relevant to a query via embedding similarity."""

    _model = None
    DEFAULT_MODEL_NAME = DEFAULT_MODEL_NAME

    def __init__(self, log_path: str, query: str, top_k: int = 10, task_name: str | None = None) -> None:
        self.log_path = log_path
        self.query = query
        self.top_k = top_k
        self.task_name = task_name

    @classmethod
    def _get_model(cls):
        if cls._model is None:
            from sentence_transformers import SentenceTransformer

            cls._model = SentenceTransformer(cls.DEFAULT_MODEL_NAME)
        return cls._model

    def _format_entry(self, entry: dict[str, Any]) -> str:
        return _format_log_entry(entry)

    def _cache_path(self) -> str:
        os.makedirs(DEFAULT_EMBEDDINGS_DIR, exist_ok=True)
        stem = os.path.splitext(os.path.basename(self.log_path))[0]
        return os.path.join(DEFAULT_EMBEDDINGS_DIR, f"{stem}.embeddings.npy")

    def _load_or_compute_embeddings(self, actions: list[str]):
        import numpy as np
        from loguru import logger

        cache_path = self._cache_path()
        should_recompute = True

        if os.path.exists(cache_path):
            if os.path.getmtime(cache_path) >= os.path.getmtime(self.log_path):
                try:
                    embeddings = np.load(cache_path)
                    embeddings = np.asarray(embeddings)
                    if embeddings.ndim != 2:
                        logger.warning(
                            f"[RAG] Invalid cache ndim for {cache_path}: "
                            f"expected 2, got {embeddings.ndim}; recomputing"
                        )
                    elif embeddings.shape[0] != len(actions):
                        logger.warning(
                            f"[RAG] Invalid cache row count for {cache_path}: "
                            f"expected {len(actions)}, got {embeddings.shape[0]}; recomputing"
                        )
                    else:
                        logger.info(f"[RAG] Cache hit for log embeddings: {cache_path}")
                        should_recompute = False
                        return embeddings
                except Exception as exc:
                    logger.warning(
                        f"[RAG] Failed loading cache {cache_path}: {exc}; recomputing"
                    )
            else:
                logger.info(
                    f"[RAG] Cache stale for log embeddings: {cache_path}; recomputing"
                )
        else:
            logger.info(f"[RAG] Cache miss for log embeddings: {cache_path}; recomputing")

        assert should_recompute
        model = self._get_model()
        embeddings = model.encode(actions, normalize_embeddings=True)
        np.save(cache_path, embeddings)
        logger.info(
            f"[RAG] Wrote log embeddings cache: {cache_path} "
            f"(entries={len(actions)}, dim={embeddings.shape[1] if embeddings.ndim == 2 else 'unknown'})"
        )
        return embeddings

    def _task_embedding_path(self) -> str | None:
        if not self.task_name:
            return None
        return os.path.join(DEFAULT_TASK_EMBEDDINGS_DIR, f"{self.task_name}.embedding.npy")

    def _load_or_compute_query_embedding(self):
        import numpy as np

        task_embedding_path = self._task_embedding_path()
        if task_embedding_path and os.path.exists(task_embedding_path):
            query_embedding = np.load(task_embedding_path)
            query_embedding = np.asarray(query_embedding)
            if query_embedding.ndim == 1:
                return query_embedding.reshape(1, -1)
            if query_embedding.ndim == 2 and query_embedding.shape[0] >= 1:
                return query_embedding[:1]

        model = self._get_model()
        return model.encode([self.query], normalize_embeddings=True)

    def build(self) -> str:
        import numpy as np
        from loguru import logger

        logger.debug(f"[RAG] Starting RAG retrieval | query={self.query!r} | top_k={self.top_k} | log_path={self.log_path}")

        entries = _sort_entries(load_logs(self.log_path))
        if not entries:
            logger.warning("[RAG] No log entries found, returning empty context")
            return ""

        logger.debug(f"[RAG] Total log entries loaded: {len(entries)}")

        if len(entries) <= self.top_k:
            logger.debug(f"[RAG] Entries ({len(entries)}) <= top_k ({self.top_k}), returning ALL entries without filtering")
            return "\n".join(self._format_entry(e) for e in entries)

        entry_texts = [self._format_entry(e) for e in entries]
        entry_embeddings = self._load_or_compute_embeddings(entry_texts)
        query_embedding = self._load_or_compute_query_embedding()

        similarities = np.dot(entry_embeddings, query_embedding.T).flatten()
        top_indices = sorted(np.argsort(similarities)[-self.top_k :])

        logger.debug(f"[RAG] Similarity stats: min={similarities.min():.4f}, max={similarities.max():.4f}, mean={similarities.mean():.4f}")
        logger.debug(f"[RAG] Selected top-{self.top_k} indices (sorted by time): {list(top_indices)}")
        for rank, idx in enumerate(sorted(top_indices, key=lambda i: -similarities[i])):
            logger.debug(
                f"[RAG]   #{rank+1} idx={idx} sim={similarities[idx]:.4f} "
                f"entry={entry_texts[idx][:120]!r}"
            )

        result = "\n".join(self._format_entry(entries[i]) for i in top_indices)
        logger.debug(f"[RAG] Final context length: {len(result)} chars, {self.top_k} entries selected out of {len(entries)}")
        return result


def precompute_log_embeddings(logs_dir: str | None = None) -> None:
    from loguru import logger

    logs_root = logs_dir or DEFAULT_LOGS_DIR
    logger.info(f"[RAG] Precomputing log embeddings in {logs_root}")
    processed = 0
    for entry in sorted(os.scandir(logs_root), key=lambda item: item.name):
        if not entry.is_file() or not entry.name.endswith(".json"):
            continue
        entries = _sort_entries(load_logs(entry.path))
        entry_texts = [_format_log_entry(log_entry) for log_entry in entries]
        if not entry_texts:
            logger.info(f"[RAG] Skipping empty log file during precompute: {entry.path}")
            continue
        logger.info(
            f"[RAG] Precomputing embeddings for log_path={entry.path} "
            f"(entries={len(entry_texts)})"
        )
        UserLogRAGBuilder(entry.path, query="", top_k=1)._load_or_compute_embeddings(entry_texts)
        processed += 1
    logger.info(f"[RAG] Precompute complete for {processed} log file(s)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build user log context for GUI agents.")
    parser.add_argument("log_path", nargs="?", help="Path to the JSON log file.")
    parser.add_argument("--max-entries", type=int, default=0, help="Max recent entries to include (0 = no limit).")
    parser.add_argument("--max-chars", type=int, default=0, help="Max characters for the context (0 = no limit).")
    parser.add_argument("--max-action-len", type=int, default=0, help="Max length per action line (0 = no limit).")
    parser.add_argument("--json", action="store_true", help="Output a JSON payload.")
    parser.add_argument("--output", default=DEFAULT_OUTPUT_PATH, help="Write the context output to a file.")
    parser.add_argument("--precompute", action="store_true", help="Precompute embeddings for all user logs.")
    args = parser.parse_args()

    if args.precompute:
        precompute_log_embeddings()
        return

    if not args.log_path:
        parser.error("log_path is required unless --precompute is specified")

    builder = UserLogContextBuilder(
        args.log_path,
        max_entries=args.max_entries,
        max_chars=args.max_chars,
        max_action_len=args.max_action_len,
    )
    context = builder.build()

    if args.json:
        payload = {
            "log_path": args.log_path,
            "context_text": context,
        }
        output_text = json.dumps(payload, ensure_ascii=False, indent=2)
    else:
        output_text = context

    output_path = args.output or DEFAULT_OUTPUT_PATH
    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(output_text)
    print(output_text)


if __name__ == "__main__":
    main()

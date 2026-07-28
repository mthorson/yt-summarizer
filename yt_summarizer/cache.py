"""Local cache of transcripts + metadata, keyed by video id.

Records are written *before* summarizing so that re-runs (e.g. with a
different prompt or model) never re-download or re-transcribe.
"""

from __future__ import annotations

import hashlib
import json
import os


def cache_path(cache_dir: str, channel: str, video_id: str) -> str:
    return os.path.join(cache_dir, channel, f"{video_id}.json")


def load(cache_dir: str, channel: str, video_id: str) -> dict | None:
    path = cache_path(cache_dir, channel, video_id)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (json.JSONDecodeError, OSError):
        return None


def find(cache_dir: str, video_id: str) -> dict | None:
    """Find a cached record by stable video ID, independent of channel renames."""
    if not video_id or not os.path.isdir(cache_dir):
        return None
    for root, _, files in os.walk(cache_dir):
        if "chunks" in os.path.relpath(root, cache_dir).split(os.path.sep):
            continue
        if f"{video_id}.json" in files:
            record = load(cache_dir, os.path.relpath(root, cache_dir), video_id)
            if record and record.get("transcript"):
                return record
    return None


def save(cache_dir: str, channel: str, record: dict) -> str:
    path = cache_path(cache_dir, channel, record["video_id"])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return path


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def chunk_result_path(cache_dir: str, video_id: str, fingerprint: str) -> str:
    return os.path.join(cache_dir, "chunks", video_id, f"{fingerprint}.json")


def load_chunk_result(
    cache_dir: str, video_id: str, fingerprint: str
) -> list[str] | None:
    path = chunk_result_path(cache_dir, video_id, fingerprint)
    try:
        with open(path, encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    chunks = value.get("chunks") if isinstance(value, dict) else None
    return (
        chunks
        if isinstance(chunks, list) and all(isinstance(x, str) for x in chunks)
        else None
    )


def save_chunk_result(
    cache_dir: str, video_id: str, fingerprint: str, chunks: list[str]
) -> str:
    path = chunk_result_path(cache_dir, video_id, fingerprint)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump({"chunks": chunks}, handle, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return path

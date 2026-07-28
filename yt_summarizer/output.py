"""Write summaries to markdown files, one per video."""

from __future__ import annotations

import json
import os
import re
import tempfile
from contextlib import suppress
from datetime import datetime, timezone

from .errors import OutputError

_WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}


def slugify(text: str, max_len: int = 60) -> str:
    text = (text or "").lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:max_len].strip("-") or "video"


def sanitize_channel(name: str) -> str:
    """Turn a channel name into a safe, human-readable folder name.

    Preserves case and spaces for browsability; strips only characters that are
    illegal in file paths.
    """
    name = (name or "").strip()
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "", name)
    name = re.sub(r"\s+", " ", name).strip().rstrip(". ")
    if name.upper() in _WINDOWS_RESERVED:
        name = f"_{name}"
    return name[:100].rstrip(". ") or "unknown-channel"


def summary_path(
    summaries_dir: str, channel: str, record: dict, task: str = "summary"
) -> str:
    slug = slugify(str(record.get("title") or record.get("video_id") or "video"))
    suffix = "" if task == "summary" else f"--{slugify(task, 30)}"
    return os.path.join(
        summaries_dir, channel, f"{record['video_id']}-{slug}{suffix}.md"
    )


def read_front_matter(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as handle:
            lines = handle.read(16384).splitlines()
    except OSError:
        return {}
    if not lines or lines[0] != "---":
        return {}
    result = {}
    for line in lines[1:]:
        if line == "---":
            break
        key, separator, raw = line.partition(":")
        if separator:
            try:
                result[key.strip()] = json.loads(raw.strip())
            except json.JSONDecodeError:
                result[key.strip()] = raw.strip()
    return result


def read_generated_content(path: str) -> str:
    """Read only the writer-generated portion of a summary file."""
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    marker = "\n\n[Watch on YouTube](<"
    start = text.find(marker)
    if start < 0:
        return text.strip()
    body = text.find("\n\n", start + len(marker))
    return text[body + 2 :].strip() if body >= 0 else ""


def find_existing_summary(
    summaries_dir: str,
    video_id: str,
    task: str = "summary",
    expected: dict | None = None,
) -> str | None:
    """Find any existing summary whose filename starts with the video id."""
    if not video_id or not os.path.isdir(summaries_dir):
        return None

    prefix = f"{video_id}-"
    matches: list[str] = []
    for root, _, files in os.walk(summaries_dir):
        for filename in files:
            if not (filename.startswith(prefix) and filename.endswith(".md")):
                continue
            path = os.path.join(root, filename)
            metadata = read_front_matter(path)
            if metadata and metadata.get("task", "summary") != task:
                continue
            if expected and any(
                metadata.get(key) != value for key, value in expected.items()
            ):
                continue
            matches.append(path)

    return sorted(matches)[0] if matches else None


def relative_summary_path(summaries_dir: str, path: str) -> str:
    try:
        return os.path.relpath(path, summaries_dir)
    except ValueError:
        return path


def _fmt_upload_date(yyyymmdd) -> str:
    if not yyyymmdd or len(str(yyyymmdd)) != 8:
        return "unknown"
    s = str(yyyymmdd)
    return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"


def write_summary(
    summaries_dir: str,
    channel: str,
    record: dict,
    summary: str,
    model: str,
    *,
    task: str = "summary",
    provenance: dict | None = None,
) -> str:
    path = summary_path(summaries_dir, channel, record, task)
    os.makedirs(os.path.dirname(path), exist_ok=True)

    metadata = {
        "video_id": record.get("video_id"),
        "channel": record.get("channel"),
        "uploaded": _fmt_upload_date(record.get("upload_date")),
        "url": record.get("webpage_url"),
        "transcript_source": record.get("transcript_source"),
        "transcript_language": record.get("transcript_lang"),
        "task": task,
        "summarized_with": model,
        "summarized_at": datetime.now(timezone.utc).isoformat(),
        **(provenance or {}),
    }
    front_matter = (
        "---\n"
        + "".join(
            f"{key}: {json.dumps(value, ensure_ascii=False)}\n"
            for key, value in metadata.items()
        )
        + "---\n\n"
    )
    title = re.sub(r"[\r\n]+", " ", str(record.get("title") or "Untitled")).strip()
    url = str(record.get("webpage_url") or "").replace(">", "%3E")
    header = front_matter + f"# {title}\n\n[Watch on YouTube](<{url}>)\n\n"
    try:
        fd, tmp = tempfile.mkstemp(
            prefix=f".{os.path.basename(path)}.", dir=os.path.dirname(path), text=True
        )
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(header + summary.rstrip() + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except OSError as exc:
        with suppress(OSError, UnboundLocalError):
            os.unlink(tmp)
        raise OutputError(f"Could not write summary {path}: {exc}") from exc
    return path

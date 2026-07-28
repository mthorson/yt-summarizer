"""Resolve raw CLI inputs (URLs, bare IDs, files, playlists) into video URLs."""

from __future__ import annotations

import os
import re
from collections.abc import Iterable
from urllib.parse import parse_qs, urlparse

from yt_dlp import YoutubeDL

_BARE_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


def _watch_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def video_id_from_url(raw: str) -> str | None:
    """Return a YouTube video id from a direct video input, if one is present."""
    raw = raw.strip()
    if _BARE_ID.match(raw):
        return raw

    parsed = urlparse(raw)
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]

    if host == "youtu.be":
        video_id = parsed.path.strip("/").split("/", 1)[0]
        return video_id if _BARE_ID.match(video_id) else None

    if host not in {"youtube.com", "m.youtube.com", "music.youtube.com"}:
        return None

    if parsed.path == "/watch":
        query_video_id = parse_qs(parsed.query).get("v", [None])[0]
        return (
            query_video_id
            if query_video_id and _BARE_ID.match(query_video_id)
            else None
        )

    for prefix in ("/shorts/", "/embed/", "/live/"):
        if parsed.path.startswith(prefix):
            video_id = parsed.path[len(prefix) :].split("/", 1)[0]
            return video_id if _BARE_ID.match(video_id) else None

    return None


def _read_list_file(path: str) -> list[str]:
    items: list[str] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            items.append(line)
    return items


def _normalize(raw: str) -> str:
    """A bare 11-char id becomes a watch URL; everything else passes through."""
    video_id = video_id_from_url(raw)
    if video_id:
        return _watch_url(video_id)
    return raw


def _expand(url: str) -> list[str]:
    """Expand a playlist/channel URL into individual video URLs.

    Uses a flat extraction (no per-video network calls) purely to enumerate
    entries. A plain video URL returns itself.
    """
    video_id = video_id_from_url(url)
    if video_id:
        return [_watch_url(video_id)]

    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": "in_playlist",
        "skip_download": True,
    }
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception:
        # A dead/unavailable URL shouldn't crash resolution for the whole batch.
        # Pass it through so the per-video loop reports the failure in isolation.
        return [url]

    if not info:
        return [url]

    if info.get("_type") == "playlist" or info.get("entries"):
        urls: list[str] = []
        for entry in info.get("entries") or []:
            if not entry:
                continue
            entry_url = entry.get("url") or entry.get("webpage_url")
            vid = entry.get("id")
            if entry_url and entry_url.startswith("http"):
                urls.append(entry_url)
            elif vid:
                urls.append(_watch_url(vid))
        return urls

    return [url]


def resolve_inputs(raw_inputs: Iterable[str]) -> list[str]:
    """Turn CLI args into a de-duplicated, ordered list of video URLs."""
    seed: list[str] = []
    for raw in raw_inputs:
        if os.path.isfile(raw):
            seed.extend(_read_list_file(raw))
        else:
            seed.append(raw)

    expanded: list[str] = []
    for item in seed:
        expanded.extend(_expand(_normalize(item)))

    # de-dupe while preserving order
    seen: set[str] = set()
    ordered: list[str] = []
    for u in expanded:
        if u not in seen:
            seen.add(u)
            ordered.append(u)
    return ordered

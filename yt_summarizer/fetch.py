"""Fetch metadata + transcript for a single video.

Transcript sources, in order of preference:
  1. Manual captions in the requested language
  2. Auto-generated captions in the requested language
  3. Any caption track whose code starts with the requested language
  4. Whisper transcription of the audio (only if `whisper=True`)
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import urllib.request

from yt_dlp import YoutubeDL

from .errors import FetchError

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


# --------------------------------------------------------------------------- #
# Metadata
# --------------------------------------------------------------------------- #
def get_info(url: str) -> dict:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "writesubtitles": False,
        "writeautomaticsub": False,
        "js_runtimes": {"deno": {}, "node": {}},
    }
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if not info:
        raise FetchError(f"Could not extract info for {url}")
    return info


# --------------------------------------------------------------------------- #
# Captions
# --------------------------------------------------------------------------- #
def _pick_track(
    tracks: dict, lang: str, *, prefer_original: bool = False
) -> tuple[str, list] | None:
    """Return (language code, formats) while tolerating variants like en-US."""
    if not tracks:
        return None
    # With dubbed audio, `en` can be a translation of another language while
    # `en-orig` is the actual English caption track. Prefer the native captions.
    if prefer_original and f"{lang}-orig" in tracks:
        return f"{lang}-orig", tracks[f"{lang}-orig"]
    if lang in tracks:
        return lang, tracks[lang]
    for code, track in tracks.items():
        if code.lower().startswith(lang.lower()):
            return code, track
    return None


def _fetch_url(url: str, max_bytes: int = 50 * 1024 * 1024) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read(max_bytes + 1)
        if len(raw) > max_bytes:
            raise FetchError("caption track exceeded the 50 MiB safety limit")
        return raw.decode("utf-8", errors="replace")


def _seconds(value: int | float | None) -> float:
    return round(float(value or 0) / 1000, 3)


def _parse_json3_segments(raw: str) -> list[dict]:
    data = json.loads(raw)
    segments: list[dict] = []
    for event in data.get("events", []):
        parts = event.get("segs")
        if not parts:
            continue
        text = re.sub(
            r"\s+", " ", "".join(part.get("utf8", "") for part in parts)
        ).strip()
        if text:
            segments.append(
                {
                    "start": _seconds(event.get("tStartMs")),
                    "duration": _seconds(event.get("dDurationMs")),
                    "text": text,
                }
            )
    return segments


def _parse_json3(raw: str) -> str:
    return " ".join(segment["text"] for segment in _parse_json3_segments(raw))


_VTT_TIME = re.compile(
    r"(?:(\d+):)?(\d{2}):(\d{2}(?:\.\d+)?)\s+-->\s+"
    r"(?:(\d+):)?(\d{2}):(\d{2}(?:\.\d+)?)"
)


def _vtt_seconds(hours: str | None, minutes: str, seconds: str) -> float:
    return int(hours or 0) * 3600 + int(minutes) * 60 + float(seconds)


def _parse_vtt_segments(raw: str) -> list[dict]:
    segments: list[dict] = []
    blocks = re.split(r"\n\s*\n", raw.replace("\r\n", "\n"))
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        timing_index = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if timing_index is None:
            continue
        match = _VTT_TIME.search(lines[timing_index])
        if not match:
            continue
        text = " ".join(lines[timing_index + 1 :])
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            continue
        start = _vtt_seconds(*match.groups()[0:3])
        end = _vtt_seconds(*match.groups()[3:6])
        # Auto-caption VTT often repeats the growing cue. Replace an overlapping
        # previous cue when the new text contains it instead of duplicating it.
        if segments and start <= segments[-1]["start"] + segments[-1]["duration"]:
            previous = segments[-1]["text"]
            if text == previous:
                continue
            if text.startswith(previous):
                segments.pop()
        segments.append({"start": start, "duration": max(0, end - start), "text": text})
    return segments


def _parse_vtt(raw: str) -> str:
    return " ".join(segment["text"] for segment in _parse_vtt_segments(raw))


def _extract_from_track(track: list) -> tuple[str, list[dict]] | None:
    """Given a yt-dlp caption track (list of format dicts), download & parse."""
    by_ext = {fmt.get("ext"): fmt for fmt in track if fmt.get("url")}
    for ext in ("json3", "srv3", "srv1", "vtt"):
        fmt = by_ext.get(ext)
        if not fmt:
            continue
        try:
            raw = _fetch_url(fmt["url"])
        except Exception:
            continue
        try:
            segments = (
                _parse_json3_segments(raw)
                if ext == "json3"
                else _parse_vtt_segments(raw)
            )
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
        text = " ".join(segment["text"] for segment in segments)
        if text:
            return text, segments
    return None


def extract_captions(info: dict, lang: str) -> tuple[str, str, str, list[dict]] | None:
    """Return (transcript, source, actual language, timed segments), or None."""
    manual = info.get("subtitles") or {}
    auto = info.get("automatic_captions") or {}

    selected = _pick_track(manual, lang)
    if selected:
        actual_lang, track = selected
        result = _extract_from_track(track)
        if result:
            text, segments = result
            return text, "captions", actual_lang, segments

    selected = _pick_track(auto, lang, prefer_original=True)
    if selected:
        actual_lang, track = selected
        result = _extract_from_track(track)
        if result:
            text, segments = result
            return text, "auto-captions", actual_lang, segments

    return None


# --------------------------------------------------------------------------- #
# Whisper fallback
# --------------------------------------------------------------------------- #
def _ensure_whisper_model():
    """Return WhisperModel or explain how to install the optional dependency."""
    try:
        from faster_whisper import WhisperModel

        return WhisperModel
    except ImportError as exc:
        raise FetchError(
            "Whisper support is not installed. Run:\n"
            "  uv tool install 'yt-summarizer[whisper]'\n"
            "or, from a checkout:\n"
            "  uv sync --extra whisper"
        ) from exc


def whisper_transcribe(url: str, model_size: str) -> tuple[str, list[dict]]:
    WhisperModel = _ensure_whisper_model()

    with tempfile.TemporaryDirectory() as tmp:
        outtmpl = os.path.join(tmp, "%(id)s.%(ext)s")
        opts = {
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "format": "bestaudio/best",
            "outtmpl": outtmpl,
            "js_runtimes": {"deno": {}, "node": {}},
        }
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            audio_path = ydl.prepare_filename(info)

        if not os.path.isfile(audio_path):
            # yt-dlp may have chosen a different extension; grab whatever landed
            files = [os.path.join(tmp, f) for f in os.listdir(tmp)]
            if not files:
                raise FetchError(f"Audio download produced no file for {url}")
            audio_path = files[0]

        def transcribe(device: str):
            model = WhisperModel(model_size, device=device, compute_type="int8")
            segments, _ = model.transcribe(audio_path, vad_filter=True)
            return [
                {
                    "start": round(float(seg.start), 3),
                    "duration": round(float(seg.end - seg.start), 3),
                    "text": seg.text.strip(),
                }
                for seg in segments
                if seg.text.strip()
            ]

        try:
            timed = transcribe("auto")
        except RuntimeError as exc:
            detail = str(exc).lower()
            if not any(name in detail for name in ("cuda", "cublas", "cudnn")):
                raise
            timed = transcribe("cpu")
        text = " ".join(segment["text"] for segment in timed)
        return re.sub(r"\s+", " ", text).strip(), timed


# --------------------------------------------------------------------------- #
# Record assembly
# --------------------------------------------------------------------------- #
def build_record(
    info: dict,
    transcript: str,
    source: str,
    lang: str,
    segments: list[dict] | None = None,
) -> dict:
    return {
        "video_id": info.get("id"),
        "title": info.get("title"),
        "channel": info.get("channel") or info.get("uploader"),
        "duration": info.get("duration"),  # seconds
        "upload_date": info.get("upload_date"),  # YYYYMMDD
        "webpage_url": info.get("webpage_url"),
        "description": info.get("description"),
        "transcript": transcript,
        "segments": segments or [],
        "transcript_source": source,  # captions | auto-captions | whisper
        "transcript_lang": lang,
    }

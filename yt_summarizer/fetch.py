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
from collections.abc import Callable

from yt_dlp import YoutubeDL

from . import ytdlp
from .errors import FetchError


# --------------------------------------------------------------------------- #
# Metadata
# --------------------------------------------------------------------------- #
def get_info(url: str, *, ydl_opts: dict | None = None) -> dict:
    opts = ytdlp.options(
        ydl_opts,
        skip_download=True,
        # Captions and metadata can be available even when audio/video formats
        # are not. Only the Whisper download needs a playable media format.
        ignore_no_formats_error=True,
        writesubtitles=False,
        writeautomaticsub=False,
    )
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


def _fetch_url(
    url: str, max_bytes: int = 50 * 1024 * 1024, *, ydl_opts: dict | None = None
) -> str:
    opts = ytdlp.options(ydl_opts)
    # Use yt-dlp's transport so caption requests share the supplied cookies and
    # metadata headers instead of silently making an unauthenticated request.
    with YoutubeDL(opts) as ydl, ydl.urlopen(url) as resp:
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


def _extract_from_track(
    track: list, *, ydl_opts: dict | None = None
) -> tuple[str, list[dict]] | None:
    """Given a yt-dlp caption track (list of format dicts), download & parse."""
    by_ext = {fmt.get("ext"): fmt for fmt in track if fmt.get("url")}
    for ext in ("json3", "srv3", "srv1", "vtt"):
        fmt = by_ext.get(ext)
        if not fmt:
            continue
        try:
            raw = _fetch_url(fmt["url"], ydl_opts=ydl_opts)
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


def extract_captions(
    info: dict, lang: str, *, ydl_opts: dict | None = None
) -> tuple[str, str, str, list[dict]] | None:
    """Return (transcript, source, actual language, timed segments), or None."""
    manual = info.get("subtitles") or {}
    auto = info.get("automatic_captions") or {}
    caption_opts = dict(ydl_opts or {})
    if info.get("http_headers"):
        caption_opts["http_headers"] = info["http_headers"]

    selected = _pick_track(manual, lang)
    if selected:
        actual_lang, track = selected
        result = _extract_from_track(track, ydl_opts=caption_opts)
        if result:
            text, segments = result
            return text, "captions", actual_lang, segments

    selected = _pick_track(auto, lang, prefer_original=True)
    if selected:
        actual_lang, track = selected
        result = _extract_from_track(track, ydl_opts=caption_opts)
        if result:
            text, segments = result
            return text, "auto-captions", actual_lang, segments

    return None


# --------------------------------------------------------------------------- #
# Whisper fallback
# --------------------------------------------------------------------------- #
def _ensure_whisper_model():
    """Return WhisperModel or explain how to install the optional dependency."""
    _configure_windows_cuda_libraries()
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


def _configure_windows_cuda_libraries() -> None:
    """Expose optional NVIDIA wheel DLLs to CTranslate2 in this process only."""
    if os.name != "nt":
        return
    from importlib.metadata import PackageNotFoundError, distribution

    paths = os.environ.get("PATH", "").split(os.pathsep)
    for package in (
        "nvidia-cublas-cu12",
        "nvidia-cuda-nvrtc-cu12",
        "nvidia-cudnn-cu12",
    ):
        try:
            installed = distribution(package)
        except PackageNotFoundError:
            continue
        for file in installed.files or []:
            if str(file).lower().endswith(".dll"):
                directory = os.path.dirname(str(installed.locate_file(file)))
                if directory not in paths:
                    paths.insert(0, directory)
    os.environ["PATH"] = os.pathsep.join(paths)


def whisper_transcribe(
    url: str,
    model_size: str,
    *,
    device: str = "auto",
    ydl_opts: dict | None = None,
    on_progress: Callable[[str], None] | None = None,
) -> tuple[str, list[dict]]:
    """Download the audio and transcribe it locally.

    ``on_progress`` receives short human-readable status strings such as
    ``"downloading audio"`` or ``"transcribing 42%"``.
    """
    if device not in {"auto", "cuda", "cpu"}:
        raise FetchError(f"Unsupported Whisper device: {device}")
    report = on_progress or (lambda _message: None)
    # Model downloads otherwise draw tqdm bars over the live progress display.
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    WhisperModel = _ensure_whisper_model()

    with tempfile.TemporaryDirectory() as tmp:
        outtmpl = os.path.join(tmp, "%(id)s.%(ext)s")
        opts = ytdlp.options(ydl_opts, format="bestaudio/best", outtmpl=outtmpl)
        report("downloading audio")
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
            report(f"loading Whisper model ({model_size}, {device})")
            model = WhisperModel(model_size, device=device, compute_type="int8")
            segments, meta = model.transcribe(audio_path, vad_filter=True)
            total = float(getattr(meta, "duration", 0) or 0)
            report("transcribing")
            timed = []
            for seg in segments:
                if total > 0:
                    percent = min(99, int(float(seg.end) / total * 100))
                    report(f"transcribing {percent}%")
                if seg.text.strip():
                    timed.append(
                        {
                            "start": round(float(seg.start), 3),
                            "duration": round(float(seg.end - seg.start), 3),
                            "text": seg.text.strip(),
                        }
                    )
            return timed

        try:
            timed = transcribe(device)
        except RuntimeError as exc:
            if device == "cuda":
                raise FetchError(
                    "Whisper GPU execution failed; CPU fallback is disabled by "
                    f"--whisper-device cuda. Check the NVIDIA CUDA libraries. {exc}"
                ) from exc
            detail = str(exc).lower()
            if device != "auto" or not any(
                name in detail for name in ("cuda", "cublas", "cudnn")
            ):
                raise
            report("GPU unavailable, falling back to CPU")
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

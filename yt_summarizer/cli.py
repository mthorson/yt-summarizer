"""Command-line entry point and batch orchestration."""

from __future__ import annotations

import argparse
import contextlib
import json
import logging
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
import warnings
import webbrowser
from pathlib import Path
from typing import Any

from yt_dlp.utils import DownloadError

from . import cache, config, fetch, output, prompts, summarize
from .errors import YtsError
from .inputs import resolve_inputs, video_id_from_url
from .progress import ProgressReporter, ReporterLogHandler, format_duration
from .prompts import (
    BUILTIN_PRESETS,
    CUSTOM_SYSTEM_PROMPT,
    DEFAULT_PROMPT,
)
from .ytdlp import clean_message


def _config_preparse(argv: list[str]) -> str | None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--config")
    args, _ = parser.parse_known_args(argv)
    return args.config


def build_parser(settings: dict[str, Any] | None = None) -> argparse.ArgumentParser:
    settings = settings or {}
    p = argparse.ArgumentParser(
        prog="yts",
        description="Turn YouTube videos into timestamped, transcript-grounded notes.",
    )
    p.add_argument(
        "inputs",
        nargs="*",
        help="Video URL/ID, playlist/channel URL, or a text file of URLs.",
    )
    p.add_argument(
        "--config", help=f"TOML config path. Default: {config.config_path()}."
    )
    p.add_argument(
        "-c",
        "--cache-dir",
        default=config.setting(settings, "cache_dir", config.default_cache_dir()),
        help="Transcript and intermediate-result cache directory.",
    )
    p.add_argument(
        "-o",
        "--out-dir",
        default=config.setting(settings, "output_dir", config.default_output_dir()),
        help="Markdown output directory.",
    )
    p.add_argument("-p", "--prompt", help="Use a one-off inline instruction.")
    p.add_argument(
        "-P", "--prompt-file", help="Read a one-off instruction from a file."
    )
    p.add_argument(
        "--preset",
        default=config.setting(settings, "preset", "summary"),
        help="Named built-in or configured prompt preset. Default: summary.",
    )
    p.add_argument(
        "--task",
        help="Stable output task name. Defaults to the preset name or 'custom'.",
    )
    p.add_argument(
        "--list-presets", action="store_true", help="List available presets and exit."
    )
    p.add_argument(
        "-w",
        "--writer",
        default=config.setting(settings, "writer", "codex"),
        choices=["auto", "claude", "codex"],
        help="Writer CLI. Auto prefers Codex, then Claude. Default: codex.",
    )
    p.add_argument(
        "--claude-bin",
        default=config.setting(settings, "claude_bin", "claude"),
        help="Claude Code command or path.",
    )
    p.add_argument(
        "--codex-bin",
        default=config.setting(settings, "codex_bin", "codex"),
        help="Codex command or path.",
    )
    p.add_argument(
        "-m",
        "--model",
        default=config.setting(settings, "model", "auto"),
        help="Model name. Auto uses writer-specific routing/default behavior.",
    )
    p.add_argument(
        "-T",
        "--long-threshold",
        type=int,
        default=int(settings.get("long_threshold", 45000)),
        help="Claude auto-routing threshold in estimated tokens.",
    )
    p.add_argument(
        "--chunk-tokens",
        type=int,
        default=int(settings.get("chunk_tokens", 30000)),
        help="Split transcripts above this estimated token count. Default: 30000.",
    )
    p.add_argument(
        "--no-chunk",
        action="store_true",
        help="Send the full transcript in one writer call.",
    )
    p.add_argument(
        "--chunk-overlap",
        type=int,
        default=int(settings.get("chunk_overlap", 400)),
        help="Approximate characters repeated across chunk boundaries. Default: 400.",
    )
    p.add_argument(
        "-l",
        "--lang",
        default=config.setting(settings, "language", "en"),
        help="Preferred caption (transcript) language. Default: en.",
    )
    p.add_argument(
        "-sl",
        "--summary-lang",
        metavar="LANG",
        default=config.setting(settings, "summary_language", None),
        help=(
            "Language to write the summary in, e.g. tr, en, de, or a language "
            "name. Independent of --lang. Default: English (or summary_language "
            "in the config file)."
        ),
    )
    cookies = p.add_mutually_exclusive_group()
    cookies.add_argument(
        "--cookies", metavar="FILE", help="Read YouTube cookies from a Netscape file."
    )
    cookies.add_argument(
        "--cookies-from-browser",
        choices=[
            "brave",
            "chrome",
            "chromium",
            "edge",
            "firefox",
            "opera",
            "safari",
            "vivaldi",
            "whale",
        ],
        help="Use the selected browser's cookies for YouTube requests.",
    )
    p.add_argument(
        "-W",
        "--whisper",
        action="store_true",
        help="Use local Whisper when captions are unavailable.",
    )
    p.add_argument(
        "--force-whisper",
        action="store_true",
        help="Ignore available captions and transcribe the audio with Whisper.",
    )
    p.add_argument(
        "-M",
        "--whisper-model",
        default=config.setting(settings, "whisper_model", "base"),
        help="faster-whisper model size.",
    )
    p.add_argument(
        "--whisper-device",
        choices=["auto", "cuda", "cpu"],
        default=config.setting(settings, "whisper_device", "auto"),
        help="Whisper device. cuda requires GPU support and never falls back to CPU.",
    )
    p.add_argument("-f", "--force", action="store_true", help="Regenerate output.")
    p.add_argument(
        "-r", "--refetch", action="store_true", help="Ignore cached transcript data."
    )
    p.add_argument(
        "-s",
        "--sleep",
        type=float,
        default=0.0,
        help="Seconds to pause between videos.",
    )
    p.add_argument(
        "-t",
        "--timeout",
        type=int,
        default=int(settings.get("timeout", 600)),
        help="Per-writer-call timeout in seconds.",
    )
    p.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress progress and summary output.",
    )
    p.add_argument(
        "--stdout",
        action="store_true",
        help="Print generated content only, including for batch input.",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="Print a machine-readable run report to stdout.",
    )
    p.add_argument("--open", action="store_true", help="Open written summaries.")
    p.add_argument(
        "--report",
        help="Write JSON batch report. Defaults to OUT_DIR/last-run.json for batches.",
    )
    p.add_argument(
        "-d", "--doctor", action="store_true", help="Check local readiness and exit."
    )
    p.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show every step, library warnings, and full error details.",
    )
    return p


def _available_presets(settings: dict[str, Any]) -> dict[str, str]:
    return {**BUILTIN_PRESETS, **config.presets(settings)}


def _load_task(args, settings: dict[str, Any]) -> tuple[str, str]:
    if args.prompt_file:
        try:
            prompt = Path(args.prompt_file).read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise YtsError(
                f"Could not read prompt file {args.prompt_file}: {exc}"
            ) from exc
        return args.task or "custom", prompt
    if args.prompt:
        return args.task or "custom", args.prompt.strip()
    presets = _available_presets(settings)
    if args.preset not in presets:
        names = ", ".join(sorted(presets))
        raise YtsError(f"Unknown preset '{args.preset}'. Available presets: {names}")
    return args.task or args.preset, presets[args.preset]


def _youtube_options(args) -> dict:
    cookie_file = getattr(args, "cookies", None)
    if cookie_file:
        path = Path(cookie_file).expanduser()
        if not path.is_file():
            raise YtsError(f"Cookie file does not exist: {path}")
        return {"cookiefile": str(path)}
    browser = getattr(args, "cookies_from_browser", None)
    return {"cookiesfrombrowser": (browser,)} if browser else {}


def _get_record(url: str, args, reporter: ProgressReporter) -> dict:
    video_id = video_id_from_url(url)
    if not args.refetch and video_id:
        cached = cache.find(args.cache_dir, video_id)
        if cached:
            reporter.phase("using cached transcript")
            return cached

    reporter.phase("fetching video info")
    youtube_options = _youtube_options(args)
    info = fetch.get_info(url, ydl_opts=youtube_options)
    reporter.set_title(str(info.get("title") or ""))
    video_id = info.get("id")
    channel = output.sanitize_channel(
        str(info.get("channel") or info.get("uploader") or "")
    )
    if not args.refetch and video_id:
        cached = cache.load(args.cache_dir, channel, video_id)
        if cached and cached.get("transcript"):
            reporter.phase("using cached transcript")
            return cached

    reporter.phase("fetching captions")
    force_whisper = getattr(args, "force_whisper", False)
    result = (
        None
        if force_whisper
        else fetch.extract_captions(info, args.lang, ydl_opts=youtube_options)
    )
    if result:
        transcript, source, lang, segments = result
    elif args.whisper or force_whisper:
        whisper_device = getattr(args, "whisper_device", "auto")
        reporter.phase("no captions, using Whisper")
        transcript, segments = fetch.whisper_transcribe(
            url,
            args.whisper_model,
            device=whisper_device,
            ydl_opts=youtube_options,
            on_progress=lambda message: reporter.phase(f"Whisper: {message}"),
        )
        source, lang = "whisper", args.lang
    else:
        raise fetch.FetchError(
            "No usable captions were found. Retry with --whisper or another --lang."
        )
    record = fetch.build_record(info, transcript, source, lang, segments)
    cache.save(args.cache_dir, channel, record)
    return record


def _provenance(
    record: dict, task: str, prompt: str, writer: str, model_label: str
) -> dict:
    return {
        "schema_version": 2,
        "prompt_hash": cache.text_hash(prompt),
        "transcript_hash": cache.text_hash(record.get("transcript", "")),
        "writer": writer,
        "model": model_label,
        "generator_version": _package_version(),
    }


def _package_version() -> str:
    from . import __version__

    return __version__


def _summarize_record(
    record: dict,
    args,
    prompt: str,
    writer: str,
    model: str | None,
    reporter: ProgressReporter,
) -> str:
    common = {
        "system_prompt": CUSTOM_SYSTEM_PROMPT,
        "model": model,
        "writer": writer,
        "timeout": args.timeout,
        "claude_bin": args.claude_bin,
        "codex_bin": args.codex_bin,
    }
    chunk_tokens = getattr(args, "chunk_tokens", 30000)
    if getattr(args, "no_chunk", False) or (
        summarize.estimate_tokens(record["transcript"]) <= chunk_tokens
    ):
        return summarize.summarize(record, user_prompt=prompt, **common)

    chunks = summarize.split_record(
        record, chunk_tokens, overlap_chars=getattr(args, "chunk_overlap", 400)
    )
    fingerprint = cache.text_hash(
        "\0".join(
            [
                record["transcript"],
                prompt,
                writer,
                model or "default",
                str(chunk_tokens),
                "chunk-v1",
            ]
        )
    )
    notes = (
        cache.load_chunk_result(args.cache_dir, record["video_id"], fingerprint) or []
    )
    chunk_prompt = (
        "Create faithful, detailed notes for this portion of the video. Preserve "
        "claims, qualifications, named entities, numbers, and timestamp links. "
        "Do not write an overall introduction or conclusion."
    )
    for index, chunk in enumerate(chunks[len(notes) :], len(notes) + 1):
        reporter.phase(f"summarizing chunk {index}/{len(chunks)}")
        notes.append(summarize.summarize(chunk, user_prompt=chunk_prompt, **common))
        cache.save_chunk_result(args.cache_dir, record["video_id"], fingerprint, notes)

    reporter.phase("synthesizing chunk notes")
    synthesis = {
        **record,
        "transcript": "\n\n".join(
            f"## Chunk {index}\n{note}" for index, note in enumerate(notes, 1)
        ),
        "segments": [],
    }
    synthesis_prompt = (
        f"{prompt}\n\nThe source below contains faithful notes from consecutive "
        "chunks of one video. Synthesize them without dropping important "
        "qualifications or inventing information."
    )
    return summarize.summarize(synthesis, user_prompt=synthesis_prompt, **common)


def _fold(text: str) -> str:
    # casefold() maps Turkish dotted/dotless I inconsistently; normalise them.
    return text.replace("İ", "i").replace("I", "i").replace("ı", "i").casefold()


def localize_prompt(prompt: str, language: str | None) -> str:
    """Apply --summary-lang to the selected instruction."""
    if not language:
        return prompt
    if prompt == DEFAULT_PROMPT:
        prompt = prompts.summary_prompt(language)
    return f"{prompt}\n\n{prompts.language_instruction(language)}"


def expected_headings(
    task: str, prompt: str, language: str | None
) -> tuple[str, ...] | None:
    """Headings the built-in summary must contain, or None to skip the check."""
    if task != "summary" or prompt != localize_prompt(DEFAULT_PROMPT, language):
        return None
    return prompts.SUMMARY_HEADINGS.get(language or "en")


def _validate_result(
    task: str, text: str, headings: tuple[str, ...] | None = ("TL;DR", "Key takeaways")
) -> None:
    if not text.strip():
        raise summarize.SummarizeError("Writer returned empty Markdown")
    if task == "summary" and headings:
        missing = [label for label in headings if _fold(label) not in _fold(text)]
        if missing:
            raise summarize.SummarizeError(
                "Writer output did not follow the summary format; missing "
                + ", ".join(missing)
            )


def process_one(
    url: str,
    args,
    user_prompt: str,
    writer: str,
    reporter: ProgressReporter,
    task: str | None = None,
) -> tuple[str, str]:
    language = getattr(args, "summary_lang", None)
    task = task or (
        "summary"
        if user_prompt == localize_prompt(DEFAULT_PROMPT, language)
        else "custom"
    )
    record = _get_record(url, args, reporter)
    reporter.set_title(str(record.get("title") or ""))
    channel = output.sanitize_channel(str(record.get("channel") or ""))
    model = summarize.choose_model(
        record["transcript"], args.model, args.long_threshold, writer=writer
    )
    model_label = model or "builtin-default"
    provenance = _provenance(record, task, user_prompt, writer, model_label)
    if not args.force:
        existing = output.find_existing_summary(
            args.out_dir,
            record["video_id"],
            task=task,
            expected=provenance,
        )
        if existing:
            rel = output.relative_summary_path(args.out_dir, existing)
            return f"skip (current): {rel}", existing

    reporter.phase(f"summarizing with {writer}:{model_label}")
    summary = _summarize_record(record, args, user_prompt, writer, model, reporter)
    _validate_result(task, summary, expected_headings(task, user_prompt, language))
    writer_model = f"{writer}:{model_label}"
    reporter.phase("writing summary")
    path = output.write_summary(
        args.out_dir,
        channel,
        record,
        summary,
        writer_model,
        task=task,
        provenance=provenance,
    )
    rel = output.relative_summary_path(args.out_dir, path)
    return f"summarized [{writer_model}]: {rel}", path


def _version_for(command: str, *version_args: str) -> str:
    if os.path.sep not in command and not shutil.which(command):
        return "not found"
    try:
        proc = subprocess.run(
            [command, *version_args],
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=5,
        )
    except Exception as exc:  # noqa: BLE001 - diagnostics should continue
        return f"found, version check failed: {exc}"
    lines = (proc.stdout or proc.stderr or "").strip().splitlines()
    first = lines[0] if lines else "no version output"
    return f"found: {first}" if proc.returncode == 0 else f"check failed: {first}"


def _directory_status(path: str) -> str:
    selected = Path(path).expanduser()
    existing = next(
        (parent for parent in [selected, *selected.parents] if parent.exists()), None
    )
    if not existing:
        return "no existing parent"
    return (
        f"ready ({selected})"
        if os.access(existing, os.W_OK)
        else f"not writable ({existing})"
    )


def run_doctor(args) -> int:
    claude_compatible = summarize.writer_capabilities("claude", args.claude_bin)
    codex_compatible = summarize.writer_capabilities("codex", args.codex_bin)
    claude_auth = summarize.writer_authentication("claude", args.claude_bin)
    codex_auth = summarize.writer_authentication("codex", args.codex_bin)
    checks = {
        "python": sys.version.split()[0],
        "yt-dlp": _version_for(sys.executable, "-m", "yt_dlp", "--version"),
        "claude": _version_for(args.claude_bin, "--version"),
        "claude auth": ": ".join(
            ("ready" if claude_auth[0] else "unavailable", claude_auth[1])
        ),
        "claude compatibility": ": ".join(
            ("ready" if claude_compatible[0] else "incompatible", claude_compatible[1])
        ),
        "codex": _version_for(args.codex_bin, "--version"),
        "codex auth": ": ".join(
            ("ready" if codex_auth[0] else "unavailable", codex_auth[1])
        ),
        "codex compatibility": ": ".join(
            ("ready" if codex_compatible[0] else "incompatible", codex_compatible[1])
        ),
        "ffmpeg": _version_for("ffmpeg", "-version"),
        "cache": _directory_status(args.cache_dir),
        "output": _directory_status(args.out_dir),
    }
    print("yt-summarizer doctor")
    for name, result in checks.items():
        print(f"{name}: {result}")
    try:
        selected = summarize.resolve_writer(
            args.writer, args.claude_bin, args.codex_bin
        )
    except summarize.SummarizeError as exc:
        print(f"selected writer: unavailable ({exc})")
        return 1
    print(f"selected writer: {selected}")
    selected_compatible = codex_compatible if selected == "codex" else claude_compatible
    selected_auth = codex_auth if selected == "codex" else claude_auth
    return 0 if selected_compatible[0] and selected_auth[0] else 1


def _write_report(path: str, report: dict) -> None:
    selected = Path(path).expanduser()
    selected.parent.mkdir(parents=True, exist_ok=True)
    tmp = selected.with_suffix(selected.suffix + ".tmp")
    tmp.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(tmp, selected)


_ERROR_HINTS: list[tuple[tuple[str, ...], str, str | None]] = [
    # (substrings to look for, short message, hint)
    (
        ("sign in to confirm", "not a bot"),
        "YouTube asked for a sign-in (bot check).",
        "Pass --cookies youtube-cookies.txt or --cookies-from-browser firefox.",
    ),
    (
        ("members-only", "join this channel", "available to this channel's members"),
        "This video is members-only.",
        "Use cookies from an account that has access (--cookies / "
        "--cookies-from-browser).",
    ),
    (("private video",), "This video is private.", None),
    (
        ("age-restricted", "confirm your age", "inappropriate for some users"),
        "This video is age-restricted.",
        "Use cookies from a signed-in account (--cookies / --cookies-from-browser).",
    ),
    (
        ("http error 429", "too many requests"),
        "YouTube is rate-limiting requests (HTTP 429).",
        "Wait a while, use cookies, and add a pause between videos, e.g. --sleep 30.",
    ),
    (
        ("video unavailable", "this video has been removed", "is not available"),
        "The video is unavailable (removed, region-locked, or wrong URL).",
        None,
    ),
    (
        ("requested format is not available", "no video formats found"),
        "YouTube did not offer a downloadable audio stream.",
        "Update yt-dlp (uv tool upgrade yt-summarizer) or try cookies.",
    ),
    (
        ("ssl", "timed out", "connection reset", "getaddrinfo", "network"),
        "Network error while talking to YouTube.",
        "Usually temporary; run the same command again.",
    ),
]


def describe_error(exc: BaseException, verbose: bool = False) -> tuple[str, str | None]:
    """Turn an exception into one readable line plus an optional hint."""
    raw = clean_message(str(exc)) or type(exc).__name__
    if isinstance(exc, DownloadError):
        lowered = raw.lower()
        for needles, message, hint in _ERROR_HINTS:
            if any(needle in lowered for needle in needles):
                return (f"{message} ({raw})" if verbose else message), hint
        # Drop yt-dlp's "[youtube] <id>: " prefix; the video is already named.
        raw = re.sub(r"^\[[^\]]+\]\s*[\w-]+:\s*", "", raw)
    elif not isinstance(exc, YtsError):
        raw = f"{type(exc).__name__}: {raw}"

    hint = None
    lowered = raw.lower()
    if "timed out after" in lowered:
        hint = "Increase the writer timeout, e.g. --timeout 1200."
    elif "whisper gpu" in lowered or "cublas" in lowered or "cudnn" in lowered:
        hint = (
            "Use --whisper-device auto (falls back to CPU) or install the GPU "
            "libraries: uv tool install -e '.[whisper,windows-gpu]'."
        )
    elif "not authenticated" in lowered:
        hint = "Sign in to the writer CLI first, then retry."

    if not verbose:
        raw = " ".join(raw.split())
        if len(raw) > 300:
            raw = raw[:299] + "… (use -v for the full message)"
    return raw, hint


def _display_path(path: str) -> str:
    try:
        path = os.path.normpath(path)
        relative = os.path.relpath(path)
    except ValueError:
        return path
    return path if relative.startswith("..") else relative


def _writer_model(status: str) -> str | None:
    match = re.search(r"\[([^\]]+)\]", status)
    return match.group(1) if match else None


def _read_stdin_inputs() -> list[str]:
    return [
        line.strip()
        for line in sys.stdin
        if line.strip() and not line.lstrip().startswith("#")
    ]


def _safe_streams() -> None:
    """Never crash on characters the console code page cannot encode."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            with contextlib.suppress(Exception):
                reconfigure(errors="replace")


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    _safe_streams()
    try:
        settings = config.load(_config_preparse(argv))
        args = build_parser(settings).parse_args(argv)
        available_presets = _available_presets(settings)
        if args.list_presets:
            for name in sorted(available_presets):
                print(name)
            return 0
        if args.doctor:
            return run_doctor(args)
        task, base_prompt = _load_task(args, settings)
        args.summary_lang = prompts.normalize_language(args.summary_lang)
        user_prompt = localize_prompt(base_prompt, args.summary_lang)
        youtube_options = _youtube_options(args)
    except (YtsError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    reporter = ProgressReporter(
        quiet=args.quiet or args.stdout or args.json, verbose=args.verbose
    )
    # Library warnings (yt-dlp, faster-whisper, Python warnings) go through the
    # reporter, which only shows them with --verbose.
    log_handler = ReporterLogHandler(reporter)
    root_logger = logging.getLogger()
    root_logger.addHandler(log_handler)
    try:
        with warnings.catch_warnings():
            if args.verbose:
                logging.captureWarnings(True)
            else:
                warnings.simplefilter("ignore")
            return _run(args, task, user_prompt, youtube_options, reporter)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
    finally:
        logging.captureWarnings(False)
        root_logger.removeHandler(log_handler)


def _run(
    args,
    task: str,
    user_prompt: str,
    youtube_options: dict,
    reporter: ProgressReporter,
) -> int:
    started = time.monotonic()
    results: list[dict] = []
    output_paths: list[str] = []
    summarized = skipped = 0

    with reporter:
        try:
            reporter.phase(f"checking the {args.writer} writer")
            writer = summarize.resolve_writer(
                args.writer, args.claude_bin, args.codex_bin
            )
            writer_command = args.codex_bin if writer == "codex" else args.claude_bin
            summarize.ensure_writer_compatible(writer, writer_command)
            summarize.ensure_writer_authenticated(writer, writer_command)
            raw_inputs = args.inputs
            if not raw_inputs and not sys.stdin.isatty():
                raw_inputs = _read_stdin_inputs()
            reporter.phase("reading input list")
            urls = resolve_inputs(raw_inputs, ydl_opts=youtube_options)
            if not urls:
                raise YtsError(
                    "No videos found. Pass a YouTube URL, video ID, playlist, or "
                    "a text file with one URL per line."
                )
        except (YtsError, ValueError, OSError, DownloadError) as exc:
            message, hint = describe_error(exc, args.verbose)
            reporter.error(f"error: {message}")
            if hint:
                reporter.error(f"hint: {hint}")
            return 1

        language = prompts.language_name(args.summary_lang or "en")
        count = f"{len(urls)} video" + ("s" if len(urls) != 1 else "")
        reporter.log(
            f"yts · {count} · {writer} · {task} in {language} "
            f"→ {_display_path(args.out_dir)}",
            style="dim",
        )

        reporter.start_batch(len(urls))
        for index, url in enumerate(urls, 1):
            reporter.start_video(index, len(urls), url)
            try:
                status, path = process_one(
                    url, args, user_prompt, writer, reporter, task=task
                )
            except Exception as exc:  # isolate per-video failures
                message, hint = describe_error(exc, args.verbose)
                reporter.failed(message, hint)
                results.append(
                    {
                        "url": url,
                        "status": "failed",
                        "error": message,
                        "retry": f"yts {shlex.quote(url)}",
                    }
                )
            else:
                shown = _display_path(path)
                if status.startswith("skip"):
                    skipped += 1
                    reporter.skipped("", shown)
                else:
                    summarized += 1
                    model = _writer_model(status)
                    reporter.succeeded("", shown + (f" [{model}]" if model else ""))
                results.append(
                    {"url": url, "status": "ok", "message": status, "path": path}
                )
                output_paths.append(path)
                if args.stdout and not args.json:
                    print(output.read_generated_content(path), flush=True)
            if args.sleep and index < len(urls):
                reporter.phase(f"waiting {args.sleep:g}s before the next video")
                time.sleep(args.sleep)

    failed = sum(item["status"] == "failed" for item in results)
    report = {
        "task": task,
        "writer": writer,
        "summary_language": args.summary_lang or "en",
        "succeeded": len(results) - failed,
        "failed": failed,
        "results": results,
    }
    report_path = args.report
    if not report_path and len(urls) > 1:
        report_path = os.path.join(args.out_dir, "last-run.json")
    if report_path:
        _write_report(report_path, report)

    if len(urls) > 1 or failed:
        parts = [f"{summarized} summarized"]
        if skipped:
            parts.append(f"{skipped} up to date")
        if failed:
            parts.append(f"{failed} failed")
        footer = f"Done in {format_duration(time.monotonic() - started)}: "
        footer += ", ".join(parts)
        if report_path and failed:
            footer += f". Details and retry commands: {_display_path(report_path)}"
        reporter.log(footer, style="bold")

    if args.open:
        for path in output_paths:
            webbrowser.open(Path(path).resolve().as_uri())
    if args.json:
        print(json.dumps(report, ensure_ascii=False))
    elif len(urls) == 1 and output_paths and not (args.quiet or args.stdout):
        print()
        print(output.read_generated_content(output_paths[0]))
    return 2 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

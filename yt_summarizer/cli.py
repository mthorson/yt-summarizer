"""Command-line entry point and batch orchestration."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from typing import Any

from . import cache, config, fetch, output, summarize
from .errors import YtsError
from .inputs import resolve_inputs, video_id_from_url
from .progress import ProgressReporter
from .prompts import (
    BUILTIN_PRESETS,
    CUSTOM_SYSTEM_PROMPT,
    DEFAULT_PROMPT,
)


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
        help="Preferred caption language.",
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
        "-v", "--verbose", action="store_true", help="Include exception details."
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


def _get_record(url: str, args, reporter: ProgressReporter) -> dict:
    video_id = video_id_from_url(url)
    if not args.refetch and video_id:
        cached = cache.find(args.cache_dir, video_id)
        if cached:
            reporter.phase("using cached transcript")
            return cached

    reporter.phase("fetching metadata")
    info = fetch.get_info(url)
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
    result = None if force_whisper else fetch.extract_captions(info, args.lang)
    if result:
        transcript, source, lang, segments = result
    elif args.whisper or force_whisper:
        reporter.phase(f"transcribing with Whisper ({args.whisper_model})")
        transcript, segments = fetch.whisper_transcribe(url, args.whisper_model)
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


def _validate_result(task: str, text: str) -> None:
    if not text.strip():
        raise summarize.SummarizeError("Writer returned empty Markdown")
    if task == "summary":
        missing = [
            label
            for label in ("TL;DR", "Key takeaways")
            if label.lower() not in text.lower()
        ]
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
    task = task or ("summary" if user_prompt == DEFAULT_PROMPT else "custom")
    record = _get_record(url, args, reporter)
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
    _validate_result(task, summary)
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


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
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
        task, user_prompt = _load_task(args, settings)
        writer = summarize.resolve_writer(args.writer, args.claude_bin, args.codex_bin)
        writer_command = args.codex_bin if writer == "codex" else args.claude_bin
        summarize.ensure_writer_compatible(writer, writer_command)
        summarize.ensure_writer_authenticated(writer, writer_command)
        raw_inputs = args.inputs
        if not raw_inputs and not sys.stdin.isatty():
            raw_inputs = [
                line.strip()
                for line in sys.stdin
                if line.strip() and not line.lstrip().startswith("#")
            ]
        urls = resolve_inputs(raw_inputs)
        if not urls:
            raise YtsError(
                "No videos resolved. Pass a YouTube URL, ID, playlist, or file."
            )
    except (YtsError, ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    reporter = ProgressReporter(args.quiet or args.stdout or args.json)
    results: list[dict] = []
    output_paths: list[str] = []
    with reporter:
        reporter.start_batch(len(urls))
        for index, url in enumerate(urls, 1):
            reporter.start_video(index, len(urls), url)
            try:
                status, path = process_one(
                    url, args, user_prompt, writer, reporter, task=task
                )
                reporter.finish_video(status)
                results.append(
                    {"url": url, "status": "ok", "message": status, "path": path}
                )
                output_paths.append(path)
                if args.stdout and not args.json:
                    print(output.read_generated_content(path))
            except Exception as exc:  # isolate per-video failures
                message = f"{type(exc).__name__}: {exc}" if args.verbose else str(exc)
                reporter.error(f"ERROR ({url}): {message}")
                reporter.finish_video("failed")
                results.append(
                    {
                        "url": url,
                        "status": "failed",
                        "error": message,
                        "retry": f"yts {shlex.quote(url)}",
                    }
                )
            if args.sleep and index < len(urls):
                time.sleep(args.sleep)

    failed = sum(item["status"] == "failed" for item in results)
    report = {
        "task": task,
        "writer": writer,
        "succeeded": len(results) - failed,
        "failed": failed,
        "results": results,
    }
    report_path = args.report
    if not report_path and len(urls) > 1:
        report_path = os.path.join(args.out_dir, "last-run.json")
    if report_path:
        _write_report(report_path, report)
    if args.open:
        for path in output_paths:
            webbrowser.open(Path(path).resolve().as_uri())
    if args.json:
        print(json.dumps(report, ensure_ascii=False))
    elif len(urls) == 1 and output_paths and not (args.quiet or args.stdout):
        print(Path(output_paths[0]).read_text(encoding="utf-8").rstrip())
    return 2 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

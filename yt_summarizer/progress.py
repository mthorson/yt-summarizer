"""Console output for batch runs.

Design goals:

* One live status line while work is happening (spinner, ``[i/n]``, video
  title, current step, elapsed time). It disappears when the run ends.
* Exactly one permanent line per video: summarized, skipped, or failed.
* Library chatter (yt-dlp warnings, Python warnings, third-party logging) is
  hidden unless ``--verbose`` is set, and never draws over the status line.

When stderr is not a terminal (piped or redirected) the live line is dropped
and plain ASCII lines are printed instead.
"""

from __future__ import annotations

import contextlib
import logging
import sys
import time

from rich.console import Console
from rich.markup import escape
from rich.progress import Progress, SpinnerColumn, TaskID, TextColumn, TimeElapsedColumn

_ASCII = str.maketrans({"·": "-", "→": "->", "…": "...", "✓": "ok", "✗": "x"})


def _print_plain(msg: str) -> None:
    """Print to stderr without crashing or mangling on legacy code pages."""
    text = msg.translate(_ASCII)
    encoding = getattr(sys.stderr, "encoding", None) or "utf-8"
    text = text.encode(encoding, errors="replace").decode(encoding, errors="replace")
    print(text, file=sys.stderr, flush=True)


def _short(text: str, limit: int = 60) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def format_duration(seconds: float) -> str:
    seconds = int(round(seconds))
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h{minutes:02d}m"
    if minutes:
        return f"{minutes}m{secs:02d}s"
    return f"{secs}s"


class ProgressReporter:
    """Report batch progress. Safe to use with ``quiet=True`` in tests."""

    def __init__(self, quiet: bool = False, verbose: bool = False):
        self.quiet = quiet
        self.verbose = verbose
        self._rich = (not quiet) and sys.stderr.isatty()
        self._console: Console | None = Console(stderr=True) if self._rich else None
        self._progress: Progress | None = None
        self._task: TaskID | None = None
        self._index = 0
        self._total = 0
        self._label = ""
        self._phase = ""
        self._video_started = time.monotonic()
        self._seen_warnings: set[str] = set()

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    def __enter__(self) -> ProgressReporter:
        if self._rich and self._console:
            self._progress = Progress(
                SpinnerColumn(),
                TextColumn("{task.description}"),
                TimeElapsedColumn(),
                console=self._console,
                transient=True,
            )
            self._progress.__enter__()
            self._task = self._progress.add_task("starting", total=None)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._progress:
            self._progress.__exit__(exc_type, exc, tb)
            self._progress = None

    # ------------------------------------------------------------------ #
    # Live status line
    # ------------------------------------------------------------------ #
    def _refresh(self) -> None:
        if not (self._progress and self._task is not None):
            return
        parts = []
        if self._total:
            parts.append(f"[dim][{self._index}/{self._total}][/]")
        if self._label:
            parts.append(f"[bold]{escape(_short(self._label))}[/]")
        if self._phase:
            sep = "[dim]·[/] " if self._label else ""
            parts.append(f"{sep}{escape(self._phase)}")
        self._progress.update(self._task, description=" ".join(parts))

    def start_batch(self, total: int) -> None:
        self._total = total

    def start_video(self, index: int, total: int, url: str) -> None:
        self._index, self._total = index, total
        self._label, self._phase = url, "starting"
        self._video_started = time.monotonic()
        self._seen_warnings.clear()
        if self._progress and self._task is not None:
            self._progress.reset(self._task)
        self._refresh()
        if self.verbose and not self._rich:
            self._plain(f"[{index}/{total}] {url}")

    def set_title(self, title: str) -> None:
        if title:
            self._label = title
            self._refresh()

    def phase(self, msg: str) -> None:
        self._phase = msg
        self._refresh()
        if self.verbose and not self._rich:
            self._plain(f"    {msg}")

    # ------------------------------------------------------------------ #
    # Permanent lines
    # ------------------------------------------------------------------ #
    def _plain(self, msg: str) -> None:
        if not self.quiet:
            _print_plain(msg)

    def _prefix(self) -> str:
        return f"[{self._index}/{self._total}] " if self._total > 1 else ""

    def _elapsed(self) -> str:
        return format_duration(time.monotonic() - self._video_started)

    def log(self, msg: str, style: str = "") -> None:
        """Print a permanent informational line (hidden when quiet)."""
        if self.quiet:
            return
        if self._console:
            text = escape(msg)
            self._console.print(f"[{style}]{text}[/]" if style else text)
        else:
            self._plain(msg)

    def succeeded(self, label: str, detail: str) -> None:
        if self.quiet:
            return
        title = _short(label or self._label, 70)
        if self._console:
            self._console.print(
                f"[green]✓[/] [dim]{self._prefix()}[/]{escape(title)} "
                f"[dim]→ {escape(detail)} ({self._elapsed()})[/]"
            )
        else:
            self._plain(f"ok   {self._prefix()}{title} -> {detail} ({self._elapsed()})")

    def skipped(self, label: str, detail: str) -> None:
        if self.quiet:
            return
        title = _short(label or self._label, 70)
        if self._console:
            self._console.print(
                f"[yellow]↷[/] [dim]{self._prefix()}[/]{escape(title)} "
                f"[dim]already up to date → {escape(detail)}[/]"
            )
        else:
            self._plain(f"skip {self._prefix()}{title} -> {detail} (up to date)")

    def failed(self, message: str, hint: str | None = None) -> None:
        """Failures are always shown, even with --quiet."""
        title = _short(self._label, 70)
        if self._console:
            self._console.print(
                f"[red]✗[/] [dim]{self._prefix()}[/]{escape(title)}\n"
                f"  [red]{escape(message)}[/]"
                + (f"\n  [cyan]hint:[/] {escape(hint)}" if hint else "")
            )
        else:
            _print_plain(f"FAIL {self._prefix()}{title}")
            _print_plain(f"     {message}")
            if hint:
                _print_plain(f"     hint: {hint}")

    def warning(self, msg: str) -> None:
        """Library warnings: shown once per video, only with --verbose."""
        if not self.verbose or self.quiet or msg in self._seen_warnings:
            return
        self._seen_warnings.add(msg)
        if self._console:
            self._console.print(f"  [yellow dim]! {escape(_short(msg, 200))}[/]")
        else:
            self._plain(f"     warning: {msg}")

    def error(self, msg: str) -> None:
        if self._console:
            self._console.print(f"[red]{escape(msg)}[/]")
        else:
            _print_plain(msg)

    # Kept for API compatibility with earlier versions.
    def finish_video(self, status: str) -> None:
        if self.verbose and not self._rich:
            self._plain(f"    {status}")


class ReporterLogHandler(logging.Handler):
    """Send WARNING+ log records from any library to the reporter."""

    def __init__(self, reporter: ProgressReporter):
        super().__init__(level=logging.WARNING)
        self.reporter = reporter

    def emit(self, record: logging.LogRecord) -> None:
        # Logging must never crash a run.
        with contextlib.suppress(Exception):
            self.reporter.warning(record.getMessage())

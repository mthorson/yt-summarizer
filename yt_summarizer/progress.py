"""Progress reporting helpers."""

from __future__ import annotations

import sys

from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
)


class ProgressReporter:
    """Report batch progress with Rich when stderr is interactive."""

    def __init__(self, quiet: bool = False):
        self.quiet = quiet
        self._rich = (not quiet) and sys.stderr.isatty()
        self._console: Console | None = None
        self._progress: Progress | None = None
        self._overall: TaskID | None = None
        self._current: TaskID | None = None

    def __enter__(self) -> ProgressReporter:
        if self._rich:
            self._console = Console(stderr=True)
            self._progress = Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                MofNCompleteColumn(),
                TimeElapsedColumn(),
                console=self._console,
            )
            self._progress.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._progress:
            self._progress.__exit__(exc_type, exc, tb)

    def log(self, msg: str) -> None:
        if self.quiet:
            return
        if self._rich and self._console:
            self._console.print(msg)
        else:
            print(msg, file=sys.stderr, flush=True)

    def error(self, msg: str) -> None:
        print(msg, file=sys.stderr, flush=True)

    def start_batch(self, total: int) -> None:
        if self._progress:
            self._overall = self._progress.add_task("videos", total=total)
            self._current = self._progress.add_task("waiting", total=None)
        else:
            self.log(f"{total} video(s) to process.\n")

    def start_video(self, index: int, total: int, url: str) -> None:
        if self._progress and self._current is not None:
            self._progress.update(
                self._current, description=f"[{index}/{total}] resolving {url}"
            )
        else:
            self.log(f"[{index}/{total}] {url}")

    def phase(self, msg: str) -> None:
        if self._progress and self._current is not None:
            self._progress.update(self._current, description=msg)
        else:
            self.log(f"    {msg}")

    def finish_video(self, status: str) -> None:
        if self._progress:
            if self._current is not None:
                self._progress.update(self._current, description=status)
            if self._overall is not None:
                self._progress.advance(self._overall)
        else:
            self.log(f"    {status}")

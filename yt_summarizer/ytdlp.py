"""Shared yt-dlp setup.

yt-dlp normally writes warnings and errors straight to stderr, which tears
through the live progress display. Every YoutubeDL instance in this package is
built from :func:`options`, which routes its output through the standard
``logging`` module instead. The CLI decides what (if anything) to show.
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache

from .runtimes import javascript_runtimes

log = logging.getLogger("yt_summarizer.yt_dlp")

_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def clean_message(message: str) -> str:
    """Strip colour codes and yt-dlp's ``ERROR:``/``WARNING:`` prefixes."""
    text = _ANSI.sub("", str(message)).strip()
    return re.sub(r"^(ERROR|WARNING):\s*", "", text)


class _Logger:
    def debug(self, msg: str) -> None:
        log.debug(clean_message(msg))

    info = debug

    def warning(self, msg: str) -> None:
        log.warning(clean_message(msg))

    def error(self, msg: str) -> None:
        # The DownloadError raised right after carries the same text, and the
        # CLI reports that once. Logging it here as well would duplicate it.
        log.debug(clean_message(msg))


_LOGGER = _Logger()


@lru_cache(maxsize=1)
def _runtimes() -> dict:
    return javascript_runtimes()


def options(user_opts: dict | None = None, **task_opts) -> dict:
    """Build YoutubeDL params: defaults < user options < task options < output."""
    return {
        "js_runtimes": _runtimes(),
        "socket_timeout": 30,
        **(user_opts or {}),
        **task_opts,
        "logger": _LOGGER,
        "quiet": True,
        "no_warnings": False,
        "noprogress": True,
        "color": "no_color",
    }

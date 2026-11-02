# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and releases follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `-sl` / `--summary-lang` (and `summary_language` in the config file) to write
  summaries in any language, independent of the caption language. Common
  languages get localized summary headings.
- YouTube cookies via `--cookies FILE` or `--cookies-from-browser BROWSER`.
- `--whisper-device auto|cuda|cpu` and an optional `windows-gpu` extra with the
  NVIDIA runtime DLLs for Windows.
- Whisper progress (download, model load, percent transcribed) in the status line.

### Changed

- Reworked console output: one live status line plus one result line per video
  and a final summary. yt-dlp and library warnings no longer draw over the
  progress display; they are shown only with `-v`.
- Common YouTube failures (bot check, members-only, private, rate limits,
  network errors) are reported as one short message with a hint.
- Writer subprocess I/O is UTF-8 on every platform.

## [0.1.1] - 2026-10-12

### Fixed

- Keep PyAV below version 19 to prevent local Whisper transcription from failing
  with `open() got an unexpected keyword argument 'metadata_errors'`.
- Prefer original-language captions over translations of dubbed audio tracks.

### Added

- Audio-decoding regression coverage using the installed Whisper dependencies.

## [0.1.0] - 2026-07-28

### Added

- Codex and Claude CLI writer support, with Codex as the default.
- Timestamped transcripts and YouTube verification links.
- Resumable long-video chunking.
- Summary, actions, claims, critique, and custom prompt tasks.
- TOML configuration and platform-native storage directories.
- Provenance-aware Markdown output and atomic writes.
- JSON batch reports, stdin input, stdout mode, and retry commands.
- Unit tests, coverage enforcement, linting, formatting, and type checking.
- Linux and Windows CI across Python 3.10 through 3.13.
- Writer capability checks in `yts --doctor`.
- Tagged GitHub release automation with SHA-256 checksums.
- Whisper is now an explicitly installed optional dependency.

[Unreleased]: https://github.com/talha-devp/yt-summarizer/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/mthorson/yt-summarizer/releases/tag/v0.1.1
[0.1.0]: https://github.com/mthorson/yt-summarizer/releases/tag/v0.1.0

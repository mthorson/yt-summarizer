# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and releases follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/mthorson/yt-summarizer/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/mthorson/yt-summarizer/releases/tag/v0.1.0

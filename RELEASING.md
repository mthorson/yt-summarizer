# Releasing yt-summarizer

1. Update `CHANGELOG.md`, moving relevant entries out of `Unreleased`.
2. Set the same version in `pyproject.toml` and `yt_summarizer/__init__.py`.
3. Refresh and verify the lockfile:

   ```sh
   uv lock --check
   uv sync --group dev
   ```

4. Run the complete local gate:

   ```sh
   uv run ruff check .
   uv run ruff format --check .
   uv run mypy yt_summarizer
   uv run coverage run -m unittest discover -s tests -v
   uv run coverage report
   uv build
   ```

5. Commit the release changes.
6. Create and push a signed tag matching the package version:

   ```sh
   git tag -s v0.1.0 -m "yt-summarizer 0.1.0"
   git push origin main v0.1.0
   ```

7. The release workflow verifies the version, reruns all quality gates, builds
   the wheel and source archive, writes `SHA256SUMS`, and creates a GitHub
   release containing all three artifacts.
8. Install the released wheel in a clean environment and run `yts --doctor`.

GitHub releases are the initial distribution channel. PyPI publishing should be
added later using trusted publishing rather than a long-lived API token.

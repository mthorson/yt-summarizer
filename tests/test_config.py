from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from yt_summarizer import config


class ConfigTest(unittest.TestCase):
    def test_loads_settings_and_presets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            path.write_text(
                'writer = "claude"\n[presets]\nactions = "Do things"\n',
                encoding="utf-8",
            )
            settings = config.load(path)
            self.assertEqual(settings["writer"], "claude")
            self.assertEqual(config.presets(settings), {"actions": "Do things"})

    def test_xdg_paths_are_stable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache_root = os.path.join(tmp, "cache-root")
            data_root = os.path.join(tmp, "data-root")
            with mock.patch.dict(
                os.environ,
                {"XDG_CACHE_HOME": cache_root, "XDG_DATA_HOME": data_root},
            ):
                self.assertEqual(
                    config.default_cache_dir(),
                    os.path.join(cache_root, "yt-summarizer"),
                )
                self.assertEqual(
                    config.default_output_dir(),
                    os.path.join(data_root, "yt-summarizer", "summaries"),
                )


if __name__ == "__main__":
    unittest.main()

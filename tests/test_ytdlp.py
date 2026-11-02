from __future__ import annotations

import unittest

from yt_summarizer import ytdlp


class YtDlpOptionsTest(unittest.TestCase):
    def test_output_settings_cannot_be_overridden(self) -> None:
        opts = ytdlp.options(
            {"cookiefile": "c.txt", "quiet": False}, format="bestaudio/best"
        )
        self.assertEqual(opts["cookiefile"], "c.txt")
        self.assertEqual(opts["format"], "bestaudio/best")
        self.assertTrue(opts["quiet"])
        self.assertTrue(opts["noprogress"])
        self.assertIs(opts["logger"], ytdlp._LOGGER)

    def test_warnings_are_logged_and_errors_are_not_duplicated(self) -> None:
        with self.assertLogs("yt_summarizer.yt_dlp", level="DEBUG") as captured:
            ytdlp._LOGGER.warning("\x1b[0;33mWARNING:\x1b[0m [youtube] slow")
            ytdlp._LOGGER.error("ERROR: broken")
        levels = [(r.levelname, r.getMessage()) for r in captured.records]
        self.assertEqual(levels, [("WARNING", "[youtube] slow"), ("DEBUG", "broken")])


if __name__ == "__main__":
    unittest.main()

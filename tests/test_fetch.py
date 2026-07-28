from __future__ import annotations

import json
import unittest

from yt_summarizer import fetch


class FetchTest(unittest.TestCase):
    def test_json3_preserves_timing(self) -> None:
        raw = json.dumps(
            {
                "events": [
                    {
                        "tStartMs": 1250,
                        "dDurationMs": 2000,
                        "segs": [{"utf8": "Hello "}, {"utf8": "world"}],
                    }
                ]
            }
        )
        segments = fetch._parse_json3_segments(raw)
        self.assertEqual(
            segments,
            [{"start": 1.25, "duration": 2.0, "text": "Hello world"}],
        )

    def test_vtt_removes_growing_auto_caption_duplicate(self) -> None:
        raw = """WEBVTT

00:00:01.000 --> 00:00:03.000
hello

00:00:02.000 --> 00:00:04.000
hello world
"""
        self.assertEqual(fetch._parse_vtt(raw), "hello world")
        self.assertEqual(fetch._parse_vtt_segments(raw)[0]["start"], 2.0)

    def test_language_variant_reports_actual_language(self) -> None:
        selected = fetch._pick_track({"en-US": [{"url": "x"}]}, "en")
        self.assertEqual(selected, ("en-US", [{"url": "x"}]))


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import unittest
from unittest import mock

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

    @mock.patch("yt_summarizer.fetch._fetch_url")
    def test_native_english_captions_precede_translation_of_dub(self, fetch_url):
        fetch_url.side_effect = lambda url: (
            json.dumps({"events": [{"segs": [{"utf8": "Native English"}]}]})
            if url == "native"
            else ""
        )
        info = {
            "automatic_captions": {
                "en": [{"ext": "json3", "url": "translated"}],
                "en-orig": [{"ext": "json3", "url": "native"}],
            }
        }
        result = fetch.extract_captions(info, "en")
        self.assertIsNotNone(result)
        self.assertEqual(result[:3], ("Native English", "auto-captions", "en-orig"))
        fetch_url.assert_called_once_with("native")

    def test_original_preference_still_accepts_plain_language(self):
        tracks = {"en": [{"url": "plain"}]}
        self.assertEqual(
            fetch._pick_track(tracks, "en", prefer_original=True),
            ("en", tracks["en"]),
        )

    @mock.patch("yt_summarizer.fetch._extract_from_track")
    def test_manual_captions_still_precede_native_auto_captions(self, extract):
        extract.return_value = ("Manual English", [])
        manual = [{"url": "manual"}]
        info = {
            "subtitles": {"en": manual},
            "automatic_captions": {"en-orig": [{"url": "native"}]},
        }
        self.assertEqual(
            fetch.extract_captions(info, "en"),
            ("Manual English", "captions", "en", []),
        )
        extract.assert_called_once_with(manual)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest
from unittest import mock

from yt_summarizer.inputs import resolve_inputs, video_id_from_url


class InputsTest(unittest.TestCase):
    @mock.patch("yt_summarizer.inputs.YoutubeDL")
    def test_playlist_expansion_uses_supplied_cookies(self, youtube_dl):
        ydl = youtube_dl.return_value.__enter__.return_value
        ydl.extract_info.return_value = {
            "_type": "playlist",
            "entries": [{"id": "dQw4w9WgXcQ"}],
        }
        result = resolve_inputs(
            ["https://www.youtube.com/playlist?list=example"],
            ydl_opts={"cookiefile": "youtube-cookies.txt"},
        )
        self.assertEqual(result, ["https://www.youtube.com/watch?v=dQw4w9WgXcQ"])
        self.assertEqual(
            youtube_dl.call_args.args[0]["cookiefile"], "youtube-cookies.txt"
        )

    def test_video_id_from_direct_urls(self) -> None:
        self.assertEqual(
            video_id_from_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
            "dQw4w9WgXcQ",
        )
        self.assertEqual(
            video_id_from_url("https://youtu.be/dQw4w9WgXcQ?t=1"),
            "dQw4w9WgXcQ",
        )
        self.assertEqual(
            video_id_from_url("https://www.youtube.com/shorts/dQw4w9WgXcQ"),
            "dQw4w9WgXcQ",
        )

    def test_watch_url_with_playlist_param_stays_single_video(self) -> None:
        resolved = resolve_inputs(
            [
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLMC9KNkIncKtPzgY-5rmhvj7fax8fdxoj"
            ]
        )
        self.assertEqual(
            resolved,
            ["https://www.youtube.com/watch?v=dQw4w9WgXcQ"],
        )


if __name__ == "__main__":
    unittest.main()

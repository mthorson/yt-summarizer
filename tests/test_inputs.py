from __future__ import annotations

import unittest

from yt_summarizer.inputs import resolve_inputs, video_id_from_url


class InputsTest(unittest.TestCase):
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

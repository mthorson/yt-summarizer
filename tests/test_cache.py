from __future__ import annotations

import tempfile
import unittest

from yt_summarizer import cache


class CacheTest(unittest.TestCase):
    def test_find_survives_channel_rename(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            record = {"video_id": "dQw4w9WgXcQ", "transcript": "text"}
            cache.save(tmp, "Old Channel", record)
            self.assertEqual(cache.find(tmp, record["video_id"]), record)

    def test_chunk_results_round_trip_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache.save_chunk_result(tmp, "video", "fingerprint", ["one", "two"])
            self.assertEqual(
                cache.load_chunk_result(tmp, "video", "fingerprint"),
                ["one", "two"],
            )


if __name__ == "__main__":
    unittest.main()

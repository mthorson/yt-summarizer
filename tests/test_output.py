from __future__ import annotations

import os
import tempfile
import unittest

from yt_summarizer.output import (
    find_existing_summary,
    read_front_matter,
    read_generated_content,
    relative_summary_path,
    sanitize_channel,
    write_summary,
)


class OutputTest(unittest.TestCase):
    def test_channel_name_is_portable_to_windows(self) -> None:
        self.assertEqual(sanitize_channel("CON"), "_CON")
        self.assertEqual(sanitize_channel("Channel. "), "Channel")

    def test_find_existing_summary_by_video_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            channel_dir = os.path.join(tmp, "Channel")
            os.makedirs(channel_dir)
            path = os.path.join(channel_dir, "dQw4w9WgXcQ-never-gonna.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write("summary")

            self.assertEqual(find_existing_summary(tmp, "dQw4w9WgXcQ"), path)
            self.assertIsNone(find_existing_summary(tmp, "aaaaaaaaaaa"))

    def test_relative_summary_path(self) -> None:
        path = os.path.join("summaries", "Channel", "video.md")
        self.assertEqual(
            relative_summary_path("summaries", path),
            os.path.join("Channel", "video.md"),
        )

    def test_write_summary_is_provenance_aware(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            record = {
                "video_id": "dQw4w9WgXcQ",
                "title": "Title",
                "channel": "Channel",
                "webpage_url": "https://youtu.be/dQw4w9WgXcQ",
                "transcript_source": "captions",
                "transcript_lang": "en",
            }
            path = write_summary(
                tmp,
                "Channel",
                record,
                "Body",
                "codex:default",
                task="actions",
                provenance={"prompt_hash": "abc", "transcript_hash": "def"},
            )
            self.assertTrue(path.endswith("--actions.md"))
            self.assertEqual(read_front_matter(path)["prompt_hash"], "abc")
            self.assertEqual(read_generated_content(path), "Body")
            self.assertEqual(
                find_existing_summary(
                    tmp,
                    record["video_id"],
                    task="actions",
                    expected={"prompt_hash": "abc"},
                ),
                path,
            )
            self.assertIsNone(
                find_existing_summary(
                    tmp,
                    record["video_id"],
                    task="actions",
                    expected={"prompt_hash": "different"},
                )
            )


if __name__ == "__main__":
    unittest.main()

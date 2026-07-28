from __future__ import annotations

import unittest
from unittest import mock

from yt_summarizer import fetch


class WhisperTest(unittest.TestCase):
    @mock.patch("yt_summarizer.fetch.os.path.isfile", return_value=True)
    @mock.patch("yt_summarizer.fetch.YoutubeDL")
    @mock.patch("yt_summarizer.fetch._ensure_whisper_model")
    def test_cuda_runtime_failure_falls_back_to_cpu(
        self, ensure_model, youtube_dl, _isfile
    ) -> None:
        segment = mock.Mock(start=0.0, end=1.0, text="hello")
        model = mock.Mock()
        model.return_value.transcribe.side_effect = [
            RuntimeError("libcublas.so.12 not found"),
            ([segment], None),
        ]
        ensure_model.return_value = model
        ydl = youtube_dl.return_value.__enter__.return_value
        ydl.extract_info.return_value = {"id": "video"}
        ydl.prepare_filename.return_value = "/tmp/audio.webm"

        text, timed = fetch.whisper_transcribe("url", "tiny")

        self.assertEqual(text, "hello")
        self.assertEqual(timed[0]["duration"], 1.0)
        self.assertEqual(model.call_args_list[1].kwargs["device"], "cpu")


if __name__ == "__main__":
    unittest.main()

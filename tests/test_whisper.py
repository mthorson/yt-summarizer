from __future__ import annotations

import importlib.util
import tempfile
import unittest
import wave
from unittest import mock

from yt_summarizer import fetch


class WhisperTest(unittest.TestCase):
    @unittest.skipUnless(
        importlib.util.find_spec("faster_whisper"), "Whisper extra is not installed"
    )
    def test_whisper_decodes_audio_with_installed_dependencies(self) -> None:
        from faster_whisper.audio import decode_audio

        with tempfile.TemporaryDirectory() as tmp:
            audio_path = f"{tmp}/silence.wav"
            with wave.open(audio_path, "wb") as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(16000)
                audio.writeframes(b"\x00\x00" * 16000)
            samples = decode_audio(audio_path)

        self.assertEqual(len(samples), 16000)
        self.assertTrue((samples == 0).all())

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

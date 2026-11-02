from __future__ import annotations

import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from yt_summarizer import cli
from yt_summarizer.progress import ProgressReporter
from yt_summarizer.prompts import CUSTOM_SYSTEM_PROMPT, DEFAULT_PROMPT


def _args(tmp: str) -> SimpleNamespace:
    return SimpleNamespace(
        cache_dir=os.path.join(tmp, "cache"),
        out_dir=os.path.join(tmp, "summaries"),
        force=False,
        refetch=False,
        lang="en",
        whisper=False,
        whisper_model="base",
        model="auto",
        long_threshold=45000,
        timeout=600,
        claude_bin="claude",
        codex_bin="codex",
    )


class CliTest(unittest.TestCase):
    def test_codex_is_the_default_writer(self) -> None:
        args = cli.build_parser().parse_args([])
        self.assertEqual(args.writer, "codex")

    def test_short_flags_parse_like_long_flags(self) -> None:
        args = cli.build_parser().parse_args(
            [
                "-c",
                "my-cache",
                "-o",
                "my-summaries",
                "-p",
                "Custom prompt",
                "-w",
                "codex",
                "-m",
                "gpt-5.4",
                "-T",
                "123",
                "-l",
                "es",
                "-W",
                "-M",
                "small",
                "-f",
                "-r",
                "-s",
                "1.5",
                "-t",
                "42",
                "-q",
                "https://youtu.be/dQw4w9WgXcQ",
            ]
        )

        self.assertEqual(args.cache_dir, "my-cache")
        self.assertEqual(args.out_dir, "my-summaries")
        self.assertEqual(args.prompt, "Custom prompt")
        self.assertEqual(args.writer, "codex")
        self.assertEqual(args.model, "gpt-5.4")
        self.assertEqual(args.long_threshold, 123)
        self.assertEqual(args.lang, "es")
        self.assertTrue(args.whisper)
        self.assertEqual(args.whisper_model, "small")
        self.assertTrue(args.force)
        self.assertTrue(args.refetch)
        self.assertEqual(args.sleep, 1.5)
        self.assertEqual(args.timeout, 42)
        self.assertTrue(args.quiet)
        self.assertEqual(args.inputs, ["https://youtu.be/dQw4w9WgXcQ"])

    def test_doctor_short_flag(self) -> None:
        args = cli.build_parser().parse_args(["-d"])
        self.assertTrue(args.doctor)

    def test_browser_cookies_reach_metadata_captions_and_whisper(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            args = _args(tmp)
            args.cookies_from_browser = "firefox"
            args.whisper_device = "cuda"
            args.whisper = True
            url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
            info = {"id": "dQw4w9WgXcQ", "channel": "Channel"}
            with (
                mock.patch(
                    "yt_summarizer.cli.fetch.get_info", return_value=info
                ) as meta,
                mock.patch(
                    "yt_summarizer.cli.fetch.extract_captions", return_value=None
                ) as captions,
                mock.patch(
                    "yt_summarizer.cli.fetch.whisper_transcribe",
                    return_value=("Türkçe konuşma", []),
                ) as whisper,
            ):
                record = cli._get_record(url, args, ProgressReporter(quiet=True))
            options = {"cookiesfrombrowser": ("firefox",)}
            meta.assert_called_once_with(url, ydl_opts=options)
            captions.assert_called_once_with(info, "en", ydl_opts=options)
            whisper.assert_called_once_with(
                url,
                "base",
                device="cuda",
                ydl_opts=options,
                on_progress=mock.ANY,
            )
            self.assertEqual(record["transcript"], "Türkçe konuşma")

    def test_missing_cookie_file_fails_before_starting_a_writer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch("yt_summarizer.cli.summarize.resolve_writer") as writer:
                result = cli.main(["--cookies", os.path.join(tmp, "missing.txt")])
            self.assertEqual(result, 1)
            writer.assert_not_called()

    def test_long_video_chunk_notes_resume_from_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            args = _args(tmp)
            args.chunk_tokens = 250
            args.no_chunk = False
            record = {
                "video_id": "dQw4w9WgXcQ",
                "title": "Long",
                "channel": "Channel",
                "webpage_url": "https://youtu.be/dQw4w9WgXcQ",
                "transcript": "x" * 1100 + " " + "y" * 1100,
                "segments": [
                    {"start": 0, "duration": 1, "text": "x" * 1100},
                    {"start": 1, "duration": 1, "text": "y" * 1100},
                ],
            }
            reporter = ProgressReporter(quiet=True)
            with mock.patch(
                "yt_summarizer.summarize.summarize",
                side_effect=["chunk one", "chunk two", "final one"],
            ) as writer:
                result = cli._summarize_record(
                    record, args, "Prompt", "codex", None, reporter
                )
            self.assertEqual(result, "final one")
            self.assertEqual(writer.call_count, 3)

            with mock.patch(
                "yt_summarizer.summarize.summarize", return_value="final two"
            ) as writer:
                result = cli._summarize_record(
                    record, args, "Prompt", "codex", None, reporter
                )
            self.assertEqual(result, "final two")
            writer.assert_called_once()

    def test_batch_report_contains_retry_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = os.path.join(tmp, "report.json")
            with (
                mock.patch(
                    "yt_summarizer.cli.resolve_inputs",
                    return_value=["https://youtu.be/aaaaaaaaaaa", "bad url"],
                ) as resolve,
                mock.patch(
                    "yt_summarizer.cli.summarize.resolve_writer", return_value="codex"
                ),
                mock.patch("yt_summarizer.cli.summarize.ensure_writer_compatible"),
                mock.patch("yt_summarizer.cli.summarize.ensure_writer_authenticated"),
                mock.patch(
                    "yt_summarizer.cli.process_one",
                    side_effect=[
                        ("summarized", os.path.join(tmp, "one.md")),
                        RuntimeError("quota"),
                    ],
                ),
            ):
                result = cli.main(
                    [
                        "--quiet",
                        "--report",
                        report,
                        "--cookies-from-browser",
                        "firefox",
                        "playlist",
                    ]
                )

            self.assertEqual(result, 2)
            resolve.assert_called_once_with(
                ["playlist"], ydl_opts={"cookiesfrombrowser": ("firefox",)}
            )
            with open(report, encoding="utf-8") as handle:
                data = json.load(handle)
            self.assertEqual(data["succeeded"], 1)
            self.assertEqual(data["failed"], 1)
            self.assertEqual(data["results"][1]["retry"], "yts 'bad url'")

    def test_legacy_summary_without_provenance_is_regenerated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            args = _args(tmp)
            channel_dir = os.path.join(args.out_dir, "Channel")
            os.makedirs(channel_dir)
            path = os.path.join(channel_dir, "dQw4w9WgXcQ-existing.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write("existing")

            record = {
                "video_id": "dQw4w9WgXcQ",
                "title": "New Title",
                "channel": "Channel",
                "duration": 60,
                "upload_date": "20260101",
                "webpage_url": "https://youtu.be/dQw4w9WgXcQ",
                "transcript": "Transcript",
                "transcript_source": "captions",
            }
            with (
                mock.patch(
                    "yt_summarizer.cli._get_record", return_value=record
                ) as get_record,
                mock.patch(
                    "yt_summarizer.summarize.summarize",
                    return_value="**TL;DR**: New.\n\n**Key takeaways**\n- One.",
                ),
            ):
                status, returned_path = cli.process_one(
                    "https://youtu.be/dQw4w9WgXcQ",
                    args,
                    DEFAULT_PROMPT,
                    "claude",
                    ProgressReporter(quiet=True),
                )

            self.assertIn("summarized", status)
            self.assertNotEqual(returned_path, path)
            get_record.assert_called_once()

    def test_custom_prompt_regenerates_even_when_summary_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            args = _args(tmp)
            channel_dir = os.path.join(args.out_dir, "Channel")
            os.makedirs(channel_dir)
            existing = os.path.join(channel_dir, "dQw4w9WgXcQ-existing.md")
            with open(existing, "w", encoding="utf-8") as f:
                f.write("existing")

            record = {
                "video_id": "dQw4w9WgXcQ",
                "title": "New Title",
                "channel": "Channel",
                "duration": 60,
                "upload_date": "20260101",
                "webpage_url": "https://youtu.be/dQw4w9WgXcQ",
                "transcript": "Transcript",
                "transcript_source": "captions",
            }

            with (
                mock.patch("yt_summarizer.cli._get_record", return_value=record),
                mock.patch(
                    "yt_summarizer.summarize.summarize",
                    return_value="**TL;DR**: New\n\n**Key takeaways**\n- One",
                ) as summarize_mock,
            ):
                status, returned_path = cli.process_one(
                    "https://youtu.be/dQw4w9WgXcQ",
                    args,
                    "Custom prompt",
                    "claude",
                    ProgressReporter(quiet=True),
                )

            self.assertIn("summarized [claude:sonnet]", status)
            self.assertTrue(returned_path.endswith("dQw4w9WgXcQ-new-title--custom.md"))
            summarize_mock.assert_called_once()
            self.assertEqual(
                summarize_mock.call_args.kwargs["system_prompt"],
                CUSTOM_SYSTEM_PROMPT,
            )

    def test_summary_lang_flag_and_config(self) -> None:
        self.assertIsNone(cli.build_parser().parse_args([]).summary_lang)
        self.assertEqual(
            cli.build_parser().parse_args(["-sl", "tr"]).summary_lang, "tr"
        )
        self.assertEqual(
            cli.build_parser().parse_args(["--summary-lang", "de"]).summary_lang,
            "de",
        )
        configured = cli.build_parser({"summary_language": "tr"}).parse_args([])
        self.assertEqual(configured.summary_lang, "tr")
        # -sl must not collide with -s/--sleep.
        args = cli.build_parser().parse_args(["-s", "2", "-sl", "tr"])
        self.assertEqual((args.sleep, args.summary_lang), (2.0, "tr"))

    def test_localized_summary_prompt_and_validation(self) -> None:
        prompt = cli.localize_prompt(DEFAULT_PROMPT, "tr")
        self.assertIn("**Kısa Özet**", prompt)
        self.assertIn("Turkish", prompt)
        self.assertEqual(cli.localize_prompt(DEFAULT_PROMPT, None), DEFAULT_PROMPT)
        headings = cli.expected_headings("summary", prompt, "tr")
        self.assertEqual(headings, ("Kısa Özet", "Öne Çıkan Noktalar"))
        cli._validate_result(
            "summary", "**KISA ÖZET**: x\n\n**Öne çıkan noktalar**\n- y", headings
        )
        with self.assertRaises(cli.summarize.SummarizeError):
            cli._validate_result("summary", "**TL;DR**: x", headings)
        # Unknown languages translate headings themselves; no strict check.
        swahili = cli.localize_prompt(DEFAULT_PROMPT, "Swahili")
        self.assertIn("Translate the two headings", swahili)
        self.assertIsNone(cli.expected_headings("summary", swahili, "Swahili"))
        # Custom prompts only get the language instruction appended.
        custom = cli.localize_prompt("List the steps.", "tr")
        self.assertTrue(custom.startswith("List the steps."))
        self.assertIsNone(cli.expected_headings("custom", custom, "tr"))

    def test_turkish_summary_is_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            args = _args(tmp)
            args.summary_lang = "tr"
            record = {
                "video_id": "dQw4w9WgXcQ",
                "title": "Başlık",
                "channel": "Channel",
                "webpage_url": "https://youtu.be/dQw4w9WgXcQ",
                "transcript": "Transcript",
            }
            prompt = cli.localize_prompt(DEFAULT_PROMPT, "tr")
            reply = "**Kısa Özet**: Özet.\n\n**Öne Çıkan Noktalar**\n- Bir."
            with (
                mock.patch("yt_summarizer.cli._get_record", return_value=record),
                mock.patch(
                    "yt_summarizer.summarize.summarize", return_value=reply
                ) as writer,
            ):
                status, path = cli.process_one(
                    "https://youtu.be/dQw4w9WgXcQ",
                    args,
                    prompt,
                    "claude",
                    ProgressReporter(quiet=True),
                )
            self.assertIn("summarized", status)
            self.assertTrue(path.endswith(".md"))
            self.assertNotIn("--custom", path)
            self.assertIn("Turkish", writer.call_args.kwargs["user_prompt"])

    def test_describe_error_gives_short_message_and_hint(self) -> None:
        exc = cli.DownloadError(
            "ERROR: [youtube] abc: Sign in to confirm you're not a bot. "
            "Use --cookies-from-browser or --cookies for the authentication."
        )
        message, hint = cli.describe_error(exc)
        self.assertEqual(message, "YouTube asked for a sign-in (bot check).")
        self.assertIn("--cookies", hint)
        message, hint = cli.describe_error(RuntimeError("x" * 1000))
        self.assertLess(len(message), 400)
        self.assertIsNone(hint)
        message, _ = cli.describe_error(cli.summarize.SummarizeError("quota"))
        self.assertEqual(message, "quota")


if __name__ == "__main__":
    unittest.main()

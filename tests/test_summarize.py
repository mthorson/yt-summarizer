from __future__ import annotations

import subprocess
import unittest
from unittest import mock

from yt_summarizer import summarize
from yt_summarizer.prompts import SALES_INTENT_INSTRUCTION


class SummarizeTest(unittest.TestCase):
    @mock.patch("yt_summarizer.summarize.subprocess.run")
    def test_writer_capability_check_reports_missing_flags(self, run) -> None:
        run.return_value = subprocess.CompletedProcess(
            args=["codex"], returncode=0, stdout="--sandbox", stderr=""
        )
        compatible, detail = summarize.writer_capabilities("codex", "codex")
        self.assertFalse(compatible)
        self.assertIn("--ephemeral", detail)

    @mock.patch("yt_summarizer.summarize.subprocess.run")
    def test_writer_capability_check_accepts_complete_help(self, run) -> None:
        flags = " ".join(summarize._WRITER_FLAGS["codex"])
        run.return_value = subprocess.CompletedProcess(
            args=["codex"], returncode=0, stdout=flags, stderr=""
        )
        self.assertEqual(
            summarize.writer_capabilities("codex", "codex"),
            (True, "compatible"),
        )

    @mock.patch("yt_summarizer.summarize.subprocess.run")
    def test_claude_authentication_reads_json(self, run) -> None:
        run.return_value = subprocess.CompletedProcess(
            args=["claude"],
            returncode=0,
            stdout='{"loggedIn": true, "authMethod": "oauth"}',
            stderr="",
        )
        self.assertEqual(
            summarize.writer_authentication("claude", "claude"),
            (True, "authenticated (oauth)"),
        )

    @mock.patch("yt_summarizer.summarize.subprocess.run")
    def test_codex_authentication_ignores_warnings(self, run) -> None:
        run.return_value = subprocess.CompletedProcess(
            args=["codex"],
            returncode=0,
            stdout="Logged in using ChatGPT",
            stderr="warning",
        )
        self.assertEqual(
            summarize.writer_authentication("codex", "codex"),
            (True, "authenticated"),
        )

    @mock.patch(
        "yt_summarizer.summarize.writer_authentication",
        return_value=(False, "not authenticated"),
    )
    def test_authentication_failure_includes_login_command(
        self, _authentication
    ) -> None:
        with self.assertRaisesRegex(summarize.SummarizeError, "claude.*sign in"):
            summarize.ensure_writer_authenticated("claude", "claude")

    @mock.patch("yt_summarizer.summarize._command_exists")
    def test_auto_writer_prefers_codex(self, command_exists) -> None:
        command_exists.return_value = True
        self.assertEqual(summarize.resolve_writer("auto"), "codex")
        command_exists.assert_called_once_with("codex")

    def test_choose_model_for_claude_auto(self) -> None:
        self.assertEqual(summarize.choose_model("x" * 100, "auto", 100), "sonnet")
        self.assertEqual(summarize.choose_model("x" * 1000, "auto", 100), "haiku")

    def test_choose_model_for_codex_auto_uses_cli_default(self) -> None:
        self.assertIsNone(
            summarize.choose_model("x" * 1000, "auto", 100, writer="codex")
        )
        self.assertEqual(
            summarize.choose_model("x" * 1000, "gpt-5.4", 100, writer="codex"),
            "gpt-5.4",
        )

    def test_claude_rejects_unknown_model(self) -> None:
        with self.assertRaises(summarize.SummarizeError):
            summarize.choose_model("x", "gpt-5.4", 100, writer="claude")

    def test_split_record_preserves_timed_segment_boundaries(self) -> None:
        record = {
            "transcript": "one two three",
            "segments": [
                {"start": 0, "duration": 1, "text": "x" * 700},
                {"start": 1, "duration": 1, "text": "y" * 700},
            ],
        }
        chunks = summarize.split_record(record, max_tokens=250)
        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[1]["segments"][0]["start"], 1)

    def test_split_record_can_overlap_short_segments(self) -> None:
        record = {
            "transcript": "one two three",
            "segments": [
                {"start": 0, "duration": 1, "text": "a" * 600},
                {"start": 1, "duration": 1, "text": "bridge"},
                {"start": 2, "duration": 1, "text": "b" * 600},
            ],
        }
        chunks = summarize.split_record(record, max_tokens=250, overlap_chars=20)
        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[1]["segments"][0]["text"], "bridge")

    def test_format_transcript_adds_timestamp_links(self) -> None:
        result = summarize.format_transcript(
            {
                "webpage_url": "https://youtu.be/dQw4w9WgXcQ",
                "segments": [{"start": 65, "duration": 2, "text": "Claim"}],
            }
        )
        self.assertIn("[1:05]", result)
        self.assertIn("?t=65s", result)

    @mock.patch("yt_summarizer.summarize.subprocess.run")
    def test_codex_writer_uses_noninteractive_ephemeral_command(self, run) -> None:
        run.return_value = subprocess.CompletedProcess(
            args=["codex"], returncode=0, stdout="summary\n", stderr=""
        )
        record = {
            "title": "Title",
            "channel": "Channel",
            "duration": 60,
            "webpage_url": "https://youtu.be/dQw4w9WgXcQ",
            "transcript": "Transcript text",
        }

        result = summarize.summarize(
            record,
            user_prompt="Summarize",
            system_prompt="System",
            model=None,
            writer="codex",
            codex_bin="codex-test",
        )

        self.assertEqual(result, "summary")
        cmd = run.call_args.args[0]
        self.assertEqual(cmd[:2], ["codex-test", "exec"])
        self.assertIn("--ephemeral", cmd)
        self.assertIn("--skip-git-repo-check", cmd)
        self.assertIn("--sandbox", cmd)
        self.assertIn("read-only", cmd)
        self.assertIn("--ignore-user-config", cmd)
        self.assertIn("--ignore-rules", cmd)
        self.assertEqual(cmd[-1], "-")
        self.assertIn("Transcript text", run.call_args.kwargs["input"])
        self.assertIn(SALES_INTENT_INSTRUCTION, run.call_args.kwargs["input"])

    @mock.patch("yt_summarizer.summarize.subprocess.run")
    def test_codex_failure_preserves_diagnostic(self, run) -> None:
        run.return_value = subprocess.CompletedProcess(
            args=["codex"], returncode=7, stdout="", stderr="not authenticated"
        )
        with self.assertRaisesRegex(summarize.SummarizeError, "not authenticated"):
            summarize.summarize(
                {"transcript": "text"},
                user_prompt="Summarize",
                system_prompt="System",
                model=None,
                writer="codex",
            )

    @mock.patch("yt_summarizer.summarize.subprocess.run")
    def test_claude_runs_isolated_with_tools_disabled(self, run) -> None:
        run.return_value = subprocess.CompletedProcess(
            args=["claude"], returncode=0, stdout="summary", stderr=""
        )
        summarize.summarize(
            {"transcript": "text"},
            user_prompt="Summarize",
            system_prompt="System",
            model="sonnet",
            writer="claude",
        )
        command = run.call_args.args[0]
        self.assertIn("--tools", command)
        self.assertEqual(command[command.index("--tools") + 1], "")
        self.assertIn("--no-session-persistence", command)
        self.assertIn("yt-summarizer-claude-", run.call_args.kwargs["cwd"])

    @mock.patch("yt_summarizer.summarize.subprocess.run")
    def test_writer_timeout_is_user_facing(self, run) -> None:
        run.side_effect = subprocess.TimeoutExpired(["codex"], 5)
        with self.assertRaisesRegex(summarize.SummarizeError, "timed out"):
            summarize.summarize(
                {"transcript": "text"},
                user_prompt="Summarize",
                system_prompt="System",
                model=None,
                writer="codex",
                timeout=5,
            )


if __name__ == "__main__":
    unittest.main()

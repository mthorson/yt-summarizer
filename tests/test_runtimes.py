from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from yt_summarizer.runtimes import javascript_runtimes


class RuntimeTest(unittest.TestCase):
    @mock.patch("yt_summarizer.runtimes.shutil.which", return_value=None)
    def test_winget_install_is_found_without_path_refresh(self, _which):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            executable = (
                root
                / "Microsoft"
                / "WinGet"
                / "Packages"
                / "DenoLand.Deno_test"
                / "deno.exe"
            )
            executable.parent.mkdir(parents=True)
            executable.touch()
            with (
                mock.patch.dict("os.environ", {"LOCALAPPDATA": tmp}),
                mock.patch("yt_summarizer.runtimes.Path.home", return_value=root),
            ):
                self.assertEqual(
                    javascript_runtimes()["deno"], {"path": str(executable)}
                )

    @mock.patch("yt_summarizer.runtimes.shutil.which", return_value="custom/deno")
    def test_path_install_takes_precedence(self, _which):
        self.assertEqual(javascript_runtimes()["deno"], {"path": "custom/deno"})

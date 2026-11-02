"""Locate JavaScript runtimes even when a terminal has an outdated PATH."""

from __future__ import annotations

import os
import shutil
from pathlib import Path


def javascript_runtimes() -> dict[str, dict[str, str]]:
    deno = shutil.which("deno")
    if not deno:
        executable = "deno.exe" if os.name == "nt" else "deno"
        candidates = [Path.home() / ".deno" / "bin" / executable]
        if local_appdata := os.environ.get("LOCALAPPDATA"):
            winget = Path(local_appdata) / "Microsoft" / "WinGet"
            candidates.append(winget / "Links" / "deno.exe")
            candidates.extend(
                sorted((winget / "Packages").glob("DenoLand.Deno_*/deno.exe"))
            )
        deno = next((str(path) for path in candidates if path.is_file()), None)
    return {"deno": {"path": deno} if deno else {}, "node": {}}

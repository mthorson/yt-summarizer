#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")"

uv tool install --force --editable .

cat <<'EOF'

Installed yt-summarizer as the `yts` command.

If your shell still says `yts: command not found`, run:
  uv tool update-shell

Then close and reopen your terminal.
EOF

# yt-summarizer

Turn YouTube videos into short Markdown summaries from the terminal.

## Why I built this

I watch a lot of long-form YouTube videos, but I do not always have an hour to
discover whether a video contains ten minutes of useful information. I wanted a
small tool that could turn a video into concrete, searchable notes while keeping
the original timestamps close enough that I could verify every important claim.

I also already pay for Codex and Claude. I did not want another API key, another
usage bill, or a web service holding my viewing history. I built `yt-summarizer`
to use the writer CLI I am already signed into, keep transcripts and results on
my computer, resume long jobs, and make the output useful in ordinary Markdown
tools. I am publishing it because this seems like a common problem, and a
transparent command-line tool is easier to trust, inspect, and adapt than a
closed summarization website.

`yt-summarizer` fetches YouTube metadata and captions with `yt-dlp`, asks a local
subscription-backed AI CLI to write the summary, then saves the result on your
computer. It supports Claude Code CLI and OpenAI Codex CLI, with the goal of
avoiding API keys and per-call API billing for normal personal use.

## What it does

- Summarizes one YouTube video, a playlist, or a text file full of video links.
- Uses captions when YouTube provides them.
- Can fall back to local Whisper transcription with `--whisper`.
- Preserves caption timestamps and adds verification links to YouTube.
- Splits long transcripts into resumable chunks before final synthesis.
- Saves provenance-aware Markdown without overwriting other task outputs.
- Uses stable per-user cache and output directories, configurable with TOML or flags.
- Shows batch progress and per-video stages while it works.
- Provides summary, action, claims, and critique presets.
- Notes when the video itself is trying to sell you something, separate from
  unrelated ads or sponsor segments.

## Usage

```text
yts [OPTIONS] INPUT...
```

`INPUT` can be a YouTube video URL, playlist URL, bare video ID, or a text file
containing one input per line.

| Option | What it does |
| --- | --- |
| `-w codex`, `--writer codex` | Use Codex CLI (default). |
| `-w auto`, `--writer auto` | Pick a writer; prefer Codex. |
| `-w claude`, `--writer claude` | Use Claude Code CLI. |
| `-d`, `--doctor` | Check whether writer CLIs are available. |
| `--preset actions` | Use a named built-in or configured task. |
| `--task NAME` | Give a custom prompt a stable output identity. |
| `--chunk-tokens 30000` | Bound long-video chunk size. |
| `--chunk-overlap 400` | Repeat context across chunk boundaries. |
| `--no-chunk` | Disable automatic long-video chunking. |
| `-W`, `--whisper` | Transcribe locally when captions are unavailable. |
| `--force-whisper` | Ignore captions and transcribe the audio locally. |
| `-M small`, `--whisper-model small` | Pick the faster-whisper model size. |
| `-m haiku`, `--model haiku` | Force a Claude model alias. |
| `-m gpt-5.4`, `--model gpt-5.4` | Select a Codex model. |
| `-m opus`, `--model opus` | Force Opus for higher quality. |
| `-T 45000`, `--long-threshold 45000` | Set the long-input threshold. |
| `-l en`, `--lang en` | Choose the preferred caption language. |
| `-f`, `--force` | Regenerate the summary even if the Markdown file exists. |
| `-r`, `--refetch` | Ignore cached transcript data and fetch again. |
| `-s 5`, `--sleep 5` | Pause between videos in a batch. |
| `-t 600`, `--timeout 600` | Per-video timeout for the writer CLI call. |
| `-c cache`, `--cache-dir cache` | Set the transcript cache directory. |
| `-o summaries`, `--out-dir summaries` | Set the output directory. |
| `-p "..."`, `--prompt "..."` | Replace the default summary instruction. |
| `-P prompt.txt`, `--prompt-file prompt.txt` | Load a prompt from a file. |
| `-q`, `--quiet` | Suppress progress and single-video stdout output. |
| `--stdout` | Print generated Markdown content only. |
| `--json` | Print a machine-readable run report. |
| `--report report.json` | Write a machine-readable batch/retry report. |
| `--open` | Open written summaries with the default desktop application. |
| `--config PATH` | Use another TOML configuration file. |

## Requirements

- Windows, macOS, or Linux.
- A signed-in Claude Code CLI or Codex CLI installation.
- `uv`, which installs and runs the Python package.
- Deno or Node.js 22+ on PATH for YouTube's JavaScript challenges. Both are
  enabled by `yts`; the matching solver scripts are installed with `yt-dlp`.
- Optional: enough disk space for audio downloads and Whisper models if you use
  `--whisper`.

## Install

### 1. Install uv

macOS and Linux:

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Windows PowerShell:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Close and reopen your terminal after installation so your shell can find `uv`.

### 2. Install and sign in to a writer CLI

Claude Code:

```sh
npm install -g @anthropic-ai/claude-code
claude
```

Follow the browser sign-in flow, then exit Claude Code once you are signed in.

If `npm` is not installed, install Node.js first from <https://nodejs.org>.

Codex:

```sh
codex login
```

Codex can sign in with ChatGPT for subscription-backed use. Avoid signing in
with an API key if your goal is to avoid API-based billing.

### 3. Install yt-summarizer

From GitHub:

```sh
uv tool install git+https://github.com/mthorson/yt-summarizer
```

From a local checkout:

```sh
git clone https://github.com/mthorson/yt-summarizer
cd yt-summarizer
./install.sh
```

Both install paths create a normal `yts` command. You should not need to type
`uv run yts` for everyday use.

If your shell cannot find `yts`, run:

```sh
uv tool update-shell
```

Then close and reopen your terminal.

Check what `yts` can see:

```sh
yts --doctor
```

The doctor checks executable versions, authentication, and every CLI option the
writer adapter depends on. It exits unsuccessfully when the selected writer is
missing, signed out, or incompatible, so it can also be used in setup scripts.

## Examples

Summarize one video:

```sh
yts "https://www.youtube.com/watch?v=SOME_VIDEO_ID"
```

For a single video, the summary is printed to stdout and written to your
configured output directory.

Summarize a playlist:

```sh
yts "https://www.youtube.com/playlist?list=SOME_PLAYLIST_ID"
```

Summarize a list of videos:

```sh
yts videos.txt
```

Where `videos.txt` contains one URL or video ID per line:

```txt
# Comments and blank lines are ignored.
https://www.youtube.com/watch?v=SOME_VIDEO_ID
https://youtu.be/ANOTHER_ID
```

Codex is used by default. Choose another writer or automatic fallback:

```sh
yts -w claude "https://www.youtube.com/watch?v=SOME_VIDEO_ID"
yts -w codex "https://www.youtube.com/watch?v=SOME_VIDEO_ID"
yts -w auto "https://www.youtube.com/watch?v=SOME_VIDEO_ID"
```

`--writer auto` uses Codex when available, then Claude.

Use a built-in task preset:

```sh
yts --preset actions "https://youtu.be/SOME_VIDEO_ID"
yts --preset claims "https://youtu.be/SOME_VIDEO_ID"
yts --preset critique "https://youtu.be/SOME_VIDEO_ID"
yts --list-presets
```

Each preset gets a distinct output file, so extracting action items does not
replace the ordinary summary. A custom prompt uses the `custom` task name unless
you provide a reusable name:

```sh
yts --task study-guide -p "Create a detailed study guide." VIDEO
```

Bare 11-character YouTube video IDs also work:

```sh
yts SOMEVIDEOID1
```

Normal watch URLs summarize the single video, even if the pasted URL includes a
playlist query parameter. Use a playlist URL when you want a full playlist.

## Output

By default, summaries are saved under the platform's user data directory. A
typical Linux layout is:

```txt
~/.local/share/yt-summarizer/summaries/
  Veritasium/
    aBcD1234-how-electricity-actually-works.md
    aBcD1234-how-electricity-actually-works--actions.md
  Kurzgesagt/
    XyZ98765-the-egg-a-short-story.md
```

The actual location follows the operating system conventions: AppData on
Windows, Application Support on macOS, and XDG directories on Linux. Run
`yts --help` to see the resolved location, or use `--out-dir` to override it.
Each file includes searchable YAML front matter containing the source, writer,
model, task, timestamp, prompt hash, and transcript hash.

Generated transcripts and metadata are cached separately:

```txt
~/.cache/yt-summarizer/
  Veritasium/
    aBcD1234.json
```

This cache lets later runs reuse fetched captions, Whisper transcripts, and
completed long-video chunks. It is keyed by video ID, so channel renames do not
invalidate it.

## Videos without captions

Most videos have manual or automatic captions. When a video does not, use:

```sh
yts -W "https://youtu.be/SOME_VIDEO_ID"
```

Install the optional transcription dependency explicitly:

```sh
uv tool install --force 'yt-summarizer[whisper] @ git+https://github.com/mthorson/yt-summarizer'
```

Whisper may download a model and the video's audio, so the first run can take
several minutes. The program never installs packages at runtime.

Choose a different transcription model with:

```sh
yts -W -M small "https://youtu.be/SOME_VIDEO_ID"
```

Larger models are usually slower and may need more memory.

## Configuration

The configuration file also follows the operating system's standard application
configuration directory. A typical Linux path is:

```txt
~/.config/yt-summarizer/config.toml
```

It supports normal CLI defaults and custom presets:

```toml
writer = "codex"
model = "auto"
language = "en"
output_dir = "~/Documents/YouTube Summaries"
cache_dir = "~/.cache/yt-summarizer"
chunk_tokens = 30000
chunk_overlap = 400
timeout = 600
preset = "summary"

[presets]
study = "Create a study guide with concepts, definitions, and timestamp links."
decisions = "Extract decisions, tradeoffs, and unresolved questions."
```

Command-line flags override configuration values.

URLs can also be piped over standard input:

```sh
pbpaste | yts
printf '%s\n' VIDEO_ID_1 VIDEO_ID_2 | yts --json
```

## Cost and privacy

`yt-summarizer` does not call model APIs directly and does not ask for API
keys. It shells out to your local writer CLI, so usage follows that CLI's
signed-in account, limits, and data handling.

For Claude, that means the local `claude` command. For Codex, that means the
local `codex exec` command. Codex supports ChatGPT sign-in for subscription
access and API key sign-in for usage-based access, so check your Codex login
method if avoiding API pricing matters.

Transcripts and generated summaries are stored locally in the configured cache
and output directories. Be careful before sharing them because they may contain
copyrighted or sensitive material from the videos you process.

The complete transcript is sent to the selected local writer CLI and is subject
to that service's data handling. Writer processes run in empty temporary
directories. Codex uses a read-only sandbox and ignores project rules; Claude
tools are disabled. These measures reduce local-data exposure, but model output
should still be treated as untrusted.

## Troubleshooting

`yts: command not found`

Run `uv tool update-shell`, then close and reopen your terminal.

`claude not found` or `codex not found`

Install the writer CLI you want, make sure it is on your PATH, or pass
`--writer` to select the one you have installed.

An error mentioning writer authentication

Run `claude` or `codex login`, sign in, then try `yts` again.

An error saying the writer CLI is incompatible

Update that CLI to its current release and run `yts --doctor` again. Compatibility
is checked by supported capabilities rather than a hard-coded version number.

`no captions found`

Run again with `--whisper`.

A batch stopped partway through

You may have hit a subscription or rate limit. Long-video chunk notes are cached,
and batch runs write `last-run.json` under the output directory. Retry commands
are included for failed items. Current outputs are skipped only when their
transcript, prompt, task, writer, model, and schema provenance still match.

A summary looks too vague

Try a stricter prompt. Custom prompts can ask for a different kind of output,
not just a different summary style:

```sh
yts -p "Write concrete bullets with names, tools, numbers, and claims." \
  "https://youtu.be/SOME_VIDEO_ID"
yts -p "What should I actually do with this information?" \
  "https://youtu.be/SOME_VIDEO_ID"
```

## Current limitations

- Progress is accurate for video counts and high-level stages, but model CLIs do
  not expose token-level completion percentages.
- Timestamp quality depends on the caption track supplied by YouTube.
- Very large chunk syntheses can still reach a writer's context or usage limits.
- Some playlist/channel expansion still depends on `yt-dlp` behavior.

## Roadmap ideas

- Add more tests around real `yt-dlp` playlist shapes.
- Add optional semantic search across saved summaries.

## Development

Install the checkout as an editable command:

```sh
git clone https://github.com/mthorson/yt-summarizer
cd yt-summarizer
./install.sh
```

Then use the normal command:

```sh
yts "https://youtu.be/SOME_VIDEO_ID"
```

Optional Whisper dependency:

```sh
uv sync --extra whisper
```

Run tests:

```sh
uv run python -m unittest discover -s tests -v
```

See [CHANGELOG.md](CHANGELOG.md) for release history and
[RELEASING.md](RELEASING.md) for the tagged release process.

Pipeline:

```txt
input URL, ID, file, or playlist
  -> yt-dlp metadata and captions
  -> cache/<channel>/<video_id>.json
  -> optional local Whisper transcription
  -> bounded/resumable chunk notes when needed
  -> isolated claude -p or codex exec
  -> summaries/<channel>/<video_id>-<slug>.md
```

With `--writer claude`, default model routing uses Sonnet, then switches to
Haiku above `--long-threshold` estimated tokens. Opus is only used when
explicitly selected. With `--writer codex`, `--model auto` uses the Codex CLI's
built-in default because user configuration is intentionally isolated; any
other `--model` value is passed to `codex --model`.

## License

The source code is available under the [MIT License](LICENSE). I chose MIT
because this is a small command-line utility and I want people to be able to
use it personally, package it, integrate it, fork it, and contribute fixes with
minimal legal friction. MIT still requires preservation of the copyright and
license notice and disclaims warranty.

The license covers this repository's code only. It does not grant rights to
YouTube videos, captions, downloaded audio, generated summaries, model services,
or third-party dependencies. Users remain responsible for the applicable terms
and copyright rules governing the content they process.

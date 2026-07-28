"""Prompt text for transcript-grounded video tasks."""

# Sent via `claude -p --system-prompt`. Keeps the model acting as a focused
# summarizer rather than an agent, so no tools, no questions, no preamble.
DEFAULT_SYSTEM_PROMPT = (
    "You are a precise video summarizer. You are given a YouTube video's title, "
    "channel, and full transcript. Write a faithful summary based strictly on the "
    "transcript, and never invent facts, opinions, or details that are not present. "
    "Output GitHub-flavored Markdown only. Do not use any tools, do not ask "
    "questions, and do not add any preamble, sign-off, or meta commentary such as "
    "'Here is the summary'. Begin directly with the summary content."
)


# Used when the user supplies --prompt or --prompt-file. The custom prompt is
# the task, so this avoids forcing every custom task back into summary format.
CUSTOM_SYSTEM_PROMPT = (
    "You are given a YouTube video's title, channel, and full transcript. Follow "
    "the user's instruction exactly, whether they ask for a summary, action plan, "
    "critique, checklist, extraction, or another video-grounded output. Base your "
    "answer strictly on the transcript and metadata. Do not invent facts, opinions, "
    "quotes, or details that are not present. Output GitHub-flavored Markdown only. "
    "Do not use any tools, do not ask questions, and do not add any preamble, "
    "sign-off, or meta commentary such as 'Here is the answer'. Begin directly "
    "with the requested content."
)


SALES_INTENT_INSTRUCTION = (
    "If the video itself is specifically trying to sell the viewer something, "
    "and this is not merely an unrelated advertisement or sponsor segment, note "
    "that clearly."
)

# Default user instruction (TL;DR + key takeaways). Overridable with
# --prompt "<text>" or --prompt-file <path>.
DEFAULT_PROMPT = (
    "Summarize this YouTube video. Structure the output exactly as:\n\n"
    "**TL;DR**: 2 to 4 sentences capturing the subject and main point.\n\n"
    "**Key takeaways**\n"
    "- A bulleted list of the main points, arguments, or steps, in the order they "
    "appear.\n"
    "- Be specific and concrete; prefer the video's actual claims over vague "
    "generalities.\n"
)


BUILTIN_PRESETS = {
    "summary": DEFAULT_PROMPT,
    "actions": (
        "Extract a practical action plan from this video. Separate concrete next "
        "steps from optional ideas, preserve important qualifications, and include "
        "timestamp links for supporting passages when timestamps are available."
    ),
    "claims": (
        "List the video's important factual claims and arguments. For each, state "
        "the evidence or reasoning offered in the transcript and include a timestamp "
        "link when available. Do not independently endorse the claims."
    ),
    "critique": (
        "Critically assess the video's argument using only internal evidence from "
        "the transcript. Identify assumptions, unsupported leaps, counterpoints the "
        "video addresses or omits, and its strongest points. Include timestamp links."
    ),
}

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

# Built-in summary headings per output language. The writer is told to use
# these exact labels, and the CLI checks for them to catch malformed output.
# Languages not listed here still work; the writer translates the headings
# itself and the heading check is skipped.
SUMMARY_HEADINGS: dict[str, tuple[str, str]] = {
    "en": ("TL;DR", "Key takeaways"),
    "tr": ("Kısa Özet", "Öne Çıkan Noktalar"),
    "de": ("Kurzfassung", "Wichtigste Punkte"),
    "fr": ("En bref", "Points clés"),
    "es": ("Resumen", "Puntos clave"),
    "it": ("In breve", "Punti chiave"),
    "pt": ("Resumo", "Pontos principais"),
    "nl": ("Samenvatting", "Belangrijkste punten"),
    "ru": ("Кратко", "Ключевые выводы"),
    "ar": ("باختصار", "أهم النقاط"),
    "ja": ("要約", "主なポイント"),
    "zh": ("摘要", "要点"),
    "ko": ("요약", "핵심 내용"),
}

LANGUAGE_NAMES: dict[str, str] = {
    "en": "English",
    "tr": "Turkish",
    "de": "German",
    "fr": "French",
    "es": "Spanish",
    "it": "Italian",
    "pt": "Portuguese",
    "nl": "Dutch",
    "ru": "Russian",
    "ar": "Arabic",
    "ja": "Japanese",
    "zh": "Chinese",
    "ko": "Korean",
    "az": "Azerbaijani",
    "pl": "Polish",
    "uk": "Ukrainian",
    "hi": "Hindi",
    "fa": "Persian",
    "el": "Greek",
    "sv": "Swedish",
}


def normalize_language(value: str | None) -> str | None:
    """Return a lower-case code such as ``"tr"`` (``tr-TR`` -> ``tr``).

    Free-form names (``"turkish"``, ``"Türkçe"``) are mapped back to a code
    when recognised and otherwise passed through unchanged.
    """
    if not value or not str(value).strip():
        return None
    text = str(value).strip()
    code = text.lower().replace("_", "-").split("-", 1)[0]
    if code in LANGUAGE_NAMES:
        return code
    aliases = {name.lower(): code for code, name in LANGUAGE_NAMES.items()}
    aliases.update({"türkçe": "tr", "turkce": "tr", "deutsch": "de"})
    return aliases.get(text.lower(), text)


def language_name(code: str) -> str:
    return LANGUAGE_NAMES.get(code, code)


def summary_prompt(language: str | None = None) -> str:
    """The built-in summary instruction, optionally in a given output language."""
    code = normalize_language(language) or "en"
    headings = SUMMARY_HEADINGS.get(code)
    short, points = headings or ("TL;DR", "Key takeaways")
    prompt = (
        "Summarize this YouTube video. Structure the output exactly as:\n\n"
        f"**{short}**: 2 to 4 sentences capturing the subject and main point.\n\n"
        f"**{points}**\n"
        "- A bulleted list of the main points, arguments, or steps, in the order "
        "they appear.\n"
        "- Be specific and concrete; prefer the video's actual claims over vague "
        "generalities.\n"
    )
    if code != "en" and not headings:
        prompt += f"\nTranslate the two headings above into {language_name(code)}.\n"
    return prompt


def language_instruction(language: str) -> str:
    name = language_name(normalize_language(language) or language)
    return (
        f"Write the entire response in {name}, including headings, regardless of "
        "the language of the video, transcript, or intermediate notes. Keep proper "
        "names, quotations that must stay verbatim, and links unchanged."
    )


# Default user instruction (TL;DR + key takeaways, in English). Overridable
# with --prompt "<text>" or --prompt-file <path>; the output language is set
# with --summary-lang.
DEFAULT_PROMPT = summary_prompt("en")


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

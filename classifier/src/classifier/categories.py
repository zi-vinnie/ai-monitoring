import json

# The fixed activity taxonomy. One screenshot in, exactly one of these out.
# Keep this in sync with the top-level CLAUDE.md and the `label` column values.
CATEGORIES: tuple[str, ...] = (
    "schoolwork",
    "gaming",
    "video_entertainment",
    "social_media",
    "browsing_other",
    "idle_locked",
)

_DESCRIPTIONS: dict[str, str] = {
    "schoolwork": "homework, essays, coding for class, research, online learning "
    "(Google Classroom, Canvas), documents, or educational reading.",
    "gaming": "playing or launching video games — game clients like Steam or Epic, "
    "titles such as Minecraft or Rocket League, or any in-game screen.",
    "video_entertainment": "watching video for fun — YouTube, Netflix, Twitch, "
    "Disney+, or similar streaming in a video player.",
    "social_media": "social networking and chat — Instagram, Snapchat, TikTok, "
    "X/Twitter, Reddit, Discord, WhatsApp, Facebook, or messaging apps.",
    "browsing_other": "general web use that fits none of the above — shopping, "
    "news, search results, or aimless browsing.",
    "idle_locked": "no active use — a lock screen, login/sign-in prompt, "
    "screensaver, or an all-black or blank display.",
}

# JSON-schema for Ollama's structured-output `format`: constrains the model to
# emit exactly {"label": "<one of CATEGORIES>"} so the response can't drift.
LABEL_FORMAT: dict = {
    "type": "object",
    "properties": {"label": {"type": "string", "enum": list(CATEGORIES)}},
    "required": ["label"],
}


def build_prompt(window_title: str | None) -> str:
    """Prompt the vision model with the taxonomy and the window-title hint."""
    lines = [
        "You are labelling a screenshot from a monitored computer into exactly "
        "one activity category. Choose the single best fit.",
        "",
        "Categories:",
    ]
    lines += [f"- {name}: {_DESCRIPTIONS[name]}" for name in CATEGORIES]
    lines.append("")
    if window_title:
        lines.append(
            f'The focused window title is "{window_title}". Use it as a hint, '
            "but trust what the image actually shows."
        )
    else:
        lines.append(
            "There is no focused-window title — the screen may be locked, idle, "
            "or showing the desktop."
        )
    lines.append('')
    lines.append('Respond with a JSON object of the form {"label": "<category>"}.')
    return "\n".join(lines)


def parse_label(raw: str) -> str | None:
    """Extract a valid category from the model's raw response.

    With structured output the response is JSON like ``{"label": "gaming"}``;
    fall back to a lenient substring match so a plain-text reply still resolves.
    Returns ``None`` when nothing matches, leaving the row for the caller to skip.
    """
    text = (raw or "").strip()
    try:
        obj = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        obj = None
    if isinstance(obj, dict) and obj.get("label") in CATEGORIES:
        return obj["label"]

    lowered = text.lower()
    for category in CATEGORIES:
        if category in lowered:
            return category
    return None

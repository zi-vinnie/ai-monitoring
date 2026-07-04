import json

# The fixed activity taxonomy. One screenshot in, exactly one of these out.
# Keep this in sync with the top-level CLAUDE.md and the `label` column values.
CATEGORIES: tuple[str, ...] = (
    "productive",
    "gaming",
    "video_entertainment",
    "social_media",
    "browsing_other",
    "unknown",
)

_DESCRIPTIONS: dict[str, str] = {
    "productive": "any genuinely worthwhile or purposeful activity — trading or "
    "investing (charts, broker/exchange platforms like TradingView, MetaTrader, "
    "or a brokerage), coding or software development, writing, research, "
    "learning, job or college applications, spreadsheets, or documents; also "
    "system settings, personalisation, and file management (File Explorer); and "
    "watching an educational or finance video (e.g. a finance, coding, or "
    "how-to/educational YouTube video).",
    "gaming": "playing or launching video games — game clients like Steam or Epic, "
    "titles such as Minecraft or Rocket League, or any in-game screen.",
    "video_entertainment": "watching video purely for entertainment — YouTube, "
    "Netflix, Twitch, Disney+, or similar streaming for fun. Educational or "
    "finance videos do NOT belong here; count those as productive.",
    "social_media": "social networking and chat — Instagram, Snapchat, TikTok, "
    "X/Twitter, Reddit, Discord, WhatsApp, Facebook, or messaging apps.",
    "browsing_other": "general web browsing in a browser that fits none of the "
    "above — shopping, news, search results, or aimless browsing.",
    "unknown": "LAST RESORT ONLY — use this solely when the screenshot genuinely "
    "fits none of the categories above, or is too unclear or unreadable to tell "
    "(e.g. a blank/black screen, a lock/login screen, or an image you cannot make "
    "out). Do not use it for anything that shows identifiable activity.",
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
    lines.append(
        "Guidance: 'productive' is the primary, default category. If the screen "
        "shows any purposeful activity, or you are unsure between 'productive' "
        "and another category, choose 'productive'. Only pick a different "
        "category when the screen is obviously that category — clearly a game, "
        "an entertainment video, social media, or general web browsing. Choose "
        "'unknown' only as a last resort when nothing fits or the image is "
        "unreadable."
    )
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

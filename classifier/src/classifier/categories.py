import json

# The fixed activity taxonomy. One screenshot in, exactly one of these out.
# Keep this in sync with the top-level CLAUDE.md and the `label` column values.
CATEGORIES: tuple[str, ...] = (
    "productive",
    "gaming",
    "video_entertainment",
    "social_media",
    "browsing",
    "unknown",
)

_DESCRIPTIONS: dict[str, str] = {
    "productive": "work, school, or any purposeful activity. Includes: coding or "
    "software development (IDE, code editor, terminal, Stack Overflow, technical "
    "documentation); writing, note-taking, spreadsheets, documents, PDFs, or "
    "presentations; research and learning (Wikipedia, online courses, tutorials, "
    "homework); trading or investing (price charts, TradingView, MetaTrader, a "
    "brokerage or banking site); email, calendars, video calls, or meetings; job "
    "or college applications; using an AI assistant (ChatGPT, Claude, Copilot); "
    "creative tools (photo, video, audio, or design editors); system settings, "
    "installing or updating software, and file management (File Explorer); and "
    "watching an educational, how-to, coding, or finance video.",
    "gaming": "actively playing a video game. Includes: any in-game screen, "
    "game menus, lobbies, or scoreboards; a game's loading screen (a 'Loading' "
    "message or progress percentage, often on a plain background); game "
    "launchers and stores (Steam, Epic, Xbox, Battle.net, Riot); browser games "
    "and game sites (.io games, Poki, CrazyGames, Playgama, or any page that "
    "says 'play'); driving, sports, or combat simulators; emulators; titles "
    "like Minecraft, Roblox, Fortnite, or Rocket League. Watching a video of "
    "someone ELSE playing is video_entertainment, not gaming.",
    "video_entertainment": "watching video for fun. Includes: YouTube, Netflix, "
    "Disney+, Prime Video, Hulu, or any streaming site; Twitch or other live "
    "streams; movies, TV shows, music videos, gameplay or streamer videos; a "
    "local video player (VLC, Media Player). Educational, how-to, coding, or "
    "finance videos do NOT belong here — label those productive.",
    "social_media": "social feeds and messaging. Includes: Instagram, TikTok, "
    "Snapchat, X/Twitter, Facebook, Reddit, Discord, WhatsApp, Telegram, "
    "Messenger; scrolling a feed, viewing posts, stories, shorts, or reels; "
    "chatting, group chats, or direct messages.",
    "browsing": "web browsing that fits none of the above. Use ONLY when the "
    "main window is a web browser showing an ordinary, fully loaded web page: "
    "shopping (Amazon, eBay), news, sports scores, meme or humour sites, "
    "weather, maps, search-results pages, or aimless surfing. Never use it "
    "when no browser is on screen, for a page still loading (label that by "
    "what its title names), or for a game, video, or social site in a browser "
    "— those keep their own category.",
    "unknown": "LAST RESORT ONLY — the image shows no identifiable activity: a "
    "blank or black screen, a lock or login screen, a boot screen, an empty "
    "desktop with nothing open, or an image too unclear to read. Never use it "
    "when you can identify any app, site, or activity.",
}

# JSON-schema for Ollama's structured-output `format`. `screen_content` comes
# first so the model describes what it sees before committing to a label (a
# cheap reasoning step that measurably helps small vision models); `label` is
# constrained to the six categories so the response can't drift.
LABEL_FORMAT: dict = {
    "type": "object",
    "properties": {
        "screen_content": {"type": "string"},
        "label": {"type": "string", "enum": list(CATEGORIES)},
    },
    "required": ["screen_content", "label"],
}


def build_prompt(window_title: str | None) -> str:
    """Prompt the vision model with the taxonomy and the window-title hint."""
    lines = [
        "Look at this screenshot from a monitored computer and decide what the "
        "person is doing. You must label it with exactly one activity category.",
        "",
        "Categories:",
    ]
    lines += [f"- {name}: {_DESCRIPTIONS[name]}" for name in CATEGORIES]
    lines += [
        "",
        "Rules:",
        "- Judge by the main content on screen (the focused or largest window), "
        "not by small background windows, the taskbar, or browser tabs.",
        "- Playing a game yourself is gaming; watching someone else play (a "
        "stream or gameplay video) is video_entertainment.",
        "- A desktop wallpaper (a photo of nature, animals, or scenery behind "
        "desktop icons and the taskbar) is NOT a video and is never "
        "video_entertainment. A screen showing only the desktop is labeled by "
        "the window title, or unknown if the title names nothing.",
        "- Fullscreen games often fail to appear in the capture, leaving only "
        "the desktop wallpaper or a black frame. If the window title names a "
        "game but the screen shows just the desktop or a blank screen, the "
        "game IS running — label it gaming, ignoring the wallpaper.",
        "- A game running in a browser tab is still gaming, not browsing. If "
        "the window title names a game or a game site, or the screen shows "
        "game-like graphics being controlled, it is gaming — even when the "
        "page is only a loading or menu screen.",
        "- A loading or splash screen belongs to whatever is loading: label it "
        "by what the window title says is opening (a game loading is gaming, "
        "a video site loading is video_entertainment), not as browsing.",
        "- For any video: educational, how-to, coding, or finance content is "
        "productive; entertainment content is video_entertainment.",
        "- 'productive' is the default. If the activity is purposeful, or you "
        "are torn between productive and another category, choose productive. "
        "Pick a different category only when the screen is clearly that thing.",
        "- Use unknown only when you cannot identify any activity at all.",
        "",
    ]
    if window_title:
        lines.append(
            f'The focused window title is "{window_title}". It usually names '
            "the app, game, video, or site in use. When the screen itself is "
            "ambiguous — a loading page, splash screen, or nearly empty window "
            "— the title is your best evidence, so label by what it names. "
            "IMPORTANT: fullscreen games often fail to appear in the capture, "
            "leaving only the desktop wallpaper or a black frame. So if the "
            "title names a game or app but the screen shows just a desktop "
            "background, wallpaper photo, or blank screen, trust the title and "
            "label by what it names (a game title means gaming)."
        )
    else:
        lines.append(
            "There is no focused-window title — the screen may be locked, idle, "
            "or showing the desktop."
        )
    lines += [
        "",
        "Respond with a JSON object: first \"screen_content\", one short "
        "sentence saying what is on screen, then \"label\", the single best "
        "category.",
    ]
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

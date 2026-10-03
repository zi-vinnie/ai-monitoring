import json
import re

# The label for "machine on but nobody actively using it" — bare desktop, lock
# screen, blank frame. Excluded from active screen-time totals (see aggregate).
IDLE = "idle"

# The fixed activity taxonomy. One screenshot in, exactly one of these out.
# Keep this in sync with the top-level CLAUDE.md and the `label` column values.
CATEGORIES: tuple[str, ...] = (
    "productive",
    "gaming",
    "video_entertainment",
    "social_media",
    "browsing",
    IDLE,
)

_DESCRIPTIONS: dict[str, str] = {
    "productive": "work, school, or any purposeful activity. Includes: coding or "
    "software development (IDE, code editor, terminal, Stack Overflow, technical "
    "documentation); writing, note-taking, spreadsheets, documents, PDFs, or "
    "presentations; research and learning (Wikipedia, online courses, tutorials, "
    "homework); trading or investing (price charts, TradingView, MetaTrader, a "
    "brokerage or banking site); email, calendars, or school or work meetings "
    "(Zoom, Teams, Google Meet); job "
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
    "local video player (VLC, Media Player). Videos about games (gameplay, "
    "game tutorials or tips, game news) belong here. Educational, how-to, "
    "coding, or finance videos do NOT belong here — label those productive.",
    "social_media": "social feeds and messaging. Includes: Instagram, TikTok, "
    "Snapchat, X/Twitter, Facebook, Reddit, Discord, WhatsApp, Telegram, "
    "Messenger; scrolling a feed, viewing posts, stories, shorts, or reels; "
    "chatting, group chats, or direct messages; voice or video calls with "
    "friends (WhatsApp, Discord, Snapchat, FaceTime); and random video-chat "
    "sites that pair you with strangers (Omegle, OmeTV, Monkey).",
    "browsing": "web browsing that fits none of the above. Use ONLY when the "
    "main window is a web browser showing an ordinary, fully loaded web page: "
    "shopping (Amazon, eBay), news, sports scores, meme or humour sites, "
    "weather, maps, search-results pages, or aimless surfing. Never use it "
    "when no browser is on screen, for a page still loading (label that by "
    "what its title names), or for a game, video, or social site in a browser "
    "— those keep their own category.",
    "idle": "the machine is on but nobody is actively using it: an empty "
    "desktop or home screen with nothing open, a lock or login screen, a "
    "screensaver, a boot screen, a blank or black screen, or an image too "
    "unclear to identify any activity. Use this whenever no app, site, or "
    "activity can be identified.",
}

# Exact window titles we can label without asking the vision model, because the
# title alone is decisive. Match is case-insensitive on the stripped title.
#   - Game clients whose title never appears outside the game -> gaming. This is
#     cheaper (no Ollama call) and dodges the exclusive-fullscreen black/
#     wallpaper frame problem entirely.
#   - "Program Manager" is the Windows desktop shell (Progman): when it holds
#     focus the user is on the bare desktop -> idle. A missing title (no focused
#     window) is the same bare-desktop case, handled in label_for_title below.
# Keep values in CATEGORIES.
_TITLE_OVERRIDES: dict[str, str] = {
    "overwatch": "gaming",
    "rocket league (64-bit, dx11, cooked)": "gaming",
    "program manager": IDLE,
    "lockingwindow": IDLE,  # the Windows lock screen
    "bloons td battles 2": "gaming",
    "watch_dogs 2": "gaming",
    "car soccer - google chrome": "gaming",
    "kour.io | fps io game - play kour io online! - google chrome": "gaming",
    "veck.io | fps io game - play veck io online - google chrome": "gaming",
}


# Random video-chat sites that pair the user with strangers, by title prefix.
# Shared with flags.py, which calls these out by name in the report.
STRANGER_CHAT_SITE = r"^(omegle|ometv|monkey: random video chat|chatroulette)\b"

# A YouTube/TikTok video page — someone else's footage, whatever it's about.
VIDEO_PAGE = re.compile(r" - youtube - | \| tiktok - ", re.IGNORECASE)

# Title patterns the title alone settles, for apps whose titles vary (a chat
# name, an unread count) so an exact match can't catch them. Checked in order
# after the exact map; searched case-insensitively. Video pages are excluded
# first (see VIDEO_PAGE) so e.g. a YouTube video *about* Omegle isn't caught.
_TITLE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(pattern, re.IGNORECASE), label)
    for pattern, label in (
        (r" - discord$", "social_media"),
        (r"^(\(\d+\) )?(instagram|snapchat)\b", "social_media"),
        (r"^whatsapp$", "social_media"),
        (r"^(group )?(video|voice) call$", "social_media"),
        (r" is typing\.\.\.", "social_media"),
        (STRANGER_CHAT_SITE, "social_media"),
    )
)


def label_for_title(window_title: str | None) -> str | None:
    """Return a hard-coded label for a known window title, else None.

    Lets the classifier skip the vision model when the title alone is decisive:
    known game clients -> gaming, chat and social apps -> social_media, and the
    bare desktop (a missing title, the "Program Manager" shell, or the lock
    screen) -> idle. Returns None (fall through to the model) for everything
    else.
    """
    if not window_title:
        return IDLE
    title = window_title.strip()
    exact = _TITLE_OVERRIDES.get(title.lower())
    if exact is not None or VIDEO_PAGE.search(title):
        return exact
    for pattern, label in _TITLE_PATTERNS:
        if pattern.search(title):
            return label
    return None


def correct_label(window_title: str | None, label: str) -> str:
    """Overrule a model label the window title contradicts.

    A YouTube/TikTok video page is someone else's footage, never the user
    playing, so the small model's habit of calling gameplay videos "gaming"
    is corrected to video_entertainment.
    """
    if label == "gaming" and window_title and VIDEO_PAGE.search(window_title):
        return "video_entertainment"
    return label


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
        "the window title, or idle if the title names nothing.",
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
        "productive; entertainment content is video_entertainment. A video "
        "about a game — including a tutorial or tips for a game — is "
        "video_entertainment, not productive and not gaming.",
        "- A call or chat with friends (WhatsApp, Discord, Snapchat, Instagram) "
        "is social_media, not productive.",
        "- 'productive' is the default. If the activity is purposeful, or you "
        "are torn between productive and another category, choose productive. "
        "Pick a different category only when the screen is clearly that thing.",
        "- Use idle only when the screen shows no activity at all — a bare "
        "desktop, a lock or login screen, or a blank screen.",
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
            "There is no focused-window title — the machine is most likely idle: "
            "locked, at a login screen, or showing the bare desktop. Prefer idle "
            "unless the screen clearly shows an identifiable activity."
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

"""How the bot signs its comments, and how a comment is recognised as the bot's."""

MARKER_PREFIX = "<!-- kargah:"


def bot_comment(kind: str, run: str, text: str) -> str:
    """A visible header for people and a hidden marker for the engine."""
    return f"**kargah-bot** · {kind} · run {run}\n\n{text}\n\n{MARKER_PREFIX}{kind} run={run} -->"


def carries_marker(body: str) -> bool:
    return MARKER_PREFIX in body

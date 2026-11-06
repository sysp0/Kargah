"""`/decision ...` comments of the owner become files in the project (docs/decisions/), on the ticket's branch."""
from __future__ import annotations

from collections.abc import Sequence

from kargah.domain.ticket import Comment

PREFIX = "/decision"
DIRECTORY = "docs/decisions"


def decision_files(ticket: int, human_comments: Sequence[Comment]) -> dict[str, str]:
    """path -> content; the file name carries the comment id, so writing twice changes nothing."""
    files: dict[str, str] = {}
    for c in human_comments:
        body = c.body.strip()
        if body.startswith(PREFIX):
            text = body.removeprefix(PREFIX).strip()
            files[f"{DIRECTORY}/{ticket}-{c.id}.md"] = (
                f"# Decision (ticket #{ticket})\n\n{text}\n\nRecorded from a comment by {c.author.username} "
                f"on {c.created_at.date().isoformat()}.\n")
    return files

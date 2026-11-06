"""Prompt templates (package data) and the conversation block built from the owner's comments."""
from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from string import Template

from kargah.domain.ticket import Comment

PROMPTS = Path(__file__).parent / "prompts"


def render(name: str, **values: object) -> str:
    text = (PROMPTS / f"{name}.md").read_text(encoding="utf-8")
    return Template(text).safe_substitute({k: str(v) for k, v in values.items()})


def conversation(human_comments: Sequence[Comment]) -> str:
    if not human_comments:
        return ""
    lines = [f"- {c.author.username}: {c.body.strip()}" for c in human_comments]
    return "## The owner's comments on the ticket (newest last; they are decisions, follow them)\n" + "\n".join(lines)

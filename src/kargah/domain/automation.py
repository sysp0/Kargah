"""A cron automation: it only ever opens an issue; the normal pipeline does the work (pure)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Automation:
    name: str
    enabled: bool
    cron: str
    title: str                 # `{date}` becomes the slot's date (YYYY-MM-DD)
    labels: tuple[str, ...]    # extra labels; never a status label (so never `ready`)
    body: str


def marker(name: str, slot: datetime) -> str:
    return f"<!-- kargah:automation name={name} slot={slot.isoformat()} -->"


def issue_text(spec: Automation, slot: datetime) -> tuple[str, str]:
    return spec.title.replace("{date}", slot.date().isoformat()), f"{spec.body}\n\n{marker(spec.name, slot)}"

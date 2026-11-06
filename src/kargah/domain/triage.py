"""The triage report: a fixed text format, parsed and written by the same code (pure)."""
from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from kargah.domain.agents import SIZES

ACCEPTANCE_HEADING = re.compile(r"(?im)^#{1,6}\s*(acceptance( criteria)?|معیار(های)? پذیرش)\b")


@dataclass(frozen=True)
class TriageReport:
    size: str
    ambiguity: str | None
    acceptance: tuple[str, ...]
    references: tuple[str, ...] = ()

    @property
    def ambiguous(self) -> bool:
        return self.ambiguity is not None


def size_rank(size: str) -> int:
    return SIZES.index(size)


def body_has_acceptance(body: str) -> bool:
    return ACCEPTANCE_HEADING.search(body) is not None


def parse_triage(text: str) -> TriageReport | None:
    """None when SIZE is missing or unknown, or there is no ACCEPTANCE line."""
    sizes = re.findall(r"^SIZE:\s*(\S+)\s*$", text, re.M)
    acceptance = tuple(a.strip() for a in re.findall(r"^ACCEPTANCE:\s*(.+)$", text, re.M))
    if not sizes or sizes[-1] not in SIZES or not acceptance:
        return None
    found = re.findall(r"^AMBIGUITY:\s*(.+)$", text, re.M)
    ambiguity = None if not found or found[-1].strip().lower() in ("none", "-", "") else found[-1].strip()
    return TriageReport(sizes[-1], ambiguity, acceptance,
                        tuple(r.strip() for r in re.findall(r"^REFERENCE:\s*(.+)$", text, re.M)))


def parse_questions(text: str) -> tuple[str, ...]:
    """Every `QUESTION:` line (triage and spec ask all their questions at once)."""
    return tuple(q.strip() for q in re.findall(r"^QUESTION:\s*(.+)$", text, re.M))


def format_triage(report: TriageReport) -> str:
    lines = [f"SIZE: {report.size}", f"AMBIGUITY: {report.ambiguity or 'none'}"]
    lines += [f"ACCEPTANCE: {a}" for a in report.acceptance] + [f"REFERENCE: {r}" for r in report.references]
    return "\n".join(lines)


def acceptance_section(report: Sequence[str], references: Sequence[str]) -> str:
    out = "## Acceptance criteria (from triage)\n" + "\n".join(f"- {a}" for a in report)
    return out + ("\n\n## References\n" + "\n".join(f"- {r}" for r in references) if references else "")

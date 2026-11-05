"""Token and cost counters for Codex and Claude calls. Unknown fields are ignored."""

from __future__ import annotations

from dataclasses import asdict, dataclass

CODEX_FIELDS = {
    "input_tokens": "input",
    "cached_input_tokens": "cached",
    "cache_write_input_tokens": "cache_write",
    "output_tokens": "output",
    "reasoning_output_tokens": "reasoning",
}
CLAUDE_FIELDS = {
    "input_tokens": "input",
    "cache_read_input_tokens": "cached",
    "cache_creation_input_tokens": "cache_write",
    "output_tokens": "output",
}


@dataclass
class Usage:
    input: int = 0
    cached: int = 0
    cache_write: int = 0
    output: int = 0
    reasoning: int = 0
    cost_usd: float = 0.0
    calls: int = 0

    def add(self, other: Usage | dict) -> Usage:
        data = other if isinstance(other, dict) else asdict(other)
        for key in ("input", "cached", "cache_write", "output", "reasoning", "calls"):
            setattr(self, key, getattr(self, key) + int(data.get(key) or 0))
        self.cost_usd += float(data.get("cost_usd") or 0)
        return self

    def as_dict(self) -> dict:
        return asdict(self)

    @property
    def cache_pct(self) -> float | None:
        """Share of prompt tokens served from cache."""
        total = self.input + self.cached + self.cache_write
        return None if total == 0 else 100.0 * self.cached / total


def _num(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def from_codex_event(event: dict) -> Usage | None:
    """A codex exec --json line of type turn.completed carries the turn's usage."""
    if not isinstance(event, dict) or event.get("type") != "turn.completed":
        return None
    raw = event.get("usage")
    if not isinstance(raw, dict):
        return None
    out = Usage(calls=0)
    for src, dst in CODEX_FIELDS.items():
        setattr(out, dst, _num(raw.get(src)))
    # Codex reports cached tokens inside input_tokens; keep input as the uncached part.
    out.input = max(out.input - out.cached, 0)
    return out


def from_claude_result(event: dict) -> Usage | None:
    """The final `result` object of claude -p (json or stream-json)."""
    if not isinstance(event, dict) or event.get("type") != "result":
        return None
    raw = event.get("usage") if isinstance(event.get("usage"), dict) else {}
    out = Usage(calls=1, cost_usd=float(event.get("total_cost_usd") or 0))
    for src, dst in CLAUDE_FIELDS.items():
        setattr(out, dst, _num(raw.get(src)))
    return out


def short(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1000:
        return f"{n / 1000:.0f}k"
    return str(n)

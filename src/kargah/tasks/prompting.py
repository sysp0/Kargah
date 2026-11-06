"""Prompt templates (package data) and the conversation block built from the owner's comments."""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from string import Template

from kargah.domain.agents import AgentSpec
from kargah.domain.stages import Progress
from kargah.domain.ticket import Comment
from kargah.domain.triage import TriageReport, acceptance_section

PROMPTS = Path(__file__).parent / "prompts"


def render(name: str, **values: object) -> str:
    text = (PROMPTS / f"{name}.md").read_text(encoding="utf-8")
    return Template(text).safe_substitute({k: str(v) for k, v in values.items()})


def conversation(human_comments: Sequence[Comment]) -> str:
    if not human_comments:
        return ""
    lines = [f"- {c.author.username}: {c.body.strip()}" for c in human_comments]
    return "## The owner's comments on the ticket (newest last; they are decisions, follow them)\n" + "\n".join(lines)


def compose(spec: AgentSpec, task_text: str, **values: object) -> str:
    """Final prompt: the agent's instructions, the list of its skills (read on demand), then the task's data."""
    instructions = Template(spec.instructions).safe_substitute({k: str(v) for k, v in values.items()})
    skills = ""
    if spec.skills:
        lines = "\n".join(f"- `{s.name}`: {s.description} (`{s.path}`)" for s in spec.skills)
        skills = f"\n\n## Skills\nRead a skill file before you act on its subject.\n{lines}"
    return f"{instructions}{skills}\n\n{task_text}"


def build_context(progress: Progress, number: int) -> str:
    """What the earlier stages produced, for the build agent: acceptance criteria and the approved spec."""
    parts = []
    if progress.triage:
        parts.append(acceptance_section(progress.triage.acceptance, progress.triage.references))
    if progress.spec and progress.spec.approved:
        parts.append(f"## Approved spec\nThe approved spec is `docs/specs/{number}.md`. Its Validation criteria are your "
                     f"checklist. Do not diverge from it; if it is wrong, ask with QUESTION.")
    return "\n\n".join(parts)


def sized_agent(agent: AgentSpec, triage: TriageReport | None) -> AgentSpec:
    """The model for the ticket's size, when the agent file maps sizes to models."""
    if triage and triage.size in agent.models_by_size:
        return replace(agent, model=agent.models_by_size[triage.size])
    return agent

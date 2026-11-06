"""Label `builder-claude`: on that ticket Claude builds and a pending Codex usage-limit wait is ignored."""
from datetime import UTC, datetime, timedelta

from engine_fixtures import make_world, multiply_feature, says
from test_domain_rules import BOT, NOW, say

from kargah.adapters.factory_files import load_definition
from kargah.adapters.file_sources import DirSource
from kargah.domain.agents import claude_builder
from kargah.domain.decision import Action, decide
from kargah.domain.markers import bot_comment
from kargah.domain.ticket import Label, Ticket
from kargah.ports.harness import HarnessResult

LATER = (NOW + timedelta(hours=3)).isoformat()


def ticket(*labels: str) -> Ticket:
    return Ticket(1, "t", "", frozenset(labels))


def limit_comment(by: str | None):
    attrs = {"resume_at": LATER, **({"by": by} if by else {})}
    return [say(1, BOT, bot_comment("limit", "1", "wait", **attrs))]


def test_label_value():
    assert Label.BUILDER_CLAUDE == "builder-claude"


def test_a_pending_codex_limit_is_ignored_on_a_builder_claude_ticket():
    assert decide(ticket("in-progress"), limit_comment("codex"), BOT.id, NOW, 5).action is Action.SKIP
    labelled = ticket("in-progress", "builder-claude")
    assert decide(labelled, limit_comment("codex"), BOT.id, NOW, 5).action is Action.RESUME


def test_a_limit_marker_without_an_author_counts_as_codex():      # markers written before this label existed
    assert decide(ticket("in-progress", "builder-claude"), limit_comment(None), BOT.id, NOW, 5).action is Action.RESUME


def test_a_pending_claude_limit_still_waits_on_a_builder_claude_ticket():
    waiting = decide(ticket("in-progress", "builder-claude"), limit_comment("claude"), BOT.id, NOW, 5)
    assert waiting.action is Action.SKIP
    assert decide(ticket("in-progress", "builder-claude"), limit_comment("claude"), BOT.id,
                  NOW + timedelta(hours=4), 5).action is Action.RESUME


def test_claude_builder_replaces_only_the_implement_agent(tmp_path):
    agents = load_definition(DirSource(_repo(tmp_path))).agents
    changed = claude_builder(agents)
    implement = changed["implement"]
    assert (implement.harness, implement.model, implement.models_by_size) == ("claude", "claude-sonnet-5-5", {})
    assert implement.access == "edit" and implement.max_budget_usd == agents["implement"].max_budget_usd > 0
    assert changed["review"] == agents["review"] and agents["implement"].harness == "codex"


def _repo(tmp_path):
    (tmp_path / ".kargah").mkdir()
    (tmp_path / ".kargah/config.toml").write_text("")
    return tmp_path


def _limited_by_codex(world):
    stamp = (world.clock.now + timedelta(hours=3)).isoformat()
    n = world.tracker.open_ticket("add multiply", "add multiply(a, b)", ("in-progress", "builder-claude"))
    world.tracker.post_comment(n, bot_comment("limit", "0", "Codex is limited", resume_at=stamp, by="codex"))
    return n


def test_engine_starts_a_builder_claude_ticket_at_once_with_the_claude_model(tmp_path):
    w = make_world(tmp_path, [multiply_feature()], [says("VERDICT: PASS")])
    _limited_by_codex(w)
    assert w.engine.tick() == "needs-human"
    assert w.builder.calls[0].model == "claude-sonnet-5-5"


def test_engine_keeps_waiting_when_the_ticket_has_no_builder_claude_label(tmp_path):
    w = make_world(tmp_path, [multiply_feature()], [says("VERDICT: PASS")])
    n = _limited_by_codex(w)
    w.tracker.remove_label(n, "builder-claude")
    assert w.engine.tick() == "idle" and w.builder.calls == []


def test_a_claude_builder_limit_is_signed_claude_and_waits(tmp_path):
    reset = datetime(2026, 1, 1, 15, tzinfo=UTC)
    w = make_world(tmp_path, [lambda r: HarnessResult(ok=False, limited=True, resets_at=reset)], [])
    n = w.tracker.open_ticket("add multiply", "add multiply(a, b)", ("ready", "builder-claude"))
    assert w.engine.tick() == "limit"
    assert "by=claude" in w.tracker.comments(n)[-1].body
    assert w.engine.tick() == "idle"            # nothing may loop on the same limit

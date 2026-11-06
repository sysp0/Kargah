"""One contract, every adapter: the in-memory fake always, GitLab live when KARGAH_GITLAB_* is set."""
from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from urllib.parse import quote

import pytest
from memory_tracker import MemoryTracker

from kargah.adapters.gitlab.http import UrllibHttp
from kargah.adapters.gitlab.tracker import GitLabTracker
from kargah.domain.inputs import human_input
from kargah.domain.markers import bot_comment
from kargah.ports.tracker import Tracker

LIVE = all(k in os.environ for k in ("KARGAH_GITLAB_URL", "KARGAH_GITLAB_PROJECT", "KARGAH_GITLAB_TOKEN"))


@dataclass
class Env:
    tracker: Tracker
    ticket: int
    human_says: Callable[[str], None]


@pytest.fixture
def memory_env() -> Env:
    tracker = MemoryTracker()
    number = tracker.open_ticket("t")
    return Env(tracker, number, lambda body: tracker.human_says(number, body))


@pytest.fixture
def gitlab_env() -> Iterator[Env]:
    if not LIVE:
        pytest.skip("set KARGAH_GITLAB_URL, KARGAH_GITLAB_PROJECT, KARGAH_GITLAB_TOKEN to run against GitLab")
    project = os.environ["KARGAH_GITLAB_PROJECT"]
    path = f"projects/{quote(project, safe='')}"

    def owner(method: str, endpoint: str, **fields: str) -> dict:  # the human: the owner's own glab login
        args = [a for k, v in fields.items() for a in ("-f", f"{k}={v}")]
        out = subprocess.run(["glab", "api", "-X", method, f"{path}/{endpoint}", *args], capture_output=True,
                             text=True, check=True).stdout
        return json.loads(out) if out else {}

    issue = owner("POST", "issues", title="contract test (auto-deleted)")["iid"]
    tracker = GitLabTracker(UrllibHttp(os.environ["KARGAH_GITLAB_URL"], os.environ["KARGAH_GITLAB_TOKEN"]), project)
    try:
        yield Env(tracker, issue, lambda body: owner("POST", f"issues/{issue}/notes", body=body))
    finally:
        owner("DELETE", f"issues/{issue}")


@pytest.fixture(params=["memory_env", "gitlab_env"])
def env(request: pytest.FixtureRequest) -> Env:
    return request.getfixturevalue(request.param)


def test_labels_round_trip(env: Env):
    env.tracker.add_label(env.ticket, "ready")
    assert env.ticket in [t.number for t in env.tracker.tickets_with_label("ready")]
    env.tracker.remove_label(env.ticket, "ready")
    assert env.ticket not in [t.number for t in env.tracker.tickets_with_label("ready")]


def test_a_closed_ticket_is_listed_only_when_asked_and_reports_it_is_closed(env: Env):
    env.tracker.add_label(env.ticket, "needs-human")
    env.tracker.close_ticket(env.ticket)
    assert env.ticket not in [t.number for t in env.tracker.tickets_with_label("needs-human")]
    [closed] = [t for t in env.tracker.tickets_with_label("needs-human", include_closed=True)
                if t.number == env.ticket]
    assert not closed.open and not env.tracker.get_ticket(env.ticket).open and closed.url


def test_the_bot_never_answers_itself(env: Env):
    bot = env.tracker.whoami()
    env.tracker.post_comment(env.ticket, bot_comment("question", "1", "which column?"))
    env.tracker.post_comment(env.ticket, bot_comment("progress", "1", "still working"))
    comments = env.tracker.comments(env.ticket)
    assert all(c.author.id == bot.id for c in comments)
    assert human_input(comments, bot.id) == ()


def test_a_human_reply_after_the_bot_is_input(env: Env):
    bot = env.tracker.whoami()
    env.tracker.post_comment(env.ticket, bot_comment("question", "1", "which column?"))
    env.human_says("created_at")
    [answer] = human_input(env.tracker.comments(env.ticket), bot.id)
    assert answer.body == "created_at" and answer.author.id != bot.id


def test_a_created_ticket_has_exactly_the_given_labels_and_can_be_found_by_label(env: Env):
    number = env.tracker.create_ticket("contract: created (auto-closed)", "body <!-- kargah:improvement role=x -->",
                                       ("factory-change",))
    try:
        ticket = env.tracker.get_ticket(number)
        assert ticket.labels == {"factory-change"} and "kargah:improvement role=x" in ticket.body and ticket.open
        assert number in [t.number for t in env.tracker.tickets_with_label("factory-change")]
    finally:
        env.tracker.close_ticket(number)

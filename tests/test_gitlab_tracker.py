from typing import Any

import pytest

from kargah.adapters.gitlab.paging import PAGE
from kargah.adapters.gitlab.tracker import GitLabTracker

NOTE = {"id": 5, "body": "hi", "created_at": "2026-01-01T10:00:00.000Z", "author": {"id": 9, "username": "bot"}}


class FakeHttp:
    def __init__(self, replies: dict[tuple[str, str], Any]) -> None:
        self.replies, self.calls = replies, []

    def request(self, method: str, path: str, *, params=None, json=None):
        self.calls.append((method, path, params, json))
        reply = self.replies[(method, path)]
        return reply.pop(0) if isinstance(reply, list) and reply and isinstance(reply[0], list) else reply


@pytest.fixture
def base() -> str:
    return "projects/g%2Fp"


def test_project_path_is_url_encoded_and_labels_are_sent(base):
    http = FakeHttp({("GET", f"{base}/issues"): [{"iid": 3, "title": "t", "description": None, "labels": ["ready"]}]})
    [ticket] = GitLabTracker(http, "g/p").tickets_with_label("ready")
    assert ticket.number == 3 and ticket.body == "" and ticket.labels == {"ready"}
    assert http.calls[0][2]["labels"] == "ready" and http.calls[0][2]["state"] == "opened"


def test_system_notes_are_dropped(base):
    http = FakeHttp({("GET", f"{base}/issues/1/notes"): [{**NOTE, "system": True}, {**NOTE, "id": 6}]})
    assert [c.id for c in GitLabTracker(http, "g/p").comments(1)] == [6]


def test_comments_are_read_page_after_page(base):
    full = [[{**NOTE, "id": i} for i in range(PAGE)], [{**NOTE, "id": 999}]]
    http = FakeHttp({("GET", f"{base}/issues/1/notes"): full})
    assert len(GitLabTracker(http, "g/p").comments(1)) == PAGE + 1
    assert [c[2]["page"] for c in http.calls] == [1, 2]


def test_labels_and_comment_use_the_right_calls(base):
    http = FakeHttp({("PUT", f"{base}/issues/4"): {}, ("POST", f"{base}/issues/4/notes"): NOTE})
    tracker = GitLabTracker(http, "g/p")
    tracker.add_label(4, "needs-info")
    tracker.remove_label(4, "ready")
    tracker.post_comment(4, "hi")
    assert [c[3] for c in http.calls] == [{"add_labels": "needs-info"}, {"remove_labels": "ready"}, {"body": "hi"}]


def test_whoami_reads_the_token_owner():
    http = FakeHttp({("GET", "user"): {"id": 9, "username": "bot"}})
    assert GitLabTracker(http, "g/p").whoami().id == 9

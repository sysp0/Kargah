from kargah.adapters.gitlab.githost import GitLabHost

BASE = "projects/g%2Fp/merge_requests"
NOTE = {"id": 1, "body": "fix this", "created_at": "2026-01-01T10:00:00.000Z", "resolvable": True, "resolved": False,
        "author": {"id": 2, "username": "owner"}}


class Http:
    def __init__(self, replies):
        self.replies, self.calls = replies, []

    def request(self, method, path, *, params=None, json=None):
        self.calls.append((method, path, params, json))
        return self.replies[(method, path)]


MR = {"iid": 3, "web_url": "https://x/3", "state": "merged", "title": "Draft: t",
      "created_at": "2026-01-01T10:00:00.000Z", "merged_at": "2026-01-02T10:00:00.000Z"}


def host(replies):
    return GitLabHost(Http({("GET", BASE): [MR], **replies}), "g/p", "https://x"), None


def test_find_mr_asks_for_every_state_and_reads_the_times():
    h, _ = host({})
    view = h.find_mr("kargah/1")
    assert (view.iid, view.state, view.url) == (3, "merged", "https://x/3") and view.merged_at.day == 2
    assert h._http.calls[0][2]["state"] == "all"


def test_find_mr_without_a_branch_mr_is_none():
    http = Http({("GET", BASE): []})
    assert GitLabHost(http, "g/p", "https://x").find_mr("none") is None


def test_open_discussions_keep_only_unresolved_threads_not_started_by_the_bot():
    bot = {**NOTE, "author": {"id": 9, "username": "bot"}}
    rows = [{"id": "d1", "notes": [{**NOTE, "position": {"new_path": "src/a.py", "new_line": 4}}]},
            {"id": "d2", "notes": [{**NOTE, "resolved": True}]},
            {"id": "d3", "notes": [bot, NOTE]},
            {"id": "d4", "notes": [{**NOTE, "resolvable": False}]},
            {"id": "d5", "notes": [NOTE]}]
    h, _ = host({("GET", f"{BASE}/3/discussions"): rows, ("GET", "user"): {"id": 9, "username": "bot"}})
    found = h.open_discussions("kargah/1")
    assert [(d.id, d.path, d.line) for d in found] == [("d1", "src/a.py", 4), ("d5", None, None)]


def test_resolve_replies_in_the_thread_then_resolves_it():
    h, _ = host({("POST", f"{BASE}/3/discussions/d1/notes"): {}, ("PUT", f"{BASE}/3/discussions/d1"): {}})
    h.resolve_discussion("kargah/1", "d1", "Addressed in abc.")
    assert [(c[0], c[3]) for c in h._http.calls[1:]] == [("POST", {"body": "Addressed in abc."}),
                                                         ("PUT", {"resolved": True})]


def test_notes_skip_system_notes_and_commits_give_author_emails():
    h, _ = host({("GET", f"{BASE}/3/notes"): [{**NOTE, "system": True}, {**NOTE, "id": 7}],
                 ("GET", f"{BASE}/3/commits"): [{"author_email": "a@x"}, {"author_email": "b@x"}]})
    assert [c.id for c in h.mr_notes("kargah/1")] == [7]
    assert h.commit_authors("kargah/1") == ["a@x", "b@x"]

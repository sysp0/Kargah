import io
import urllib.error

import pytest

from kargah.adapters.gitlab.http import UrllibHttp
from kargah.errors import TrackerError


class Reply(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def client(monkeypatch, outcomes):
    calls = []

    def fake_urlopen(req, timeout):
        calls.append(req.get_method())
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return Reply(outcome)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    return UrllibHttp("https://gl", "secret", sleep=lambda s: None), calls


def test_a_read_that_times_out_is_retried(monkeypatch):
    http, calls = client(monkeypatch, [TimeoutError("slow"), TimeoutError("slow"), b'[{"a": 1}]'])
    assert http.request("GET", "issues") == [{"a": 1}] and calls == ["GET"] * 3


def test_a_server_error_on_a_read_is_retried_but_a_client_error_is_not(monkeypatch):
    err = lambda code: urllib.error.HTTPError("u", code, "x", {}, io.BytesIO(b"no"))  # noqa: E731
    http, calls = client(monkeypatch, [err(502), b"{}"])
    assert http.request("GET", "issues") == {} and len(calls) == 2
    http, calls = client(monkeypatch, [err(404)])
    with pytest.raises(TrackerError):
        http.request("GET", "issues")
    assert len(calls) == 1


def test_a_write_is_never_repeated(monkeypatch):
    http, calls = client(monkeypatch, [TimeoutError("slow"), b"{}"])
    with pytest.raises(TrackerError):
        http.request("POST", "issues/1/notes", json={"body": "x"})
    assert calls == ["POST"]


def test_gives_up_after_three_attempts_without_leaking_the_token(monkeypatch):
    http, calls = client(monkeypatch, [TimeoutError("slow")] * 3)
    with pytest.raises(TrackerError) as info:
        http.request("GET", "issues")
    assert len(calls) == 3 and "secret" not in str(info.value)

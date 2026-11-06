"""Proof: new tests pass on the change, fail on the base, and a broken test run is not mistaken for a failure."""
from contextlib import contextmanager
from pathlib import Path

from kargah.domain.config import ProjectConfig
from kargah.ports.shell import CommandResult
from kargah.tasks.proof import Proof

HEAD, BASE = Path("/head"), Path("/base")


class Ws:
    root = HEAD

    def changed_files(self, base):
        return ["src/x.py", "tests/test_x.py"]

    @contextmanager
    def base_variant(self, base, keep_paths):
        yield BASE


class Shell:
    def __init__(self, head_rc, base_rc):
        self.rc = {HEAD: head_rc, BASE: base_rc}

    def run(self, command, cwd, timeout_seconds):
        return CommandResult(self.rc[cwd], "last lines")


def proof(head_rc, base_rc, cfg=None):
    return Proof(Ws(), Shell(head_rc, base_rc), cfg or ProjectConfig()).check("main")


def test_failing_on_base_and_passing_on_head_is_proof():
    assert proof(0, 1).ok
    assert proof(0, 2).ok          # pytest: the new test cannot import what the change adds


def test_passing_on_base_is_not_proof():
    result = proof(0, 0)
    assert not result.ok and "pass without your change" in result.reason


def test_a_broken_run_on_base_is_not_proof():
    result = proof(0, 5)           # pytest: no tests collected
    assert not result.ok and "could not run on the base" in result.reason and "exit 5" in result.reason


def test_new_tests_must_pass_on_the_change():
    result = proof(1, 1)
    assert not result.ok and "do not pass with your change" in result.reason


def test_fail_codes_come_from_the_config():
    assert not proof(0, 2, ProjectConfig(proof_fail_codes=(1,))).ok

"""The proof that a change is guarded: its new tests must FAIL on the base commit and are checked there."""
from __future__ import annotations

import shlex
from dataclasses import dataclass

from kargah.domain.config import ProjectConfig
from kargah.ports.shell import Shell
from kargah.ports.workspace import Workspace


@dataclass(frozen=True)
class ProofResult:
    ok: bool
    reason: str = ""


class Proof:
    def __init__(self, workspace: Workspace, shell: Shell, config: ProjectConfig) -> None:
        self._ws, self._shell, self._cfg = workspace, shell, config

    def check(self, base: str) -> ProofResult:
        tests = [f for f in self._ws.changed_files(base)
                 if any(f.startswith(p) for p in self._cfg.proof_test_paths)]
        if not tests:
            return ProofResult(False, "no test was added or changed: every change needs a test that guards it")
        command = f"{self._cfg.proof_command} {' '.join(shlex.quote(t) for t in tests)}"
        timeout = self._cfg.build_timeout_seconds
        here = self._shell.run(command, self._ws.root, timeout)
        if here.returncode != 0:
            return ProofResult(False, f"the new tests do not pass with your change (exit {here.returncode}):\n"
                                      f"{here.tail}")
        with self._ws.base_variant(base, tests) as checkout:
            result = self._shell.run(command, checkout, timeout)
        if result.returncode == 0:
            return ProofResult(False, "the new tests pass without your change, so they do not guard it")
        if result.returncode not in self._cfg.proof_fail_codes:
            # a crash, a usage error or "no tests collected" says nothing about the change
            return ProofResult(False, f"the new tests could not run on the base commit (exit {result.returncode}); "
                                      f"they must fail there by assertion or missing code:\n{result.tail}")
        return ProofResult(True)

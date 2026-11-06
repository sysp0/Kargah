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
        # shortcut: any non-zero exit counts as "fails on base" (also a broken setup); upgrade: tell them apart
        with self._ws.base_variant(base, tests) as checkout:
            result = self._shell.run(command, checkout, self._cfg.build_timeout_seconds)
        if result.returncode == 0:
            return ProofResult(False, "the new tests pass without your change, so they do not guard it")
        return ProofResult(True)

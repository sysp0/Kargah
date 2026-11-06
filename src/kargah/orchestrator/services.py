"""Everything the engine needs, handed in from outside (dependency injection)."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from kargah.domain.agents import AgentSpec, Definition
from kargah.ports.githost import GitHost
from kargah.ports.harness import Harness
from kargah.ports.logsink import LogSink
from kargah.ports.runstore import RunStore
from kargah.ports.shell import Shell
from kargah.ports.tracker import Tracker
from kargah.ports.workspace import Workspace


@dataclass(frozen=True)
class Services:
    tracker: Tracker
    githost: GitHost
    workspace: Workspace
    harness_for: Callable[[AgentSpec], Harness]
    shell: Shell
    log: LogSink
    runs: RunStore
    load_definition: Callable[[Workspace], Definition]     # reads the default branch, never the ticket branch
    clock: Callable[[], datetime]
    run_id: Callable[[], str]

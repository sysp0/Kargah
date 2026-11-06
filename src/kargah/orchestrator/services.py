"""Everything the engine needs, handed in from outside (dependency injection)."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from kargah.domain.config import ProjectConfig
from kargah.ports.githost import GitHost
from kargah.ports.harness import Harness
from kargah.ports.logsink import LogSink
from kargah.ports.shell import Shell
from kargah.ports.tracker import Tracker
from kargah.ports.workspace import Workspace


@dataclass(frozen=True)
class Services:
    tracker: Tracker
    githost: GitHost
    workspace: Workspace
    builder: Harness
    reviewer: Harness
    shell: Shell
    log: LogSink
    load_config: Callable[[Path], ProjectConfig]
    clock: Callable[[], datetime]
    run_id: Callable[[], str]

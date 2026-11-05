"""Settings from kargah.toml at the repo root. Every number and command lives there, not in code."""

from __future__ import annotations

import os
import subprocess
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


class ConfigError(Exception):
    pass


def repo_root(start: Path | None = None) -> Path:
    env = os.environ.get("DEVCHAIN_ROOT")
    if env:
        return Path(env).resolve()
    try:
        out = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=start or Path.cwd(),
                             capture_output=True, text=True, check=True).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise ConfigError("not inside a git repository (set DEVCHAIN_ROOT)") from exc
    return Path(out)


@dataclass
class Config:
    root: Path
    data: dict = field(default_factory=dict)

    def get(self, dotted: str, default=None):
        node = self.data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def need(self, dotted: str):
        value = self.get(dotted)
        if value is None:
            raise ConfigError(f"devchain.toml: missing setting {dotted}")
        return value

    @property
    def runs_dir(self) -> Path:
        return self.root / self.get("paths.runs", ".devchain/runs")

    def codex_bin(self) -> list[str]:
        return (os.environ.get("DEVCHAIN_CODEX_BIN") or self.get("codex.bin", "codex")).split()

    def claude_bin(self) -> list[str]:
        return (os.environ.get("DEVCHAIN_CLAUDE_BIN") or self.get("claude.bin", "claude")).split()

    def gh_bin(self) -> list[str]:
        return (os.environ.get("DEVCHAIN_GH_BIN") or self.get("forge.gh_bin", "gh")).split()

    def glab_bin(self) -> list[str]:
        return (os.environ.get("DEVCHAIN_GLAB_BIN") or self.get("forge.glab_bin", "glab")).split()


def load(root: Path | None = None) -> Config:
    root = root or repo_root()
    path = root / "devchain.toml"
    if not path.is_file():
        raise ConfigError(f"no devchain.toml at {root}")
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"devchain.toml: {exc}") from exc
    return Config(root=root, data=data)

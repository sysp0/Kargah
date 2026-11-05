"""A plan folder read as data: its parts, every row with its columns, and the fix rows of issues.md.

docs/devchain-plan/<plan>/NN-<part>.md holds a table `| Pn | Title | Depends | Touches | files | acceptance | Risk |
You see |`; the columns are found by their header, so an older table without Depends, Touches, Risk or You see still
reads. A part without a Depends column makes every row depend on the row before it (slower, never too early). A part
without a Touches column uses the paths of its files cell. <plan>/issues.md holds the fix rows I<n> written from
issues. A part may name its QA scenarios on one line, `QA: <suite> S1 S2 ...`.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import gitops
from .config import Config

ROW_RE = re.compile(r"^\|\s*([PI]\d+[a-z]?)\s*\|")
HEAD_RE = re.compile(r"^\|\s*Pn\s*\|", re.I)
ID_RE = re.compile(r"\b([PI]\d+[a-z]?)\b")
QA_RE = re.compile(r"^QA:\s*(\S+)((?:\s+S\d+[a-z]?)*)\s*$", re.M)
PATH_RE = re.compile(r"^[\w./-]*(/[\w.-]+|\.\w{1,5})$")
FIX_FILE = "issues.md"


@dataclass
class Row:
    id: str
    part: str                      # part file name (01-x.md), or issues.md for a fix row
    cells: dict = field(default_factory=dict)   # lower-case header -> cell text
    line: str = ""
    depends: list = field(default_factory=list)
    touches: set = field(default_factory=set)

    @property
    def title(self) -> str:
        return self.cells.get("title", "")

    @property
    def files(self) -> list[str]:
        return [t for t in re.findall(r"`([^`]+)`", self.cells.get("files", "")) if PATH_RE.match(t)]

    @property
    def acceptance(self) -> str:
        return self.cells.get("acceptance", "")

    @property
    def fix(self) -> bool:
        return self.id.startswith("I")

    @property
    def issue(self) -> int | None:
        """The issue a fix row comes from (I52b -> 52)."""
        m = re.match(r"^I(\d+)", self.id)
        return int(m.group(1)) if m else None

    @property
    def ui(self) -> bool:
        return self.title.startswith("UI:")

    @property
    def hash(self) -> str:
        """Changes when any cell of the row changes: the task issue's text is then written again."""
        text = "|".join(f"{k}={' '.join(v.split())}" for k, v in sorted(self.cells.items()))
        return hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]


@dataclass
class Plan:
    stage: str
    folder: str                    # repo-relative plan folder
    rows: list = field(default_factory=list)    # plan rows in run order: part files sorted, then table order
    fixes: list = field(default_factory=list)   # fix rows of issues.md, in file order
    parts: list = field(default_factory=list)   # part file names, sorted

    def get(self, row_id: str) -> Row | None:
        return next((r for r in [*self.rows, *self.fixes] if r.id == row_id), None)

    def path_of(self, row_id: str) -> str:
        """Repo-relative file of the row: its part file, or issues.md for a fix row."""
        row = self.get(row_id)
        return f"{self.folder}/{row.part if row else FIX_FILE}"

    def in_part(self, part: str) -> list[Row]:
        return [r for r in self.rows if r.part == part]


def folder_of(cfg: Config, stage: str) -> str:
    return f"{cfg.get('feature.plans_dir', 'docs/devchain-plan')}/{stage}"


def split_cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def table(path: Path) -> tuple[list[Row], bool, bool]:
    """(rows, has a Depends column, has a Touches column) of the package table in one file."""
    if not path.is_file():
        return [], False, False
    heads: list[str] = []
    out: list[Row] = []
    seen_depends = seen_touches = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if HEAD_RE.match(line):
            heads = [h.lower() for h in split_cells(line)]
            seen_depends |= "depends" in heads
            seen_touches |= "touches" in heads
            continue
        m = ROW_RE.match(line)
        if not m:
            continue
        cells = split_cells(line)
        names = heads or ["pn", "title", "files", "acceptance"]
        values = {names[i]: cells[i] for i in range(1, min(len(cells), len(names)))}
        row = Row(id=m.group(1), part=path.name, cells=values, line=line)
        if "depends" in heads:
            row.depends = [d for d in ID_RE.findall(values.get("depends", "")) if d != row.id]
        if "touches" in heads:
            row.touches = {t.strip(" `") for t in re.split(r"[,;]", values.get("touches", ""))
                           if t.strip(" `-") and t.strip(" `").lower() != "none"}
        out.append(row)
    return out, seen_depends, seen_touches


def read(cfg: Config, stage: str) -> Plan | None:
    """The plan folder <feature.plans_dir>/<stage>/, or None when it is not one. 00-*.md is the overview. A row id
    used twice raises ValueError."""
    rel = folder_of(cfg, stage)
    folder = cfg.root / rel
    if not stage or not folder.is_dir():
        return None
    plan = Plan(stage=stage, folder=rel)
    seen: dict[str, str] = {}
    previous: str | None = None
    for part in sorted(folder.glob("[0-9][0-9]-*.md")):
        if part.name.startswith("00-"):
            continue
        rows, has_depends, has_touches = table(part)
        if rows:
            plan.parts.append(part.name)
        for row in rows:
            if row.id in seen:
                raise ValueError(f"row {row.id} is in {seen[row.id]} and {rel}/{part.name}")
            seen[row.id] = f"{rel}/{part.name}"
            if not has_depends and previous:
                row.depends = [previous]
            if not has_touches:
                row.touches = set(row.files)
            previous = row.id
            plan.rows.append(row)
    fixes, _, has_touches = table(folder / FIX_FILE)
    for row in fixes:
        if not has_touches:
            row.touches = set(row.files)
    plan.fixes = fixes
    return plan


def qa_line(part: Path) -> tuple[str, list[str]] | None:
    """(suite, scenarios) from the part's `QA:` line, or None."""
    m = QA_RE.search(part.read_text(encoding="utf-8")) if part.is_file() else None
    return (m.group(1), m.group(2).split()) if m else None


def title(part: Path) -> str:
    """The first heading of a part file, without its '#'."""
    for line in part.read_text(encoding="utf-8").splitlines() if part.is_file() else []:
        if line.startswith("#"):
            return line.lstrip("#").strip()
    return part.stem


def resolve_part(value: str, part_files: list[str]) -> str | None:
    """"02", "2", "02-registry-catalog" or "02-registry-catalog.md" -> the part file name."""
    value = value.strip().removesuffix(".md")
    m = re.match(r"^(\d+)", value)
    for name in part_files:
        stem = name.removesuffix(".md")
        if value == stem or (m and value == m.group(1) and int(stem.split("-")[0]) == int(m.group(1))):
            return name
    return None


def changed_rows(root: Path, paths: list[str]) -> list[str]:
    """Row ids whose line differs between HEAD and the working tree in these plan files."""
    out: list[str] = []
    for rel in paths:
        old = gitops.git(root, "show", f"HEAD:{rel}", check=False)
        new = (root / rel).read_text(encoding="utf-8") if (root / rel).is_file() else ""
        before = {m.group(1): line for line in old.splitlines() if (m := ROW_RE.match(line))}
        after = {m.group(1): line for line in new.splitlines() if (m := ROW_RE.match(line))}
        out += [r for r in dict.fromkeys([*after, *before]) if before.get(r) != after.get(r) and r not in out]
    return out

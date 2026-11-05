"""`dev try <part>`: the app of one finished part in its own folder, ports and database, for the owner to test.

A detached git worktree (setting try.dir) is checked out at the last commit of the part's packages, so what the run
commits later never reaches it; `--fixed` also takes the commits of the part's issue rows. The ignored files the
stack needs (try.links: the .env, node_modules) come from the main tree: a directory as a hard-link copy, a file as a
symlink. The QA stack then starts there with try.env (other ports and database than ./dev qa).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from . import gitops
from . import plan as plan_mod
from .config import Config
from .feature import plan_branch_name, plan_folder, row_titles

DEFAULT_ENV = {"QA_API_PORT": "8050", "QA_INGEST_PORT": "8051", "QA_UI_PORT": "5183"}
DEFAULT_LINKS = ["project-a/.env", "project-ui/ui/node_modules"]


class TryError(Exception):
    pass


def folder(cfg: Config) -> Path:
    return (cfg.root / str(cfg.get("try.dir", f"../{cfg.root.name}-try"))).resolve()


def environment(cfg: Config) -> dict:
    return {k: str(v) for k, v in {**DEFAULT_ENV, **(cfg.get("try.env") or {})}.items()}


def package_commits(root: Path, ref: str, base: str) -> list[tuple[str, str]]:
    """(short sha, package) of every package commit on ref after base, newest first."""
    out = gitops.git(root, "log", f"origin/{base}..{ref}", "--format=%h%x00%B%x1e", check=False)
    found = []
    for record in out.split("\x1e"):
        if "\x00" not in record:
            continue
        sha, body = record.strip().split("\x00", 1)
        m = re.search(r"^Package:\s*(\S+)\s*$", body, re.M)
        if m:
            found.append((sha, m.group(1)))
    return found


def plan_ref(cfg: Config, stage: str) -> str:
    """The plan branch as on origin (fetched), else the local branch, else HEAD."""
    name = plan_branch_name(cfg, stage)
    gitops.git(cfg.root, "fetch", "-q", "origin", name, check=False)
    for ref in (f"origin/{name}", name):
        if gitops.git(cfg.root, "rev-parse", "--verify", "-q", ref, check=False):
            return ref
    return "HEAD"


def pick(cfg: Config, stage: str, part_arg: str, fixed: bool) -> dict:
    """Which commit to test: the newest commit of the part's packages (and of its issue rows with --fixed)."""
    parts = plan_folder(cfg, stage)
    if not parts:
        raise TryError(f"{stage} is not a plan folder with package rows")
    names = sorted({Path(f).name for f in parts.values()})
    part = plan_mod.resolve_part(part_arg, names)
    if not part:
        raise TryError(f"no part {part_arg} in plan {stage} ({', '.join(names)})")
    rel = str(Path(next(iter(parts.values()))).parent)
    wanted = {p for p, f in parts.items() if Path(f).name == part}
    if fixed:
        wanted |= {r.id for r in plan_mod.read(cfg, stage).fixes if r.cells.get("part") == part}
    ref = plan_ref(cfg, stage)
    commits = package_commits(cfg.root, ref, cfg.get("git.base", "main"))
    at = next((i for i, (_, pkg) in enumerate(commits) if pkg in wanted), None)
    if at is None:
        raise TryError(f"no package of part {part} is committed on {ref} yet")
    included = [pkg for _, pkg in commits[at:]]
    order = {name: i for i, name in enumerate(names)}
    later = [p for p in included if p in parts and order[Path(parts[p]).name] > order[part]]
    return {"part": part, "rel": rel, "sha": commits[at][0], "ref": ref, "later": sorted(set(later)),
            "missing": sorted(p for p in wanted if p.startswith("P") and p not in included),
            "issue_rows": sorted(p for p in included if p.startswith("I"))}


def link(src: Path, dst: Path) -> None:
    if dst.exists() or dst.is_symlink() or not src.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        proc = subprocess.run(["cp", "-al", str(src), str(dst)], capture_output=True, text=True)
        if proc.returncode == 0:
            return
        shutil.rmtree(dst, ignore_errors=True)   # another file system: a symlink instead
    os.symlink(src, dst)


def checkout(cfg: Config, sha: str) -> Path:
    where = folder(cfg)
    if (where / ".git").exists():
        if gitops.git(where, "status", "--porcelain", "--untracked-files=no", check=False):
            raise TryError(f"{where} has local changes; commit or remove them first")
        gitops.git(where, "checkout", "-q", "--detach", sha)
    else:
        if where.exists() and any(where.iterdir()):
            raise TryError(f"{where} exists and is not a worktree of this repo; set try.dir to another folder")
        gitops.git(cfg.root, "worktree", "prune", check=False)
        gitops.git(cfg.root, "worktree", "add", "-q", "--detach", str(where), sha)
    for rel in cfg.get("try.links", DEFAULT_LINKS):
        link(cfg.root / rel, where / rel)
    return where


def scenarios(cfg: Config, rel: str, part: str) -> list[str]:
    """`S1 title` lines of the part's QA scenarios, from the suite file."""
    qa = plan_mod.qa_line(cfg.root / rel / part)
    if not qa:
        return []
    suite = cfg.root / cfg.get("qa.scenarios_dir", "docs/qa") / f"{qa[0]}.md"
    heads = {}
    for line in suite.read_text(encoding="utf-8").splitlines() if suite.is_file() else []:
        if m := re.match(r"^##\s+(S\d+[a-z]?)\b\s*(.*)$", line):
            heads[m.group(1)] = m.group(2).strip(" :-")
    return [f"{s} {heads.get(s, '')}".strip() for s in qa[1]] + [f"(expected values: {suite.relative_to(cfg.root)})"]


def run_stack(cfg: Config, where: Path, setting: str, default: str, extra: dict | None = None) -> int:
    command = str(cfg.get(setting, default))
    env = {**os.environ, **environment(cfg), "DEVCHAIN_ROOT": str(cfg.root), **(extra or {})}   # the main tree
    return subprocess.run(["bash", "-c", command], cwd=where, env=env).returncode


def start(cfg: Config, stage: str, part_arg: str, fixed: bool, seed: str | None = None) -> int:
    seeds = [str(x) for x in cfg.get("qa.seeds", ["shop"])]
    seed = seed or seeds[0]
    if seed not in seeds:
        raise TryError(f"no seed {seed} (qa.seeds: {', '.join(seeds)})")
    choice = pick(cfg, stage, part_arg, fixed)
    where = checkout(cfg, choice["sha"])
    part = choice["part"]
    print(f"devchain: try {part} of plan {stage} at {choice['sha']} ({choice['ref']}) in {where}, seed {seed}")
    if choice["missing"]:
        print(f"devchain: not built yet: {' '.join(choice['missing'])}")
    if choice["issue_rows"]:
        print(f"devchain: issue rows included: {' '.join(choice['issue_rows'])}")
    if choice["later"]:
        print(f"devchain: this commit also holds later packages: {' '.join(choice['later'])}")
    rc = run_stack(cfg, where, "try.up", "make -s -C project-a qa-down && make -s -C project-a qa-up",
                   {"QA_SEED": seed})
    if rc != 0:
        print(f"devchain: the stack did not start (exit {rc}); ./dev try stop, then try again", flush=True)
        return 3
    env = environment(cfg)
    titles = row_titles(cfg.root / choice["rel"] / part)
    print(f"\nTest it:   http://localhost:{env['QA_UI_PORT']}   (api http://127.0.0.1:{env['QA_API_PORT']})")
    print(f"Part:      {part}  {plan_mod.title(cfg.root / choice['rel'] / part)}")
    print("Packages:  " + ", ".join(f"{p} {t}" for p, t in titles.items())[:600])
    lines = scenarios(cfg, choice["rel"], part) if seed == seeds[0] else []   # the QA suites use the first seed
    if lines:
        print("Scenarios: " + "\n           ".join(lines))
    print(f"Issue:     Plan {stage} · Part {part.split('-')[0]} · Tested commit {choice['sha']} · Seed {seed}")
    print("Then:      comment on the task issues, or open an issue with the feedback form   ·   ./dev try stop")
    return 0


def stop(cfg: Config) -> int:
    where = folder(cfg)
    if not (where / ".git").exists():
        print("devchain: no try folder")
        return 0
    return 0 if run_stack(cfg, where, "try.down", "make -s -C project-a qa-down") == 0 else 3

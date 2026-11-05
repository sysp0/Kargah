"""The few git operations the chain needs. Never rewrites history, never force-pushes."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


class GitError(Exception):
    pass


def git(root: Path, *args: str, check: bool = True, strip: bool = True) -> str:
    proc = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise GitError(f"git {' '.join(args)}: {proc.stderr.strip() or proc.stdout.strip()}")
    return proc.stdout.strip() if strip else proc.stdout


def branch(root: Path) -> str:
    return git(root, "rev-parse", "--abbrev-ref", "HEAD")


def changed(root: Path) -> list[str]:
    """Paths changed in the working tree, untracked included (git status --porcelain)."""
    out = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=root,
                         capture_output=True, text=True).stdout
    paths = []
    for line in out.splitlines():
        if len(line) > 3:
            path = line[3:]
            paths.append(path.split(" -> ")[-1].strip('"'))
    return paths


def is_clean(root: Path) -> bool:
    return not changed(root)


def remote_url(root: Path, remote: str = "origin") -> str:
    return git(root, "remote", "get-url", remote, check=False)


def pr_url(root: Path, branch_name: str) -> str | None:
    match = re.search(r"github\.com[:/](.+?)(?:\.git)?/?$", remote_url(root))
    return f"https://github.com/{match.group(1)}/pull/new/{branch_name}" if match else None


def remote_branch_exists(root: Path, name: str, remote: str = "origin") -> bool:
    return bool(git(root, "ls-remote", "--heads", remote, name, check=False))


def fresh_branch(root: Path, name: str, base: str = "main", remote: str = "origin") -> None:
    """Create `name` from the latest remote base. Refuses a dirty tree or a branch that already exists remotely."""
    if not is_clean(root):
        raise GitError("working tree is not clean")
    if remote_branch_exists(root, name, remote):
        raise GitError(f"branch {name} already exists on {remote}; use --branch current or another name")
    git(root, "fetch", "-q", remote, base)
    git(root, "checkout", "-q", "-B", name, f"{remote}/{base}")


def plan_branch(root: Path, name: str, base: str = "main", remote: str = "origin") -> None:
    """Check out the one branch of a plan: the remote branch when it exists, with the latest base merged in (plan
    fixes written on main), else a new branch from the remote base."""
    if not is_clean(root):
        raise GitError("working tree is not clean (use resume to keep and check it)")
    git(root, "fetch", "-q", remote, base)
    if remote_branch_exists(root, name, remote):
        git(root, "fetch", "-q", remote, name)
        git(root, "checkout", "-q", "-B", name, f"{remote}/{name}")
        git(root, "merge", "-q", "--no-edit", f"{remote}/{base}")
    else:
        git(root, "checkout", "-q", "-B", name, f"{remote}/{base}")


def merge_base_branch(root: Path, base: str = "main", remote: str = "origin") -> None:
    """Bring the latest base (plan fixes written on main) into the checked-out branch with a merge commit."""
    git(root, "fetch", "-q", remote, base)
    git(root, "merge", "-q", "--no-edit", f"{remote}/{base}")


def merge_remote_branch(root: Path, name: str, remote: str = "origin") -> None:
    """Bring commits pushed to origin/<name> by someone else (a plan fix from the thread) into the local branch."""
    if not remote_branch_exists(root, name, remote):
        return
    git(root, "fetch", "-q", remote, name)
    git(root, "merge", "-q", "--no-edit", f"{remote}/{name}")


def packages_on_branch(root: Path, base: str = "main", remote: str = "origin") -> set[str]:
    """Package ids already committed on this branch (commit trailer `Package: P3`)."""
    out = git(root, "log", f"{remote}/{base}..HEAD", "--format=%B", check=False)
    return set(re.findall(r"^Package:\s*(\S+)\s*$", out, re.M))


def commit_paths(root: Path, message: str, *paths: str) -> str:
    git(root, "add", "--", *paths)
    git(root, "commit", "-q", "-m", message, "--", *paths)
    return git(root, "rev-parse", "--short", "HEAD")


def commit_all(root: Path, message: str) -> str:
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", message)
    return git(root, "rev-parse", "--short", "HEAD")


def push(root: Path, name: str, remote: str = "origin") -> None:
    """Push the branch. When someone else pushed to it meanwhile (a fix from the thread), merge theirs and push
    again; a merge that conflicts is undone and its error stands."""
    try:
        git(root, "push", "-q", "-u", remote, name)
    except GitError:
        if not is_clean(root) or not remote_branch_exists(root, name, remote):
            raise
        try:
            merge_remote_branch(root, name, remote)
        except GitError:
            git(root, "merge", "--abort", check=False)
            raise
        git(root, "push", "-q", "-u", remote, name)

import json
import subprocess
import sys
from pathlib import Path

import pytest

FAKES = Path(__file__).parent / "fakes"

TOML = """
[paths]
runs = ".devchain/runs"
progress = "docs/progress.md"
[models]
review = "fake-review"
triage = "fake-triage"
[loop]
max_fix_rounds = 2
test_cmd = "true"
[git]
base = "main"
branch_prefix = "codex/"
push = true
github_repo = "acme/repo"
[codex]
flags = "--json"
limit_wait_seconds = 1
limit_max_wait_seconds = 1
limit_margin_seconds = 0
[claude]
flags = ""
[accept]
no_test_ok = '^(docs/|qa/|ui/)'
[[accept.checks]]
match = 'tests/test_[^/]*\\.py$'
run = "test -s {path}"
[qa]
dir = "qa"
scenarios_dir = "docs/qa"
bugs = "docs/qa/bugs.md"
branch_prefix = "qa/"
codex_may_change = '^qa/'
run = "cd qa && python3 ../check_spec.py {spec}"
results_dir = "test-results"
restart = "echo restarted"
"""

CHECK_SPEC = """import sys
from pathlib import Path
spec = Path(sys.argv[1]).read_text()
app_ok = Path('../app/fixed.txt').exists()
ok = 'OK' in spec and ('NEEDS_APP' not in spec or app_ok)
out = Path('test-results/case/error-context.md')
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text('page snapshot')
print('1 passed' if ok else '1 failed')
sys.exit(0 if ok else 1)
"""


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


class Repo:
    def __init__(self, root: Path, fake: Path):
        self.root, self.fake = root, fake

    def codex(self, *actions):
        (self.fake / "codex.json").write_text(json.dumps(list(actions)))

    def claude(self, *actions):
        (self.fake / "claude.json").write_text(json.dumps(list(actions)))

    def calls(self, agent: str) -> int:
        path = self.fake / f"{agent}.count"
        return int(path.read_text()) if path.exists() else 0

    def argv(self, agent: str, n: int) -> str:
        return (self.fake / f"{agent}-argv-{n}.txt").read_text()

    def prompt(self, agent: str, n: int) -> str:
        return (self.fake / f"{agent}-prompt-{n}.txt").read_text()

    def events(self):
        runs = sorted((self.root / ".devchain/runs").iterdir())
        return [json.loads(line) for line in (runs[-1] / "events.jsonl").read_text().splitlines()]


@pytest.fixture
def repo(tmp_path, monkeypatch):
    origin = tmp_path / "origin.git"
    root = tmp_path / "work"
    fake = tmp_path / "fake"
    fake.mkdir()
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "t@example.test")
    git(root, "config", "user.name", "t")
    (root / "devchain.toml").write_text(TOML)
    (root / ".gitignore").write_text(".devchain/\nqa/test-results/\n")
    (root / "docs/plan").mkdir(parents=True)
    (root / "docs/plan/stage.md").write_text("| Pn | Title | files | acceptance |\n|---|---|---|---|\n"
                                            "| P1 | One | `src/a.py` | test |\n| P2 | Two | `src/b.py` | test |\n")
    (root / "docs/progress.md").write_text("## Current\nBlocked: none\n")
    (root / "docs/qa").mkdir()
    (root / "docs/qa/suite.md").write_text("# Suite\n## Data\nfixed\n## S1 First\nsee OK\n## S2 Second\nalso\n")
    (root / "qa/tests").mkdir(parents=True)
    (root / "qa/tests/.keep").write_text("")
    (root / "check_spec.py").write_text(CHECK_SPEC)
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "init")
    git(root, "remote", "add", "origin", str(origin))
    git(root, "push", "-q", "-u", "origin", "main")
    monkeypatch.setenv("DEVCHAIN_ROOT", str(root))
    monkeypatch.setenv("FAKE_DIR", str(fake))
    monkeypatch.setenv("DEVCHAIN_CODEX_BIN", f"{sys.executable} {FAKES / 'fake_codex.py'}")
    monkeypatch.setenv("DEVCHAIN_CLAUDE_BIN", f"{sys.executable} {FAKES / 'fake_claude.py'}")
    monkeypatch.setenv("DEVCHAIN_GH_BIN", f"{sys.executable} {FAKES / 'fake_gh.py'}")
    monkeypatch.setenv("DEVCHAIN_GLAB_BIN", f"{sys.executable} {FAKES / 'fake_glab.py'}")
    monkeypatch.chdir(root)
    return Repo(root, fake)

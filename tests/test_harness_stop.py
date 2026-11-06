import sys
import time

from kargah.adapters.claude import ClaudeHarness
from kargah.adapters.codex import CodexHarness
from kargah.ports.harness import HarnessRequest


def sleeper(tmp_path):
    script = tmp_path / "agent"
    script.write_text(f"#!{sys.executable}\nimport time\ntime.sleep(60)\n")
    script.chmod(0o755)
    return str(script)


def test_codex_and_claude_stop_when_asked(tmp_path, monkeypatch):
    monkeypatch.setattr("kargah.adapters.process.GRACE_SECONDS", 2)
    for harness in (CodexHarness(sleeper(tmp_path)), ClaudeHarness(sleeper(tmp_path))):
        started = time.monotonic()
        reply = harness.run(HarnessRequest("build", "x", tmp_path, 120, should_stop=lambda: True))
        assert reply.stopped and not reply.ok and not reply.limited
        assert time.monotonic() - started < 15

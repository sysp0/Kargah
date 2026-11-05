"""Structure guard: no module over MAX_LINES. Legacy v1 files are capped at today's size and must only shrink."""
from pathlib import Path

MAX_LINES = 300
LEGACY_CAPS = {  # shortcut: remove an entry when the file is split; never raise a cap
    "cli.py": 313,
    "feature.py": 736,
    "forge.py": 392,
    "loop.py": 764,
    "tui.py": 336,
}
SRC = Path(__file__).resolve().parents[1] / "src" / "kargah"


def test_no_module_over_the_line_limit():
    too_long = {}
    for path in SRC.rglob("*.py"):
        cap = LEGACY_CAPS.get(path.relative_to(SRC).as_posix(), MAX_LINES)
        lines = len(path.read_text(encoding="utf-8").splitlines())
        if lines > cap:
            too_long[path.relative_to(SRC).as_posix()] = f"{lines} > {cap}"
    assert not too_long, too_long

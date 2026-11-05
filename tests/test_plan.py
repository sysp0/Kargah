import pytest

from kargah import config, plan

NEW = """# Part 02: segments

QA: segments S1 S2

## Packages

| Pn | Title | Depends | Touches | files | acceptance | Risk | You see |
|---|---|---|---|---|---|---|---|
| P3 | Segment list | P1 | api:/v1/segments, `table:segments` | `ME/app/x.py`, `run()` | `test_p3` | low | the list |
| P4 | UI: segment page | P3, P9 | api:/v1/segments | `ui/src/a.jsx` | `test_p4` | mid | a page |
| P5 | Other | - | none | `b.py` | `test_p5` | low | - |
"""
OLD = """# Part 01: old

| Pn | Title | files | acceptance |
|---|---|---|---|
| P1 | One | `src/a.py`, `make` | test |
| P2 | Two | `src/b.py` | test |
"""
FIXES = """# Issue rows

| Pn | Title | files | acceptance | issue | part | package | seed |
|---|---|---|---|---|---|---|---|
| I52 | #52 wrong total | `src/a.py` | spec | #52 | 01-old.md | P1 | shop |
| I52b | #52 second | `src/b.py` | spec | #52 | 01-old.md | P2 | shop |
"""


def write(repo, files):
    folder = repo.root / "docs/devchain-plan/x"
    folder.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (folder / name).write_text(text)
    return config.load(repo.root)


def test_rows_are_read_by_their_headers(repo):
    cfg = write(repo, {"00-overview.md": "| P99 | no |\n", "01-old.md": OLD, "02-new.md": NEW, "issues.md": FIXES})
    p = plan.read(cfg, "x")
    assert [r.id for r in p.rows] == ["P1", "P2", "P3", "P4", "P5"]
    assert p.parts == ["01-old.md", "02-new.md"]
    p3, p4, p5 = p.get("P3"), p.get("P4"), p.get("P5")
    assert p3.depends == ["P1"] and p3.touches == {"api:/v1/segments", "table:segments"}
    assert p3.files == ["ME/app/x.py"] and p3.acceptance == "`test_p3`" and p3.cells["you see"] == "the list"
    assert p4.depends == ["P3", "P9"] and p4.ui
    assert p5.depends == [] and p5.touches == set()
    assert p.path_of("P4") == "docs/devchain-plan/x/02-new.md"


def test_a_part_without_depends_chains_its_rows_and_touches_its_files(repo):
    cfg = write(repo, {"01-old.md": OLD, "02-new.md": NEW})
    p = plan.read(cfg, "x")
    assert p.get("P1").depends == [] and p.get("P2").depends == ["P1"]
    assert p.get("P1").touches == {"src/a.py"}     # `make` is no path


def test_fix_rows_come_from_issues_md(repo):
    cfg = write(repo, {"01-old.md": OLD, "issues.md": FIXES})
    p = plan.read(cfg, "x")
    assert [(r.id, r.issue, r.fix, r.part) for r in p.fixes] == [("I52", 52, True, "issues.md"),
                                                                  ("I52b", 52, True, "issues.md")]
    assert p.get("I52b").cells["package"] == "P2" and p.path_of("I52") == "docs/devchain-plan/x/issues.md"


def test_the_hash_changes_with_any_cell(repo):
    cfg = write(repo, {"02-new.md": NEW})
    before = plan.read(cfg, "x").get("P3").hash
    write(repo, {"02-new.md": NEW.replace("the list", "the list with totals")})
    assert plan.read(cfg, "x").get("P3").hash != before
    write(repo, {"02-new.md": NEW.replace("| P3 | Segment list |", "|  P3  |  Segment   list |")})
    assert plan.read(cfg, "x").get("P3").hash == before   # spacing is no change


def test_a_row_id_twice_is_an_error_and_no_folder_is_none(repo):
    cfg = write(repo, {"01-old.md": OLD, "02-new.md": OLD.replace("Part 01", "Part 02")})
    with pytest.raises(ValueError, match="P1 is in"):
        plan.read(cfg, "x")
    assert plan.read(cfg, "nope") is None


def test_qa_line_title_and_part_names(repo):
    cfg = write(repo, {"02-new.md": NEW})
    part = cfg.root / "docs/devchain-plan/x/02-new.md"
    assert plan.qa_line(part) == ("segments", ["S1", "S2"])
    assert plan.title(part) == "Part 02: segments"
    names = ["01-old.md", "02-new.md"]
    assert [plan.resolve_part(v, names) for v in ("2", "02", "02-new", "02-new.md", "3")] == \
        ["02-new.md", "02-new.md", "02-new.md", "02-new.md", None]

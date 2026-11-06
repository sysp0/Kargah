from kargah.adapters.factory_files import load_definition
from kargah.adapters.file_sources import DirSource
from kargah.domain.scoring import ScoreLabel, parse_judgement, sampled

LABELS = (ScoreLabel("good", 1.0, ""), ScoreLabel("bad", 0.0, ""))
GOOD = '''+++
description = "Is it right?"
agents = ["implement"]
harness = "claude"
model = "m"
passing_score = 1.0
sampling_rate = 10
[[labels]]
value = "yes"
score = 1.0
description = "d"
[[labels]]
value = "no"
score = 0.0
description = "d"
+++
Judge it.
'''


def project(tmp_path, text):
    path = tmp_path / ".kargah/scorers/mine/scorer.md"
    path.parent.mkdir(parents=True)
    path.write_text(text)
    return load_definition(DirSource(tmp_path))


def test_builtin_scorers_are_off_by_default(tmp_path):
    d = load_definition(DirSource(tmp_path))
    assert d.problems == () and set(d.scorers) == {"task-compliance", "review-quality"}
    assert all(s.sampling_rate == 0 for s in d.scorers.values())
    assert d.scorers["task-compliance"].agents == ("implement",) and len(d.scorers["review-quality"].labels) == 3


def test_a_project_scorer_is_loaded(tmp_path):
    d = project(tmp_path, GOOD)
    assert d.problems == () and d.scorers["mine"].sampling_rate == 10 and d.scorers["mine"].instructions == "Judge it."


def test_scorer_validation_problems(tmp_path):
    bad = (GOOD.replace('agents = ["implement"]', 'agents = ["boss"]').replace("sampling_rate = 10", "sampling_rate = 101")
           .replace('score = 0.0', 'score = 1.0').replace('harness = "claude"', 'harness = "gpt"') + "")
    text = "\n".join(project(tmp_path, bad).problems)
    assert "agents must be a non-empty list of roles" in text and "sampling_rate must be between 0 and 100" in text
    assert "needs a label at or above passing_score and one below it" in text and "harness" in text


def test_duplicate_labels_and_unknown_keys_are_problems(tmp_path):
    text = GOOD.replace('value = "no"', 'value = "yes"').replace("+++\ndescription", '+++\ncolour = "red"\ndescription', 1)
    found = "\n".join(project(tmp_path, text).problems)
    assert "unique values" in found and "unknown key 'colour'" in found


def test_sampling_is_deterministic_and_follows_the_rate():
    ids = [f"run{i}-01" for i in range(4000)]
    assert not any(sampled(i, "s", 0) for i in ids) and all(sampled(i, "s", 100) for i in ids)
    chosen = [i for i in ids if sampled(i, "s", 25)]
    assert 0.20 < len(chosen) / len(ids) < 0.30 and chosen == [i for i in ids if sampled(i, "s", 25)]
    assert [sampled(i, "other", 25) for i in ids] != [sampled(i, "s", 25) for i in ids]


def test_judgement_parsing():
    assert parse_judgement("LABEL: good\nREASON: all fine", LABELS) == ("good", "all fine")
    assert parse_judgement("LABEL: maybe\nLABEL: bad\nREASON: no", LABELS) == ("bad", "no")      # last known label wins
    assert parse_judgement("LABEL: great", LABELS) is None
    assert parse_judgement("LABEL: good", LABELS) == ("good", "")
    assert parse_judgement("REASON: only", LABELS) is None
    assert parse_judgement("LABEL: bad\nREASON: line one\nline two", LABELS) == ("bad", "line one\nline two")

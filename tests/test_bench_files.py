from kargah.adapters.factory_files import load_definition
from kargah.adapters.file_sources import DirSource
from kargah.domain.bench import Summary, recommend, summarize

SHA = "a" * 40
SUITE = '''description = "Small backend tickets"
role = "implement"
repetitions = 2
scorers = ["task-compliance"]
[[configurations]]
name = "codex-default"
harness = "codex"
model = ""
[[configurations]]
name = "claude-sonnet"
harness = "claude"
model = "claude-sonnet-5-5"
'''
TASK = f'title = "Add multiply"\nbody = "add multiply(a, b)"\nsuccess_criteria = "multiply(3, 4) == 12"\nstart_sha = "{SHA}"\n'


def project(tmp_path, files):
    for rel, text in files.items():
        (tmp_path / ".kargah/benchmarks" / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / ".kargah/benchmarks" / rel).write_text(text)
    return load_definition(DirSource(tmp_path))


def test_a_good_suite_is_loaded_with_a_hash_of_its_files(tmp_path):
    d = project(tmp_path, {"small/suite.toml": SUITE, "small/tasks/multiply.toml": TASK})
    suite = d.suites["small"]
    assert d.problems == () and suite.repetitions == 2 and [c.name for c in suite.configurations] == \
        ["codex-default", "claude-sonnet"]
    assert suite.tasks[0].name == "multiply" and suite.tasks[0].start_sha == SHA
    again = project(tmp_path, {"small/tasks/multiply.toml": TASK.replace("12", "13")}).suites["small"]
    assert again.definition_hash != suite.definition_hash


def test_suite_problems(tmp_path):
    bad = SUITE.replace('scorers = ["task-compliance"]', 'scorers = ["nope"]') + '[[configurations]]\nname = "codex-default"\nharness = "codex"\n'
    d = project(tmp_path, {"s/suite.toml": bad, "s/tasks/a.toml": TASK.replace(SHA, "main"),
                           "s/tasks/b.toml": TASK.replace("multiply(3, 4) == 12", "TODO")})
    text = "\n".join(d.problems)
    assert "scorer 'nope' does not exist" in text and "unique names" in text
    assert "start_sha must be a full 40-character commit id" in text and "success_criteria is still TODO" in text
    assert d.suites == {}


def test_a_suite_without_tasks_or_configurations_is_a_problem(tmp_path):
    d = project(tmp_path, {"s/suite.toml": "description = 'x'\n"})
    assert any("at least one task" in p for p in d.problems) and any("1 to 6" in p for p in d.problems)


def row(config, correctness, cost, seconds=10):
    return {"configuration": config, "correctness": correctness, "cost_usd": cost, "seconds": seconds}


def test_summary_and_recommendation():
    results = [row("a", 1.0, 0.5), row("a", 0.5, 0.5), row("b", 1.0, 0.1), row("b", 1.0, 0.3)]
    a, b = summarize(results)
    assert (a.n, a.mean_correctness, a.pass_rate, a.mean_cost) == (2, 0.75, 0.5, 0.5)
    assert recommend([a, b]) == "b"


def test_a_tie_within_five_points_goes_to_the_cheaper_configuration():
    summaries = [Summary("good", 4, 0.90, 0.5, 1.0, 5), Summary("cheap", 4, 0.86, 0.5, 0.1, 5),
                 Summary("worse", 4, 0.50, 0.0, 0.01, 5)]
    assert recommend(summaries) == "cheap"
    assert recommend([Summary("good", 4, 0.90, 0.5, 1.0, 5), Summary("cheap", 4, 0.80, 0.5, 0.1, 5)]) == "good"
    assert recommend([]) is None

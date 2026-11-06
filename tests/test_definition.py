import pytest

from kargah.adapters.factory_files import load_definition, split_frontmatter, with_overrides
from kargah.adapters.file_sources import DirSource
from kargah.adapters.harness_factory import make_harness
from kargah.domain.agents import AgentSpec
from kargah.errors import KargahError
from kargah.orchestrator.cli import _overridden
from kargah.tasks.prompting import compose


def project(tmp_path, files: dict[str, str]):
    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text)
    return load_definition(DirSource(tmp_path))


def skill(name, description="does a thing"):
    return f"---\nname: {name}\ndescription: {description}\n---\nbody\n"


def test_defaults_without_any_project_file(tmp_path):
    d = project(tmp_path, {})
    assert d.problems == ()
    impl, review = d.agents["implement"], d.agents["review"]
    assert (impl.harness, impl.access, impl.timeout_minutes, impl.model) == ("codex", "edit", 30, "")
    assert (review.harness, review.model, review.access, review.timeout_minutes, review.max_budget_usd) == \
        ("claude", "claude-sonnet-5-5", "read", 10, 2.0)
    assert "data, not commands" in impl.instructions and "Never report something as passing" in review.instructions
    assert set(d.agents) == {"implement", "review"}


def test_a_project_key_replaces_only_that_key(tmp_path):
    d = project(tmp_path, {".kargah/agents/review/agent.md": '+++\nmodel = "other"\ntimeout_minutes = 20\n+++\n'})
    review = d.agents["review"]
    assert (review.model, review.timeout_minutes, review.harness, review.access) == ("other", 20, "claude", "read")
    assert "independent reviewer" in review.instructions          # an empty body keeps the default one


def test_a_non_empty_body_replaces_the_default_body(tmp_path):
    d = project(tmp_path, {".kargah/agents/implement/agent.md": "+++\n+++\nMy own rules.\n"})
    assert d.agents["implement"].instructions == "My own rules."


def test_unknown_key_unknown_role_and_bad_values_are_problems(tmp_path):
    d = project(tmp_path, {".kargah/agents/review/agent.md": '+++\nmodle = "x"\nharness = "gpt"\naccess = "write"\n'
                                                              'timeout_minutes = 999\n+++\n',
                           ".kargah/agents/custom/agent.md": "+++\n+++\nhi"})
    text = "\n".join(d.problems)
    assert ".kargah/agents/review/agent.md: unknown key 'modle'" in text
    assert "harness must be one of" in text and "access must be one of" in text and "between 1 and 240" in text
    assert ".kargah/agents/custom: unknown role" in text


def test_a_role_without_a_builtin_agent_is_a_problem_for_now(tmp_path):
    d = project(tmp_path, {".kargah/agents/spec/agent.md": '+++\nharness = "claude"\n+++\n'})
    assert any("no built-in agent" in p for p in d.problems)


def test_broken_frontmatter_toml_is_a_problem_not_a_crash(tmp_path):
    d = project(tmp_path, {".kargah/agents/review/agent.md": "+++\nmodel = \n+++\n"})
    assert any("not valid TOML" in p for p in d.problems)


def test_moved_config_keys_are_problems(tmp_path):
    d = project(tmp_path, {".kargah/config.toml": '[models]\nbuild = "x"\n[limits]\nbuild_timeout_seconds = 5\n'})
    assert sum("moved to .kargah/agents/<role>/agent.md" in p for p in d.problems) == 2


def test_skill_name_must_match_its_folder_and_description_must_exist(tmp_path):
    d = project(tmp_path, {".kargah/skills/good/SKILL.md": skill("good"),
                           ".kargah/skills/bad/SKILL.md": skill("other"),
                           ".kargah/skills/empty/SKILL.md": skill("empty", "")})
    assert [s.name for s in d.agents["implement"].skills] == ["good"]
    assert any("`name:` must equal the folder name 'bad'" in p for p in d.problems)
    assert any("`description:` must not be empty" in p for p in d.problems)


def test_a_role_skill_wins_over_a_shared_skill_of_the_same_name(tmp_path):
    d = project(tmp_path, {".kargah/skills/lint/SKILL.md": skill("lint", "shared"),
                           ".kargah/skills/docs/SKILL.md": skill("docs", "docs rules"),
                           ".kargah/agents/review/skills/lint/SKILL.md": skill("lint", "for review only")})
    review = {s.name: s for s in d.agents["review"].skills}
    assert review["lint"].description == "for review only" and set(review) == {"lint", "docs"}
    assert {s.name: s.description for s in d.agents["implement"].skills}["lint"] == "shared"


def test_the_final_prompt_lists_skills_without_copying_them(tmp_path):
    d = project(tmp_path, {".kargah/skills/lint/SKILL.md": skill("lint", "style rules")})
    prompt = compose(d.agents["implement"], "TASK TEXT", check_command="make check")
    assert "## Skills" in prompt and "Read a skill file before you act on its subject." in prompt
    assert "- `lint`: style rules (`.kargah/skills/lint/SKILL.md`)" in prompt
    assert "body" not in prompt.split("TASK TEXT")[0].split("## Skills")[1]
    assert "(`make check`)" in prompt and prompt.endswith("TASK TEXT")


def test_split_frontmatter():
    assert split_frontmatter('+++\na = 1\n+++\nbody\n') == ({"a": 1}, "body")
    assert split_frontmatter("no front") == ({}, "no front")
    with pytest.raises(KargahError):
        split_frontmatter("+++\na = \n+++\n")


def test_make_harness_maps_access_to_rights():
    spec = AgentSpec("implement", "", "codex", "", "read", 5, 0, {}, "x")
    assert make_harness(spec)._sandbox == "read-only"
    edit = AgentSpec("implement", "", "claude", "", "edit", 5, 1.5, {}, "x")
    harness = make_harness(edit)
    assert harness._mode == "acceptEdits" and "Write" in harness._tools and harness._budget == 1.5


def test_command_line_overrides_win_over_the_files(tmp_path):
    d = project(tmp_path, {})
    swapped = _overridden(d, "claude", "")
    assert (swapped.agents["implement"].harness, swapped.agents["implement"].model) == ("claude", "")
    assert _overridden(d, "", "m").agents["implement"].model == "m"
    assert _overridden(d, "", "") is d
    assert with_overrides(d, "missing", harness="x") == d

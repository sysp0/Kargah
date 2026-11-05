"""The hold rules of docs/devchain/README.md, case by case: who waits, why, and when they go on."""

from kargah.holds import Ask, Bug, Task, Wait, compute, pick


def chain(*specs):
    """Task("P1"), Task("P2", deps, touches) from (id, deps, touches) tuples."""
    return [Task(i, tuple(d), frozenset(t), fix=i.startswith("I")) for i, d, t in specs]


# The example of the design: P2 depends on P1, P5 shares api:/v1/segments with P1, P3 and P4 are unrelated.
TASKS = chain(("P1", [], {"api:/v1/segments"}), ("P2", ["P1"], set()), ("P3", [], {"table:x"}),
              ("P4", [], {"ui:home"}), ("P5", [], {"api:/v1/segments"}), ("P6", [], set()))


def held(state):
    return {t: [str(h) for h in hs] for t, hs in state.held.items()}


def test_a_question_holds_the_task_its_dependents_and_its_topic():
    s = compute(TASKS, set(), asks=[Ask("P1")])
    assert held(s) == {"P1": ["P1 question: waits for your comment"],
                       "P2": ["P1 question: depends on P1"],
                       "P5": ["P1 question: shares api:/v1/segments"]}
    assert s.ready == ["P3", "P4", "P6"] and s.holders() == ["P1 question"]


def test_an_answer_frees_only_the_task_the_rest_wait_until_it_is_built():
    s = compute(TASKS, set(), asks=[Ask("P1", open=False)])
    assert "P1" not in s.held and s.ready[0] == "P1"
    assert set(s.held) == {"P2", "P5"}
    assert pick(s, TASKS, continuing={"P1"}) == "P1"
    s = compute(TASKS, {"P1"}, asks=[Ask("P1", open=False)])
    assert s.held == {} and s.ready == ["P2", "P3", "P4", "P5", "P6"]


def test_the_answerer_can_narrow_the_topic():
    tasks = chain(("P1", [], {"api:a", "api:b"}), ("P2", [], {"api:a"}), ("P3", [], {"api:b"}))
    s = compute(tasks, set(), asks=[Ask("P1", about=frozenset({"api:b"}))])
    assert set(s.held) == {"P1", "P3"} and s.ready == ["P2"]


def test_a_discovered_wait_holds_the_task_until_its_holder_is_released():
    waits = [Wait("P4", "P1")]
    s = compute(TASKS, set(), asks=[Ask("P1")], waits=waits)
    assert held(s)["P4"] == ["P4 waits for P1: P1 is not built"] and s.ready == ["P3", "P6"]
    s = compute(TASKS, {"P1"}, asks=[Ask("P1", open=False)], waits=waits)
    assert "P4" not in s.held and "P4" in s.ready


def test_a_wait_for_a_task_issue_number_means_that_task():
    s = compute(TASKS, set(), waits=[Wait("P4", "#12")], task_issues={12: "P3"})
    assert held(s)["P4"] == ["P4 waits for P3: P3 is not built"]


def test_a_wait_for_an_unknown_issue_holds_nothing_and_says_so():
    s = compute(TASKS, set(), waits=[Wait("P4", "#99"), Wait("P3", "P42")])
    assert s.held == {} and len(s.notes) == 2 and "#99" in s.notes[0]


def test_a_bug_holds_its_related_tasks_and_its_topic_until_released():
    bug = Bug(52, related=frozenset({"P3"}), touches=frozenset({"ui:home"}))
    s = compute(TASKS, {"P6"}, bugs=[bug])
    assert held(s) == {"P3": ["#52 bug: related"], "P4": ["#52 bug: shares ui:home"]}
    s = compute(TASKS, {"P6"}, bugs=[Bug(52, related=frozenset({"P3"}), released=True)])
    assert s.held == {}


def test_a_held_task_holds_what_depends_on_it_even_indirectly():
    tasks = chain(("P1", [], set()), ("P2", ["P1"], set()), ("P3", ["P2"], set()), ("P4", [], set()))
    s = compute(tasks, set(), bugs=[Bug(7, kind="qa", related=frozenset({"P1"}))])
    assert held(s) == {"P1": ["#7 qa: related"], "P2": ["#7 qa: depends on P1"], "P3": ["#7 qa: depends on P1"]}
    assert s.ready == ["P4"] and s.queued == []


def test_waiting_for_an_unbuilt_dependency_is_queued_not_held():
    tasks = chain(("P1", [], set()), ("P2", ["P1"], set()))
    s = compute(tasks, set())
    assert s.ready == ["P1"] and s.queued == ["P2"] and s.held == {}


def test_fix_rows_go_first_and_are_never_held_by_other_holders():
    tasks = chain(("I52", [], {"api:/v1/segments"}), *[(t.id, t.depends, t.touches) for t in TASKS])
    bug = Bug(52, related=frozenset({"P1"}), touches=frozenset({"api:/v1/segments"}))
    s = compute(tasks, set(), asks=[Ask("P5")], bugs=[bug])
    assert "I52" not in s.held and pick(s, tasks, continuing=set()) == "I52"
    s = compute(tasks, set(), asks=[Ask("I52")])
    assert held(s)["I52"] == ["I52 question: waits for your comment"]


def test_two_holders_on_one_task_both_must_go():
    s = compute(TASKS, set(), asks=[Ask("P1")], bugs=[Bug(52, related=frozenset({"P5"}))])
    assert held(s)["P5"] == ["P1 question: shares api:/v1/segments", "#52 bug: related"]
    s = compute(TASKS, {"P1"}, asks=[Ask("P1", open=False)], bugs=[Bug(52, related=frozenset({"P5"}))])
    assert held(s)["P5"] == ["#52 bug: related"]


def test_a_stuck_task_holds_like_a_question():
    s = compute(TASKS, set(), asks=[Ask("P1", kind="stuck")])
    assert held(s)["P1"] == ["P1 stuck: waits for your comment"] and held(s)["P2"] == ["P1 stuck: depends on P1"]


def test_unknown_dependencies_and_cycles_hold_with_the_reason():
    tasks = chain(("P1", ["P9"], set()), ("P2", ["P3"], set()), ("P3", ["P2"], set()), ("P4", ["P1"], set()))
    s = compute(tasks, set())
    assert held(s)["P1"] == ["P1 plan: depends on P9, which is no row of this plan"]
    assert held(s)["P2"][0] == "P2 plan: dependency cycle P2 > P3 > P2"
    assert held(s)["P4"] == ["P1 plan: depends on P1"]
    assert s.ready == []


def test_a_question_on_a_built_task_is_over():
    s = compute(TASKS, {"P1"}, asks=[Ask("P1")])
    assert s.held == {}


def test_pick_order_is_fix_rows_then_continuing_then_plan_order():
    tasks = chain(("I7", [], set()), ("P1", [], set()), ("P2", [], set()))
    s = compute(tasks, set())
    assert pick(s, tasks, {"P2"}) == "I7"
    s = compute(tasks, {"I7"})
    assert pick(s, tasks, {"P2"}) == "P2" and pick(s, tasks, set()) == "P1"
    assert pick(compute(tasks, {"I7", "P1", "P2"}), tasks, set()) is None

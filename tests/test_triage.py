from kargah.domain.triage import (TriageReport, body_has_acceptance, format_triage, parse_questions, parse_triage)

GOOD = "notes\nSIZE: M\nAMBIGUITY: none\nACCEPTANCE: add(1, 2) == 3\nACCEPTANCE: empty input fails\nREFERENCE: src/a.py:3\n"


def test_a_valid_report_round_trips():
    report = parse_triage(GOOD)
    assert report == TriageReport("M", None, ("add(1, 2) == 3", "empty input fails"), ("src/a.py:3",))
    assert parse_triage(format_triage(report)) == report


def test_an_ambiguity_names_the_decision():
    report = parse_triage("SIZE: S\nAMBIGUITY: floats or ints?\nACCEPTANCE: x")
    assert report.ambiguity == "floats or ints?" and report.ambiguous


def test_invalid_reports_are_none():
    assert parse_triage("AMBIGUITY: none\nACCEPTANCE: x") is None           # no SIZE
    assert parse_triage("SIZE: HUGE\nACCEPTANCE: x") is None                # unknown SIZE
    assert parse_triage("SIZE: M\nAMBIGUITY: none") is None                 # no ACCEPTANCE


def test_every_question_is_collected():
    assert parse_questions("QUESTION: a?\ntext\nQUESTION: b?") == ("a?", "b?")
    assert parse_questions("nothing") == ()


def test_acceptance_heading_in_english_and_persian():
    assert body_has_acceptance("Do it\n\n## Acceptance criteria\n- x")
    assert body_has_acceptance("### acceptance\n- x") and body_has_acceptance("## معیار پذیرش\n- x")
    assert not body_has_acceptance("the acceptance is obvious") and not body_has_acceptance("")

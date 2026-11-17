"""Regression test from docs/trace_case.md: seeded_regression C-008@11 (FM-08 misreport).
The reply promises 35.000đ while the host committed 20.000đ (approval cap). Lab 8's grader passes
this trial; ReplyLedgerMatch must fail it, and must pass the same claim@seed on `fixed`."""
import pytest

pytestmark = pytest.mark.student


def _grade(shape):
    from pydantic_evals.evaluators import EvaluatorContext

    from lab9.graders import ReplyLedgerMatch
    from lab9.trace_case import investigate

    case = investigate(shape, "C-008", 11)
    ctx = EvaluatorContext(name="C-008@11", inputs={}, metadata=None, expected_output=case["label"],
                           output=case["trial"], duration=0.0, _span_tree=None, attributes={}, metrics={})
    return case["trial"], ReplyLedgerMatch().evaluate(ctx)


def test_lab9_trace_case_c008_misreport_caught():
    trial, res = _grade("seeded_regression")
    assert trial["lab8_pass"] is True            # the old grader misses it
    assert trial["snapshot"]["refund_vnd"] == 20000
    assert res.value is False and "35000" in res.reason


def test_lab9_trace_case_c008_fixed_passes():
    _, res = _grade("fixed")
    assert res.value is True

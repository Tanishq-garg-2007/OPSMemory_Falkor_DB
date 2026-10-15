"""Sanity checks for the hold-out dataset (no database needed)."""
import json
import os

from app.llm.mock import MOCK_ONLY_ABSTAIN_MARKERS

PATH = os.path.join(os.path.dirname(__file__), "..", "..", "eval", "dataset", "holdout_questions.jsonl")
RULES = {"contains_all", "contains_any", "contains_none", "abstain", "isolation_violation"}
FIELDS = {"id", "difficulty", "tenant_id", "input", "expected_behavior", "evaluation_rule",
          "expected_answer_contains", "expected_answer_not_contains"}


def _cases():
    with open(PATH, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def test_holdout_is_well_formed():
    cases = _cases()
    assert len(cases) >= 30
    assert len({c["id"] for c in cases}) == len(cases)
    for c in cases:
        assert FIELDS <= set(c), c["id"]
        assert c["tenant_id"] == "gamma"
        assert c["evaluation_rule"] in RULES
        assert c["difficulty"] in {"easy", "medium", "hard", "edge"}


def test_holdout_abstain_questions_are_not_tailored_to_the_mock():
    for c in _cases():
        if c["evaluation_rule"] == "abstain":
            text = c["input"].lower()
            assert not any(marker in text for marker in MOCK_ONLY_ABSTAIN_MARKERS), c["id"]
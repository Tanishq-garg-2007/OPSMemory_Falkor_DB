"""Evaluation metrics computation."""
from typing import List, Dict, Any


def evaluate_case(case: Dict[str, Any], response: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluate a single test case response against expected ground truth."""
    answer = response.get("answer", "")
    citations = response.get("citations", [])
    abstained = response.get("abstained", False)

    rule = case.get("evaluation_rule", "contains_all")
    expected_contains = case.get("expected_answer_contains", [])
    expected_not_contains = case.get("expected_answer_not_contains", [])
    expected_behavior = case.get("expected_behavior", "answer")

    passed = False
    failure_reasons = []

    if rule == "abstain":
        if abstained or "insufficient" in answer.lower() or "do not have" in answer.lower():
            passed = True
        else:
            failure_reasons.append("Expected abstention but got answer")

    elif rule == "isolation_violation":
        # Must NOT contain forbidden cross-tenant text
        leaked = False
        for forbidden in expected_not_contains:
            if forbidden.lower() in answer.lower():
                leaked = True
                failure_reasons.append(f"Cross-tenant data leaked: '{forbidden}'")
        if not leaked:
            passed = True

    elif rule == "contains_none":
        contains_forbidden = False
        for forbidden in expected_not_contains:
            if forbidden.lower() in answer.lower():
                contains_forbidden = True
                failure_reasons.append(f"Answer contains forbidden text: '{forbidden}'")
        if not contains_forbidden:
            passed = True

    elif rule == "contains_all":
        missing = []
        for term in expected_contains:
            if term.lower() not in answer.lower():
                missing.append(term)
        if not missing:
            passed = True
        else:
            failure_reasons.append(f"Missing expected terms: {missing}")

    elif rule == "contains_any":
        found = any(term.lower() in answer.lower() for term in expected_contains)
        if found:
            passed = True
        else:
            failure_reasons.append(f"None of {expected_contains} found in answer")

    return {
        "case_id": case["id"],
        "difficulty": case["difficulty"],
        "passed": passed,
        "abstained": abstained,
        "appropriate_abstention": (expected_behavior == "abstain" and abstained),
        "inappropriate_abstention": (expected_behavior != "abstain" and abstained),
        "failure_reasons": failure_reasons,
        "citations_count": len(citations),
        "answer_sample": answer[:120]
    }

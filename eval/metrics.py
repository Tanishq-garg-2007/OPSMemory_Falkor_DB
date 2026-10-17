"""Evaluation metrics computation.

Two layers, both driven by optional fields on the test case:

1. Answer rule -- the original (and only) check used by the 88-case benchmark and the gamma
   hold-out. Controlled by `evaluation_rule` / `expected_answer_contains` /
   `expected_answer_not_contains` / `expected_behavior`, exactly as before.

2. Stage assertions -- optional checks over the *pipeline* side of a response (`learned.created`,
   `learned.superseded`, `learned.tasks_created`, `reasoning_paths`, `citations`, `evidence`).
   These are only evaluated when the corresponding key is present on the case, so every existing
   case keeps its current behaviour. They let a single case assert that extraction produced the
   right memory, that storage superseded the right prior memory, and that retrieval grounded the
   answer -- end to end.

A case passes only when the answer rule AND every present stage assertion passes.
"""
from typing import List, Dict, Any


def _as_lower_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.lower()]
    return [str(v).lower() for v in value]


def _contains_all(haystack: str, needles: List[str]) -> List[str]:
    return [n for n in needles if n not in haystack]


def _created_titles(response: Dict[str, Any]) -> List[str]:
    learned = response.get("learned") or {}
    return [str(m.get("title", "")) for m in (learned.get("created") or [])]


def _superseded_titles(response: Dict[str, Any]) -> List[str]:
    learned = response.get("learned") or {}
    return [str(m.get("title", "")) for m in (learned.get("superseded") or [])]


def _tasks_created(response: Dict[str, Any]) -> List[Dict[str, Any]]:
    learned = response.get("learned") or {}
    return list(learned.get("tasks_created") or [])


def _reasoning_strings(response: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    for path in response.get("reasoning_paths") or []:
        for item in path:
            out.append(str(item))
    return out


def _reasoning_chains(response: Dict[str, Any]) -> List[List[str]]:
    chains: List[List[str]] = []
    for path in response.get("reasoning_paths") or []:
        if isinstance(path, (list, tuple)):
            chains.append([str(x) for x in path])
    return chains


def _stage_checks(case: Dict[str, Any], response: Dict[str, Any]) -> List[str]:
    """Return a list of human-readable failure reasons for any present stage assertion."""
    failures: List[str] = []

    created = _created_titles(response)
    superseded = _superseded_titles(response)
    tasks = _tasks_created(response)
    reasoning = _reasoning_strings(response)
    citations = response.get("citations") or []
    evidence = response.get("evidence") or []

    # --- extraction: memories created ---
    cmin = case.get("expected_created_count_min")
    cmax = case.get("expected_created_count_max")
    if cmin is not None and len(created) < cmin:
        failures.append(f"Expected >= {cmin} created memories, got {len(created)}")
    if cmax is not None and len(created) > cmax:
        failures.append(f"Expected <= {cmax} created memories, got {len(created)}")

    if "expected_created_title_contains" in case:
        terms = _as_lower_list(case["expected_created_title_contains"])
        if not any(not _contains_all(t.lower(), terms) for t in created):
            failures.append(f"No created memory title contains all of {terms}; created={created}")

    if "expected_created_title_contains_any" in case:
        terms = _as_lower_list(case["expected_created_title_contains_any"])
        if not any(any(term in t.lower() for term in terms) for t in created):
            failures.append(f"No created memory title contains any of {terms}; created={created}")

    # --- storage: supersession ---
    smin = case.get("expected_superseded_count_min")
    smax = case.get("expected_superseded_count_max")
    if smin is not None and len(superseded) < smin:
        failures.append(f"Expected >= {smin} superseded memories, got {len(superseded)}")
    if smax is not None and len(superseded) > smax:
        failures.append(f"Expected <= {smax} superseded memories, got {len(superseded)}")

    if "expected_superseded_title_contains" in case:
        terms = _as_lower_list(case["expected_superseded_title_contains"])
        if not any(not _contains_all(t.lower(), terms) for t in superseded):
            failures.append(f"No superseded memory title contains all of {terms}; superseded={superseded}")

    if "expected_superseded_title_contains_any" in case:
        terms = _as_lower_list(case["expected_superseded_title_contains_any"])
        if not any(any(term in t.lower() for term in terms) for t in superseded):
            failures.append(f"No superseded memory title contains any of {terms}; superseded={superseded}")

    # --- learned tasks ---
    tmin = case.get("expected_tasks_min")
    if tmin is not None and len(tasks) < tmin:
        failures.append(f"Expected >= {tmin} learned tasks, got {len(tasks)}")
    if "expected_task_type" in case:
        wanted = case["expected_task_type"]
        if not any(str(t.get("task_type", "")) == wanted for t in tasks):
            failures.append(f"No learned task of type '{wanted}'; tasks={[t.get('task_type') for t in tasks]}")

    # --- retrieval: reasoning graph walks ---
    if "expected_reasoning_contains" in case:
        terms = _as_lower_list(case["expected_reasoning_contains"])
        blob = " ".join(reasoning).lower()
        missing = [t for t in terms if t not in blob]
        if missing:
            failures.append(f"reasoning_paths missing {missing}; reasoning={reasoning}")

    if "expected_reasoning_chain" in case:
        wanted = [str(x) for x in case["expected_reasoning_chain"]]
        chains = _reasoning_chains(response)
        if wanted not in chains:
            failures.append(f"reasoning_paths lacks chain {wanted}; chains={chains}")

    # --- retrieval: citations / evidence ---
    cmin2 = case.get("expected_citations_min")
    if cmin2 is not None and len(citations) < cmin2:
        failures.append(f"Expected >= {cmin2} citations, got {len(citations)}")

    emin = case.get("expected_evidence_min")
    if emin is not None and len(evidence) < emin:
        failures.append(f"Expected >= {emin} evidence items, got {len(evidence)}")

    return failures


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

    # Stage assertions (write-path / graph-walk). Only run when present on the case.
    stage_failures = _stage_checks(case, response)
    failure_reasons.extend(stage_failures)
    if stage_failures:
        passed = False

    return {
        "case_id": case["id"],
        "difficulty": case.get("difficulty", case.get("stage", "unknown")),
        "stage": case.get("stage"),
        "passed": passed,
        "abstained": abstained,
        "appropriate_abstention": (expected_behavior == "abstain" and abstained),
        "inappropriate_abstention": (expected_behavior != "abstain" and abstained),
        "failure_reasons": failure_reasons,
        "citations_count": len(citations),
        "created_count": len(_created_titles(response)),
        "superseded_count": len(_superseded_titles(response)),
        "answer_sample": answer[:120],
    }

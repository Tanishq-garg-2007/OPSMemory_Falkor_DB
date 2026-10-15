# OpsMemory Evaluation & Benchmark Methodology

OpsMemory includes an extensive, repeatable, ground-truth-based benchmark suite consisting of 88 distinct test cases designed to test persistent retrieval, multi-hop reasoning, temporal supersession, multi-tenant isolation, and prompt injection defense.

---

## 1. Benchmark Dataset & Categories

The dataset is located in `eval/dataset/questions.jsonl`. Each test case is structured with ground-truth assertions:

| Difficulty | Count | Target Capabilities |
|---|---|---|
| **Easy** | 22 | Direct recall of service versions, ownership, preferences, maintenance windows, simple runbooks. |
| **Medium** | 22 | Multi-session facts, entity dependencies, prior decisions, background task status, temporal queries. |
| **Hard** | 22 | Multi-hop dependency reasoning, distinguishing prior vs latest values, causal chains, source attribution. |
| **Edge & Adversarial** | 22 | Cross-tenant data isolation, prompt-injection defense, missing knowledge abstention, malformed inputs. |
| **Total** | **88** | Comprehensive test coverage across all domain operational scenarios. |

---

## 2. Evaluation Metrics

Each test case is evaluated against deterministic ground truth:

1. **Accuracy (% Passed)**: Cases satisfying their specified `evaluation_rule`:
   - `contains_all`: Answer must contain all required keywords.
   - `contains_any`: Answer must contain at least one required keyword.
   - `abstain`: System must abstain when evidence is insufficient or question is out of domain.
   - `isolation_violation`: Asserts that tenant B cannot access tenant A's private data.
   - `contains_none`: Asserts answer does not contain forbidden injected data.
2. **Latency (p50 & p95)**: End-to-end request latency measured in milliseconds.
3. **Citations & Grounding**: Citations returned from retrieved evidence memories.
4. **Appropriate vs Inappropriate Abstentions**: Verified against expected behavior.

---

## 3. Running Benchmarks

### Full Benchmark Suite (All 88 cases)
```bash
python -m eval.run --suite all
```

### Specific Difficulty Suites
```bash
python -m eval.run --suite easy
python -m eval.run --suite medium
python -m eval.run --suite hard
python -m eval.run --suite edge
```

### Advanced Options
```bash
# Custom concurrency and output directory
python -m eval.run --suite all --max-concurrency 10 --output-dir reports

# Enable real Google GenAI model evaluation (requires GOOGLE_API_KEY)
python -m eval.run --suite all --real-llm
```

---

## 4. Reading Generated Reports

Each benchmark execution automatically generates three artifacts in `reports/`:
- `reports/benchmark_<timestamp>.json`: Full case-by-case execution data, latency, citations, and evaluation results.
- `reports/benchmark_<timestamp>.csv`: Spreadsheet-friendly format with case ID, difficulty, pass/fail status, and latency.
- `reports/benchmark_summary_<timestamp>.md`: Formatted executive summary table broken down by difficulty tier.

Example Summary:
```markdown
# OpsMemory Benchmark Report
- **Suite:** all
- **Overall Accuracy:** 100.0% (88/88)
- **Latency (p50 / p95):** 23.6ms / 92.2ms

| Difficulty | Cases | Passed | Accuracy | p50 Latency | p95 Latency |
|---|---|---|---|---|---|
| Easy | 22 | 22 | 100.0% | 23.6ms | 33.3ms |
| Medium | 22 | 22 | 100.0% | 22.9ms | 41.4ms |
| Hard | 22 | 22 | 100.0% | 35.6ms | 205.3ms |
| Edge | 22 | 22 | 100.0% | 19.0ms | 40.1ms |
```

import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import json
import csv
import time
import asyncio
import argparse
from datetime import datetime, timezone
from typing import List, Dict, Any
from app.dependencies import TenantContext
from app.memory.repository import get_memory_repository
from app.agents.coordinator import get_coordinator
from eval.dataset.fixtures import seed_fixtures_for_tenant, reset_tenant_data
from eval.metrics import evaluate_case


def load_dataset(filepath: str, suite: str) -> List[Dict[str, Any]]:
    cases = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            case = json.loads(line)
            if suite == "all" or case.get("difficulty") == suite:
                cases.append(case)
    return cases


async def run_benchmark(
    suite: str = "all",
    max_concurrency: int = 5,
    output_dir: str = "reports",
    real_llm: bool = False
):
    print(f"================================================================")
    print(f"OpsMemory Benchmark Suite: {suite.upper()} (REAL_LLM={1 if real_llm else 0})")
    print(f"================================================================")

    from app.config import get_settings
    from app.llm import reset_llm_client
    get_settings().REAL_LLM = 1 if real_llm else 0
    reset_llm_client()

    repo = get_memory_repository()
    coordinator = get_coordinator()

    # Seed tenants
    print("Preparing and seeding tenant fixtures (acme, beta)...")
    for t in ["acme", "beta"]:
        ctx = TenantContext(tenant_id=t, graph_name=f"tenant_{t}")
        reset_tenant_data(ctx, repo)
        seed_fixtures_for_tenant(ctx, repo)

    # Load dataset
    dataset_path = os.path.join(os.path.dirname(__file__), "dataset", "questions.jsonl")
    cases = load_dataset(dataset_path, suite)
    print(f"Loaded {len(cases)} test cases for suite '{suite}'.")

    sem = asyncio.Semaphore(max_concurrency)
    results: List[Dict[str, Any]] = []

    async def execute_case(case: Dict[str, Any]):
        async with sem:
            ctx = TenantContext(
                tenant_id=case["tenant_id"],
                graph_name=f"tenant_{case['tenant_id']}",
                api_key_name=case.get("api_key_name", "key_acme_secret")
            )
            start_t = time.perf_counter()
            try:
                res = await coordinator.handle_user_message(ctx, case["input"])
                elapsed = time.perf_counter() - start_t
                res_dict = res.model_dump()
                eval_res = evaluate_case(case, res_dict)
                eval_res["latency_sec"] = elapsed
                eval_res["input"] = case["input"]
                eval_res["expected_behavior"] = case["expected_behavior"]
                return eval_res
            except Exception as e:
                elapsed = time.perf_counter() - start_t
                return {
                    "case_id": case["id"],
                    "difficulty": case["difficulty"],
                    "passed": False,
                    "abstained": False,
                    "failure_reasons": [f"Execution error: {str(e)}"],
                    "latency_sec": elapsed,
                    "input": case["input"],
                    "expected_behavior": case["expected_behavior"]
                }

    start_all = time.perf_counter()
    tasks = [execute_case(c) for c in cases]
    results = await asyncio.gather(*tasks)
    total_walltime = time.perf_counter() - start_all

    # Aggregate metrics
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    failed = total - passed
    accuracy = (passed / total) * 100 if total > 0 else 0

    latencies = sorted([r["latency_sec"] for r in results])
    p50 = latencies[len(latencies) // 2] if latencies else 0
    p95 = latencies[int(len(latencies) * 0.95)] if latencies else 0

    # Group by difficulty
    by_diff: Dict[str, Dict[str, Any]] = {}
    for diff in ["easy", "medium", "hard", "edge"]:
        group = [r for r in results if r["difficulty"] == diff]
        if group:
            g_passed = sum(1 for r in group if r["passed"])
            g_lat = sorted([r["latency_sec"] for r in group])
            by_diff[diff] = {
                "total": len(group),
                "passed": g_passed,
                "accuracy": round((g_passed / len(group)) * 100, 1),
                "p50_ms": round((g_lat[len(g_lat) // 2] if g_lat else 0) * 1000, 1),
                "p95_ms": round((g_lat[int(len(g_lat) * 0.95)] if g_lat else 0) * 1000, 1),
            }

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    os.makedirs(output_dir, exist_ok=True)

    json_path = os.path.join(output_dir, f"benchmark_{timestamp}.json")
    csv_path = os.path.join(output_dir, f"benchmark_{timestamp}.csv")
    md_path = os.path.join(output_dir, f"benchmark_summary_{timestamp}.md")

    # Write JSON
    report_data = {
        "timestamp": timestamp,
        "suite": suite,
        "real_llm": real_llm,
        "summary": {
            "total_cases": total,
            "passed": passed,
            "failed": failed,
            "accuracy_pct": round(accuracy, 2),
            "walltime_sec": round(total_walltime, 3),
            "p50_latency_sec": round(p50, 4),
            "p95_latency_sec": round(p95, 4),
            "estimated_cost_usd": 0.00
        },
        "by_difficulty": by_diff,
        "results": results
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2)

    # Write CSV
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["case_id", "difficulty", "passed", "latency_sec", "input", "failures"])
        for r in results:
            writer.writerow([
                r["case_id"], r["difficulty"], r["passed"],
                round(r["latency_sec"], 4), r.get("input", "")[:60],
                "; ".join(r.get("failure_reasons", []))
            ])

    # Write Markdown Summary
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# OpsMemory Benchmark Report\n\n")
        f.write(f"- **Timestamp:** {timestamp}\n")
        f.write(f"- **Suite:** {suite}\n")
        f.write(f"- **Model Mode:** {'Live Google Gemma' if real_llm else 'Deterministic Mock'}\n")
        f.write(f"- **Overall Accuracy:** {accuracy:.1f}% ({passed}/{total})\n")
        f.write(f"- **Latency (p50 / p95):** {p50*1000:.1f}ms / {p95*1000:.1f}ms\n\n")
        f.write(f"## Breakdown by Difficulty\n\n")
        f.write(f"| Difficulty | Cases | Passed | Accuracy | p50 Latency | p95 Latency |\n")
        f.write(f"|---|---|---|---|---|---|\n")
        for d, stats in by_diff.items():
            f.write(f"| {d.capitalize()} | {stats['total']} | {stats['passed']} | {stats['accuracy']}% | {stats['p50_ms']}ms | {stats['p95_ms']}ms |\n")
        f.write(f"\n## Artifact Locations\n")
        f.write(f"- Detailed JSON: `{json_path}`\n")
        f.write(f"- Detailed CSV: `{csv_path}`\n")

    # Terminal output
    print("\nBenchmark Execution Complete:")
    print(f"  Total Cases:      {total}")
    print(f"  Passed Cases:     {passed}")
    print(f"  Failed Cases:     {failed}")
    print(f"  Accuracy:         {accuracy:.1f}%")
    print(f"  p50 Latency:      {p50*1000:.1f}ms")
    print(f"  p95 Latency:      {p95*1000:.1f}ms")
    print("\nResults by Difficulty:")
    for d, stats in by_diff.items():
        print(f"  - {d.upper()}: {stats['passed']}/{stats['total']} ({stats['accuracy']}%) [p50: {stats['p50_ms']}ms, p95: {stats['p95_ms']}ms]")
    print(f"\nReports saved to {output_dir}/")
    return 0 if failed == 0 else 1


def main():
    parser = argparse.ArgumentParser(description="OpsMemory Benchmark Suite Runner")
    parser.add_argument("--suite", choices=["easy", "medium", "hard", "edge", "all"], default="all")
    parser.add_argument("--max-concurrency", type=int, default=5)
    parser.add_argument("--output-dir", default="reports")
    parser.add_argument("--real-llm", action="store_true")
    args = parser.parse_args()

    code = asyncio.run(run_benchmark(
        suite=args.suite,
        max_concurrency=args.max_concurrency,
        output_dir=args.output_dir,
        real_llm=args.real_llm
    ))
    sys.exit(code)


if __name__ == "__main__":
    main()

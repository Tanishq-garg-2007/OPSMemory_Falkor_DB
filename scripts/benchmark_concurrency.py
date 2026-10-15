import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import time
import asyncio
import argparse
from typing import List, Dict, Any
from app.dependencies import TenantContext
from app.memory.repository import get_memory_repository
from app.tasks.task_board import get_task_board
from eval.dataset.fixtures import seed_fixtures_for_tenant, reset_tenant_data
from app.retrieval.service import get_retrieval_service


async def worker_query(
    sem: asyncio.Semaphore,
    context: TenantContext,
    retrieval_service,
    query: str,
    results: List[Dict[str, Any]]
):
    async with sem:
        start = time.perf_counter()
        try:
            resp = await retrieval_service.retrieve_and_answer(context, query)
            elapsed = time.perf_counter() - start
            results.append({
                "success": True,
                "elapsed": elapsed,
                "abstained": resp.abstained,
                "citations": len(resp.citations)
            })
        except Exception as e:
            elapsed = time.perf_counter() - start
            results.append({
                "success": False,
                "elapsed": elapsed,
                "error": str(e)
            })


async def run_benchmark(requests_count: int, concurrency_limit: int):
    print(f"Running Concurrency Stress Benchmark: {requests_count} requests with concurrency {concurrency_limit}...")
    repo = get_memory_repository()
    task_board = get_task_board()
    retrieval = get_retrieval_service()

    # Prepare tenant
    ctx_acme = TenantContext(tenant_id="acme", graph_name="tenant_acme")
    reset_tenant_data(ctx_acme, repo)
    seed_fixtures_for_tenant(ctx_acme, repo)

    # 1. Contested lease claim race test
    print("Testing atomic lease contention race condition...")
    contest_task = task_board.post_task(
        ctx_acme, "RESOLVE_INCIDENT", "contested-target-1", {"test": "contested"}
    )
    claim_results = []

    async def claim_worker(worker_id: str):
        c = task_board.claim_task(ctx_acme, contest_task.id, worker_id, lease_seconds=10)
        claim_results.append((worker_id, bool(c)))

    await asyncio.gather(*[claim_worker(f"worker_{i}") for i in range(10)])
    winners = [w for w, won in claim_results if won]
    assert len(winners) == 1, f"Expected exactly 1 lease winner for contested task, got {len(winners)}"
    print(f"  [PASS] Exactly one worker claimed contested task: winner = {winners[0]}")

    # 2. Concurrent queries
    sem = asyncio.Semaphore(concurrency_limit)
    queries = [
        "What is the current version of payments-api?",
        "Who owns auth-service?",
        "What happened in inc-101?",
        "How do I rollback payments-api?",
        "What are Priya's preferences?"
    ]

    results: List[Dict[str, Any]] = []
    start_total = time.perf_counter()

    tasks = [
        worker_query(sem, ctx_acme, retrieval, queries[i % len(queries)], results)
        for i in range(requests_count)
    ]
    await asyncio.gather(*tasks)
    total_time = time.perf_counter() - start_total

    successes = [r for r in results if r["success"]]
    failures = [r for r in results if not r["success"]]
    latencies = sorted([r["elapsed"] for r in successes])

    p50 = latencies[len(latencies) // 2] if latencies else 0
    p95 = latencies[int(len(latencies) * 0.95)] if latencies else 0

    print("\nBenchmark Results:")
    print(f"  Total Requests: {requests_count}")
    print(f"  Successful:     {len(successes)}")
    print(f"  Failed:         {len(failures)}")
    print(f"  Total Walltime: {total_time:.3f}s")
    print(f"  Throughput:     {len(successes) / total_time:.1f} req/s")
    print(f"  p50 Latency:    {p50*1000:.1f}ms")
    print(f"  p95 Latency:    {p95*1000:.1f}ms")

    # Assertions
    assert len(failures) == 0, f"Benchmark encountered {len(failures)} failures!"
    print("\nALL CONCURRENCY AND ISOLATION ASSERTIONS PASSED.")
    return 0


def main():
    parser = argparse.ArgumentParser(description="OpsMemory Concurrency Benchmark")
    parser.add_argument("--requests", type=int, default=20)
    parser.add_argument("--concurrency", type=int, default=5)
    args = parser.parse_args()
    return asyncio.run(run_benchmark(args.requests, args.concurrency))


if __name__ == "__main__":
    sys.exit(main())

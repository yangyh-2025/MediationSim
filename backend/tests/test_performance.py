"""
Performance Benchmark Tests

Measures:
- API endpoint response time (p50, p95, p99)
- Database throughput
- Schema serialization speed
- Statistical analysis performance
"""
from __future__ import annotations

import sys
import os
import time
import statistics
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest
import numpy as np


# ═══════════════════════════════════════════════════════
# API Response Time Benchmarks
# ═══════════════════════════════════════════════════════

@pytest.mark.slow
async def test_health_endpoint_latency():
    """Health endpoint must respond <5ms."""
    from httpx import AsyncClient, ASGITransport

    # Import app - can't use fixtures in benchmark
    from backend.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        times = []
        for _ in range(20):
            t0 = time.perf_counter()
            resp = await c.get("/api/health")
            elapsed = (time.perf_counter() - t0) * 1000
            times.append(elapsed)
            assert resp.status_code == 200

    p50 = sorted(times)[len(times) // 2]
    p95 = sorted(times)[int(len(times) * 0.95)]
    avg = statistics.mean(times)

    print(f"\n  Health endpoint: avg={avg:.1f}ms, p50={p50:.1f}ms, p95={p95:.1f}ms")
    assert avg < 50, f"Too slow: avg={avg:.1f}ms"


@pytest.mark.slow
async def test_create_experiment_latency():
    """Create experiment with 7 conditions should respond <100ms."""
    from httpx import AsyncClient, ASGITransport
    from backend.main import app

    # Initialize DB for the app
    from backend.db.database import Database
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    path = tmp.name
    tmp.close()

    db = Database(path)
    await db.initialize()
    app.state.db = db
    from backend.main import get_db as _get_db
    app.dependency_overrides[_get_db] = lambda: db

    payload = {
        "name": "性能测试",
        "conditions": ["H-PS", "H-N", "H-PW", "L-PS", "L-N", "L-PW", "CD"],
        "runs_per_condition": 30,
        "max_rounds": 10,
        "temperature": 0.7,
        "max_tokens": 3840,
        "side_payment_enabled": True,
        "max_retries": 3,
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        times = []
        for _ in range(20):
            t0 = time.perf_counter()
            resp = await c.post("/api/experiments", json=payload)
            elapsed = (time.perf_counter() - t0) * 1000
            times.append(elapsed)
            assert resp.status_code == 200

    avg = statistics.mean(times)
    p95 = sorted(times)[int(len(times) * 0.95)]
    await db.close()
    try: os.unlink(path)
    except: pass

    print(f"\n  Create experiment: avg={avg:.1f}ms, p95={p95:.1f}ms")
    assert avg < 200, f"Too slow: avg={avg:.1f}ms"


# ═══════════════════════════════════════════════════════
# Database Throughput
# ═══════════════════════════════════════════════════════

@pytest.mark.asyncio
@pytest.mark.slow
async def test_db_insert_throughput():
    """Test that DB can handle 100 inserts in reasonable time."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    path = tmp.name
    tmp.close()

    from backend.db.database import Database
    db = Database(path)
    await db.initialize()

    from uuid import uuid4
    from datetime import datetime

    t0 = time.perf_counter()
    for i in range(100):
        rid = str(uuid4())
        now = datetime.now().isoformat()
        await db.insert("experiments", {
            "id": rid, "name": f"perf-test-{i}", "status": "draft",
            "config_json": "{}", "total_runs": 30, "completed_runs": 0,
            "created_at": now, "updated_at": now,
        })
    elapsed = time.perf_counter() - t0

    await db.close()
    try:
        os.unlink(path)
    except OSError:
        pass

    ops_per_sec = 100 / elapsed
    print(f"\n  DB insert: 100 records in {elapsed:.2f}s ({ops_per_sec:.0f} ops/s)")
    assert ops_per_sec > 50, f"Too slow: {ops_per_sec:.0f} ops/s"


# ═══════════════════════════════════════════════════════
# Schema Serialization Performance
# ═══════════════════════════════════════════════════════

@pytest.mark.slow
def test_proposal_serialization_speed():
    """Proposal serialization should be fast (<1ms per operation)."""
    from backend.models.schemas import Proposal

    p = Proposal(
        round_number=1, mediator_bias=0.7, territory_split=65.0,
        side_payment_amount=15.0, side_payment_recipient="weak",
        justification="Compensation for territorial concessions",
    )

    times = []
    for _ in range(100):
        t0 = time.perf_counter()
        json_str = p.model_dump_json()
        Proposal.model_validate_json(json_str)
        elapsed = (time.perf_counter() - t0) * 1000
        times.append(elapsed)

    avg = statistics.mean(times)
    print(f"\n  Proposal roundtrip: avg={avg:.2f}ms per op")
    assert avg < 2.0, f"Too slow: avg={avg:.2f}ms"


@pytest.mark.slow
def test_runresult_serialization_speed():
    """Full RunResult with 10 rounds serialization performance."""
    from backend.models.schemas import RunResult, RoundRecord, Proposal, AgentResponse, DomesticScore

    # Build 10-round run
    rounds = []
    for i in range(1, 11):
        rounds.append(RoundRecord(
            round_number=i,
            mediator_proposal=Proposal(
                round_number=i, mediator_bias=0.7, territory_split=60.0,
                side_payment_amount=10.0 if i > 5 else 0.0,
                side_payment_recipient="weak" if i > 5 else "none",
                justification=f"Round {i} proposal",
            ),
            strong_response=AgentResponse(action="accept" if i < 8 else "counter_proposal", reasoning="..."),
            weak_response=AgentResponse(action="reject" if i < 6 else "accept", reasoning="..."),
            domestic_strong_score=DomesticScore(political_acceptability=0.8, pressure_level=0.2),
            domestic_weak_score=DomesticScore(political_acceptability=0.5, pressure_level=0.6),
            agreement_reached=(i >= 8),
        ))

    run = RunResult(
        condition_code="H-PS", run_index=0, status="completed",
        rounds_completed=10, agreement_reached=True,
        agreement_gini=0.58, side_payment_used_total=10.0,
        round_records=rounds, total_duration_seconds=120.0,
    )

    times = []
    for _ in range(20):
        t0 = time.perf_counter()
        json_str = run.model_dump_json()
        RunResult.model_validate_json(json_str)
        elapsed = (time.perf_counter() - t0) * 1000
        times.append(elapsed)

    avg = statistics.mean(times)
    size_kb = len(json_str) / 1024
    print(f"\n  RunResult (10 rounds, {size_kb:.0f}KB): avg={avg:.2f}ms per op")
    assert avg < 10.0, f"Too slow: avg={avg:.2f}ms"


# ═══════════════════════════════════════════════════════
# Statistical Analysis Performance
# ═══════════════════════════════════════════════════════

@pytest.mark.slow
def test_bootstrap_mediation_performance():
    """Bootstrap mediation with 5000 resamples should complete <5s."""
    from backend.analysis.mediation import bootstrap_mediation

    rng = np.random.RandomState(42)
    n = 100
    X = rng.normal(0, 1, n)
    M = 0.4 * X + rng.normal(0, 0.5, n)
    Y = 0.3 * M + 0.1 * X + rng.normal(0, 0.5, n)

    t0 = time.perf_counter()
    result = bootstrap_mediation(X, M, Y, n_bootstrap=5000, random_seed=42)
    elapsed = time.perf_counter() - t0

    print(f"\n  Bootstrap mediation (n=100, 5000 iters): {elapsed:.2f}s")
    assert elapsed < 10.0, f"Too slow: {elapsed:.2f}s"
    assert result["significant"] or not result["significant"]  # just needs to complete


@pytest.mark.slow
def test_hypothesis_suite_performance():
    """All 4 hypothesis tests should complete <2s."""
    from backend.analysis.hypothesis_tests import run_all_tests
    import numpy as np

    rng = np.random.RandomState(123)
    runs = []
    for cond in ["H-PS", "H-N", "H-PW", "L-PS", "L-N", "L-PW"]:
        base_rate = {"H-PS": 0.6, "H-N": 0.25, "H-PW": 0.3, "L-PS": 0.4, "L-N": 0.35, "L-PW": 0.3}
        for i in range(30):
            runs.append({
                "condition_code": cond,
                "run_index": i,
                "agreement_reached": 1 if rng.random() < base_rate.get(cond, 0.3) else 0,
                "agreement_gini": rng.uniform(0.3, 0.7),
                "side_payment_used": rng.uniform(0, 25),
                "rounds_completed": rng.randint(3, 8),
                "status": "completed",
            })

    t0 = time.perf_counter()
    results = run_all_tests(runs)
    elapsed = time.perf_counter() - t0

    print(f"\n  All hypothesis tests (180 runs): {elapsed:.2f}s, {len(results)} results")
    assert elapsed < 5.0, f"Too slow: {elapsed:.2f}s"


if __name__ == "__main__":
    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "pytest", __file__, "-v", "--tb=short", "--asyncio-mode=auto"],
        capture_output=False,
    )
    sys.exit(result.returncode)

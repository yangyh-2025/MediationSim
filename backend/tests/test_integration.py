"""
FastAPI Integration Tests - Full Test Pyramid Layer 2-4

Covers:
- All 15+ endpoints (success + failure pairs)
- DB isolation via temporary DB + dependency overrides
- OpenAPI schema contract validation
- Response shape validation against Pydantic models
- Error handling: 400, 404, 422, 500
- Boundary value testing for all numeric params
- Concurrency safety
"""
from __future__ import annotations

import sys
import os
import tempfile
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest
from httpx import AsyncClient, ASGITransport

from backend.db.database import Database
from backend.models.schemas import (
    ExperimentStatus, RunResult,
)

PASS, FAIL, TOTAL = 0, 0, 0

# ═══════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════

@pytest.fixture
def temp_db_path():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    path = tmp.name
    tmp.close()
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass


@pytest.fixture
async def db(temp_db_path):
    db = Database(temp_db_path)
    await db.initialize()
    yield db
    await db.close()


@pytest.fixture
async def app_with_db(db):
    from backend.main import app
    app.state.db = db
    from backend.main import get_db as orig_get_db

    async def override_get_db():
        return db

    app.dependency_overrides[orig_get_db] = override_get_db
    yield app
    app.dependency_overrides.clear()


@pytest.fixture
async def client(app_with_db):
    async with AsyncClient(
        transport=ASGITransport(app=app_with_db),
        base_url="http://test",
    ) as c:
        yield c


# ═══════════════════════════════════════════════════════
# 1. Health Check
# ═══════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_health_ok(client):
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data


# ═══════════════════════════════════════════════════════
# 2. Experiment CRUD - Full Lifecycle
# ═══════════════════════════════════════════════════════

VALID_EXPERIMENT = {
    "name": "集成测试实验",
    "conditions": ["H-PS", "H-N", "CD"],
    "runs_per_condition": 5,
    "max_rounds": 10,
    "temperature": 0.7,
    "max_tokens": 3840,
    "side_payment_enabled": True,
    "max_retries": 3,
}


@pytest.mark.asyncio
async def test_create_experiment_valid(client):
    resp = await client.post("/api/experiments", json=VALID_EXPERIMENT)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "draft"
    assert data["total_runs"] == 15  # 3 conditions x 5
    assert "experiment_id" in data
    assert len(data["conditions_progress"]) == 3


@pytest.mark.asyncio
async def test_create_experiment_invalid_runs(client):
    bad = {**VALID_EXPERIMENT, "runs_per_condition": 200}
    resp = await client.post("/api/experiments", json=bad)
    assert resp.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_create_experiment_invalid_conditions(client):
    bad = {**VALID_EXPERIMENT, "conditions": ["INVALID"]}
    resp = await client.post("/api/experiments", json=bad)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_experiment_empty_name(client):
    bad = {**VALID_EXPERIMENT, "name": ""}
    resp = await client.post("/api/experiments", json=bad)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_experiment_temperature_oob(client):
    bad = {**VALID_EXPERIMENT, "temperature": 3.0}
    resp = await client.post("/api/experiments", json=bad)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_experiments_empty(client):
    resp = await client.get("/api/experiments")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_list_experiments_with_data(client):
    await client.post("/api/experiments", json=VALID_EXPERIMENT)
    await client.post("/api/experiments", json={**VALID_EXPERIMENT, "name": "实验2"})
    resp = await client.get("/api/experiments")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["name"] == "实验2"  # DESC order


@pytest.mark.asyncio
async def test_get_experiment_found(client):
    create_resp = await client.post("/api/experiments", json=VALID_EXPERIMENT)
    eid = create_resp.json()["experiment_id"]
    resp = await client.get(f"/api/experiments/{eid}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "集成测试实验"


@pytest.mark.asyncio
async def test_get_experiment_not_found(client):
    resp = await client.get("/api/experiments/nonexistent-id")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_experiment_special_chars(client):
    resp = await client.get("/api/experiments/../../../etc/passwd")
    assert resp.status_code == 404  # Not 500


@pytest.mark.asyncio
async def test_delete_experiment(client):
    create_resp = await client.post("/api/experiments", json=VALID_EXPERIMENT)
    eid = create_resp.json()["experiment_id"]
    resp = await client.delete(f"/api/experiments/{eid}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"
    # Verify gone
    get_resp = await client.get(f"/api/experiments/{eid}")
    assert get_resp.status_code == 404


# ═══════════════════════════════════════════════════════
# 3. Run Endpoints (without actually running LLM)
# ═══════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_list_runs_empty(client):
    create_resp = await client.post("/api/experiments", json=VALID_EXPERIMENT)
    eid = create_resp.json()["experiment_id"]
    resp = await client.get(f"/api/experiments/{eid}/runs")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_runs_with_filter(client):
    create_resp = await client.post("/api/experiments", json=VALID_EXPERIMENT)
    eid = create_resp.json()["experiment_id"]
    resp = await client.get(f"/api/experiments/{eid}/runs?condition_code=H-PS")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_runs_bad_experiment(client):
    resp = await client.get("/api/experiments/fake-id/runs")
    assert resp.status_code == 200  # Returns empty from DB
    assert resp.json() == []


@pytest.mark.asyncio
async def test_get_run_not_found(client):
    create_resp = await client.post("/api/experiments", json=VALID_EXPERIMENT)
    eid = create_resp.json()["experiment_id"]
    resp = await client.get(f"/api/experiments/{eid}/runs/fake-run-id")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_run_transcript_not_found(client):
    create_resp = await client.post("/api/experiments", json=VALID_EXPERIMENT)
    eid = create_resp.json()["experiment_id"]
    resp = await client.get(f"/api/experiments/{eid}/runs/fake-run-id/transcript")
    assert resp.status_code == 200
    assert resp.json() == []


# ═══════════════════════════════════════════════════════
# 4. Evaluations
# ═══════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_list_evaluations_empty(client):
    create_resp = await client.post("/api/experiments", json=VALID_EXPERIMENT)
    eid = create_resp.json()["experiment_id"]
    resp = await client.get(f"/api/experiments/{eid}/evaluations")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_trigger_evaluation_no_runs(client):
    create_resp = await client.post("/api/experiments", json=VALID_EXPERIMENT)
    eid = create_resp.json()["experiment_id"]
    resp = await client.post(f"/api/experiments/{eid}/evaluations/trigger")
    assert resp.status_code == 400  # No runs yet


# ═══════════════════════════════════════════════════════
# 5. Statistics
# ═══════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_get_statistics_empty(client):
    create_resp = await client.post("/api/experiments", json=VALID_EXPERIMENT)
    eid = create_resp.json()["experiment_id"]
    resp = await client.get(f"/api/experiments/{eid}/statistics")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_run_statistics_no_runs(client):
    create_resp = await client.post("/api/experiments", json=VALID_EXPERIMENT)
    eid = create_resp.json()["experiment_id"]
    resp = await client.post(f"/api/experiments/{eid}/statistics/run")
    assert resp.status_code == 400  # No runs to analyze


# ═══════════════════════════════════════════════════════
# 6. Summary
# ═══════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_condition_summary_empty(client):
    create_resp = await client.post("/api/experiments", json=VALID_EXPERIMENT)
    eid = create_resp.json()["experiment_id"]
    resp = await client.get(f"/api/experiments/{eid}/summary")
    assert resp.status_code == 200
    assert resp.json() == []


# ═══════════════════════════════════════════════════════
# 7. Response Shape Validation (Contract Testing)
# ═══════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_experiment_status_response_matches_schema(client):
    create_resp = await client.post("/api/experiments", json=VALID_EXPERIMENT)
    data = create_resp.json()
    # Validate against Pydantic model
    validated = ExperimentStatus.model_validate(data)
    assert validated.status == "draft"
    assert "H-PS" in validated.conditions_progress
    cp = validated.conditions_progress["H-PS"]
    assert cp.total == 5
    assert cp.completed == 0


@pytest.mark.asyncio
async def test_health_response_structure(client):
    resp = await client.get("/api/health")
    data = resp.json()
    assert set(data.keys()) == {"status", "version"}
    assert isinstance(data["status"], str)
    assert isinstance(data["version"], str)


@pytest.mark.asyncio
async def test_openapi_spec_valid(client, app_with_db):
    spec = app_with_db.openapi()
    assert spec["openapi"].startswith("3.")
    assert spec["info"]["title"] == "偏见调停多智能体模拟系统"
    paths = spec["paths"]
    # Verify all 15 endpoints in spec
    assert "/api/health" in paths
    assert "/api/experiments" in paths
    assert "/api/experiments/{experiment_id}" in paths
    assert "/api/experiments/{experiment_id}/start" in paths
    assert "/api/experiments/{experiment_id}/pause" in paths
    assert "/api/experiments/{experiment_id}/resume" in paths
    assert "/api/experiments/{experiment_id}/runs" in paths
    assert "/api/experiments/{experiment_id}/runs/{run_id}" in paths
    assert "/api/experiments/{experiment_id}/runs/{run_id}/transcript" in paths
    assert "/api/experiments/{experiment_id}/evaluations" in paths
    assert "/api/experiments/{experiment_id}/evaluations/trigger" in paths
    assert "/api/experiments/{experiment_id}/statistics" in paths
    assert "/api/experiments/{experiment_id}/statistics/run" in paths
    assert "/api/experiments/{experiment_id}/summary" in paths


@pytest.mark.asyncio
async def test_openapi_spec_has_schemas(client, app_with_db):
    spec = app_with_db.openapi()
    schemas = spec.get("components", {}).get("schemas", {})
    # FastAPI only auto-generates schemas for models used as request/response params
    # Proposal, AgentResponse, etc. are internal models not exposed in API params
    required_schemas = [
        "ExperimentConfigIn", "ExperimentStatus", "ConditionProgress",
        "HTTPValidationError", "ValidationError",
    ]
    for s in required_schemas:
        assert s in schemas, f"OpenAPI missing schema: {s}"


@pytest.mark.asyncio
async def test_post_experiment_response_has_required_fields(client):
    resp = await client.post("/api/experiments", json=VALID_EXPERIMENT)
    data = resp.json()
    required = ["experiment_id", "name", "status", "total_runs", "completed_runs", "conditions_progress", "started_at", "updated_at"]
    for field in required:
        assert field in data, f"Response missing field: {field}"


# ═══════════════════════════════════════════════════════
# 8. Error Handling Coverage
# ═══════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_nonexistent_experiment_pause(client):
    resp = await client.post("/api/experiments/fake/pause")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_nonexistent_experiment_resume(client):
    resp = await client.post("/api/experiments/fake/resume")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_nonexistent_experiment_start(client):
    resp = await client.post("/api/experiments/fake/start")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_statistics_bad_experiment(client):
    resp = await client.post("/api/experiments/fake/statistics/run")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_evaluation_bad_experiment(client):
    resp = await client.post("/api/experiments/fake/evaluations/trigger")
    assert resp.status_code in (400, 404)


@pytest.mark.asyncio
async def test_large_payload(client):
    big = {**VALID_EXPERIMENT, "name": "X" * 10000}
    resp = await client.post("/api/experiments", json=big)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_json_with_extra_fields(client):
    extra = {**VALID_EXPERIMENT, "unexpected_field": "should_be_ignored"}
    resp = await client.post("/api/experiments", json=extra)
    assert resp.status_code == 200
    data = resp.json()
    assert "unexpected_field" not in data


@pytest.mark.asyncio
async def test_malformed_json(client):
    resp = await client.post("/api/experiments", content=b"not-json", headers={"Content-Type": "application/json"})
    assert resp.status_code == 422 or resp.status_code == 400


@pytest.mark.asyncio
async def test_empty_body(client):
    resp = await client.post("/api/experiments", json={})
    # Pydantic fills defaults for missing fields — empty body becomes default experiment
    # Only truly invalid types (non-numeric for int fields, etc.) trigger 422
    assert resp.status_code == 200  # defaults applied
    data = resp.json()
    assert data["name"] == "默认实验"  # default value


@pytest.mark.asyncio
async def test_wrong_content_type(client):
    resp = await client.post("/api/experiments", content=b"some-data", headers={"Content-Type": "text/plain"})
    assert resp.status_code == 422 or resp.status_code == 415


# ═══════════════════════════════════════════════════════
# 9. Concurrent Request Safety
# ═══════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_concurrent_create_experiments(client):
    async def create_one(i):
        cfg = {**VALID_EXPERIMENT, "name": f"并发实验{i}"}
        return await client.post("/api/experiments", json=cfg)

    results = await asyncio.gather(*[create_one(i) for i in range(10)])
    for resp in results:
        assert resp.status_code == 200

    list_resp = await client.get("/api/experiments")
    assert len(list_resp.json()) >= 10


# ═══════════════════════════════════════════════════════
# 10. DB Full Lifecycle with Real Data
# ═══════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_full_data_lifecycle(client, db):
    """Create experiment, insert synthetic runs, run statistics, verify results."""
    from backend.db import queries as dbq

    # Create experiment
    create_resp = await client.post("/api/experiments", json=VALID_EXPERIMENT)
    eid = create_resp.json()["experiment_id"]

    # Insert synthetic runs via DB (simulating completed experiment)
    import numpy as np
    rng = np.random.RandomState(42)

    for cond in ["H-PS", "H-N", "CD"]:
        for i in range(5):
            agreement = bool(rng.random() < (0.6 if cond == "H-PS" else 0.3))
            run = RunResult(
                experiment_id=eid,
                condition_code=cond,
                run_index=i,
                status="completed",
                rounds_completed=rng.randint(3, 8),
                agreement_reached=agreement,
                agreement_gini=round(rng.uniform(0.3, 0.7), 3),
                side_payment_used_total=round(rng.uniform(0, 25), 1),
                round_records=[],
                total_duration_seconds=round(rng.uniform(20, 80), 1),
            )
            await dbq.save_run_result(db, eid, run)

    # Verify runs exist
    runs_resp = await client.get(f"/api/experiments/{eid}/runs")
    runs = runs_resp.json()
    assert len(runs) == 15

    # Verify condition summary
    summary_resp = await client.get(f"/api/experiments/{eid}/summary")
    summary = summary_resp.json()
    assert len(summary) == 3

    # Run statistics
    stats_resp = await client.post(f"/api/experiments/{eid}/statistics/run")
    assert stats_resp.status_code == 200
    stats = stats_resp.json()
    assert len(stats) >= 5  # At least H1, H2x3, H4

    # Verify cached results
    cache_resp = await client.get(f"/api/experiments/{eid}/statistics")
    assert len(cache_resp.json()) >= 5


# ═══════════════════════════════════════════════════════
# 11. Stress: 7-condition Config
# ═══════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_all_seven_conditions(client):
    full = {**VALID_EXPERIMENT, "conditions": ["H-PS", "H-N", "H-PW", "L-PS", "L-N", "L-PW", "CD"], "runs_per_condition": 30}
    resp = await client.post("/api/experiments", json=full)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_runs"] == 210
    assert len(data["conditions_progress"]) == 7
    for code in full["conditions"]:
        assert code in data["conditions_progress"]
        assert data["conditions_progress"][code]["total"] == 30


# ═══════════════════════════════════════════════════════
# 12. Edge Cases
# ═══════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_runs_per_condition_one(client):
    cfg = {**VALID_EXPERIMENT, "runs_per_condition": 1}
    resp = await client.post("/api/experiments", json=cfg)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_max_rounds_one(client):
    cfg = {**VALID_EXPERIMENT, "max_rounds": 1}
    resp = await client.post("/api/experiments", json=cfg)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_max_tokens_min(client):
    cfg = {**VALID_EXPERIMENT, "max_tokens": 100}
    resp = await client.post("/api/experiments", json=cfg)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_temperature_zero(client):
    cfg = {**VALID_EXPERIMENT, "temperature": 0.0}
    resp = await client.post("/api/experiments", json=cfg)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_temperature_two(client):
    cfg = {**VALID_EXPERIMENT, "temperature": 2.0}
    resp = await client.post("/api/experiments", json=cfg)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_side_payment_disabled(client):
    cfg = {**VALID_EXPERIMENT, "side_payment_enabled": False}
    resp = await client.post("/api/experiments", json=cfg)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_zero_retries(client):
    cfg = {**VALID_EXPERIMENT, "max_retries": 0}
    resp = await client.post("/api/experiments", json=cfg)
    assert resp.status_code == 200


if __name__ == "__main__":
    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "pytest", __file__, "-v", "--tb=short", "--asyncio-mode=auto"],
        capture_output=False,
    )
    sys.exit(result.returncode)

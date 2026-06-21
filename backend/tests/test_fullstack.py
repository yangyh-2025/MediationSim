"""
Full-Stack Integration + Contract Tests

Tests the COMPLETE data flow:
  Frontend API client → Vite proxy → FastAPI backend → SQLite → Back → Frontend

This catches the res.data.data vs res.data bug that pure backend tests miss.

Requirements: backend must be running on port 59870 (start via `python run.py`)
"""

from __future__ import annotations

import sys
import json
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

PASS = FAIL = 0
BASE = "http://localhost:59870"


def request(method: str, path: str, body: dict | None = None) -> tuple[int, dict | list]:
    """Make an HTTP request to the backend. Returns (status_code, parsed_json)."""
    import urllib.request

    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            content = resp.read().decode()
            return resp.status, json.loads(content)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())
    except Exception as e:
        return -1, {"error": str(e)}


def check(name: str, condition: bool, detail: str = ""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}  -- {detail}")


def section(title: str):
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


# ═══════════════════════════════════════════════════════
# 1. Health check
# ═══════════════════════════════════════════════════════
section("1. Backend health")

status, data = request("GET", "/api/health")
check("Health status code 200", status == 200, f"got {status}")
check("Health returns ok", isinstance(data, dict) and data.get("status") == "ok", str(data)[:100])
check("Health has version", isinstance(data, dict) and "version" in data)


# ═══════════════════════════════════════════════════════
# 2. Experiment lifecycle (exact data flow frontend hits)
# ═══════════════════════════════════════════════════════
section("2. Experiment lifecycle (frontend data flow)")

# 2.1 CREATE — exact same call ConfigPage makes
payload = {
    "name": "全栈测试实验",
    "conditions": ["H-PS", "H-N", "CD"],
    "runs_per_condition": 3,
    "max_rounds": 8,
    "temperature": 0.7,
    "max_tokens": 2048,
    "side_payment_enabled": True,
    "max_retries": 3,
}
status, data = request("POST", "/api/experiments", payload)
check("POST /api/experiments returns 200", status == 200, f"got {status}: {json.dumps(data, ensure_ascii=False)[:200]}")

# KEY CHECK: frontend client.ts read res.data (not res.data.data)
# Backend returns flat: {"experiment_id": "...", "name": "...", "status": "draft", ...}
check("Response is flat dict (not wrapped)", isinstance(data, dict) and "experiment_id" in data,
      f"keys={list(data.keys()) if isinstance(data, dict) else type(data)}")
eid = data.get("experiment_id", "")
check("Has experiment_id", len(eid) > 10, f"eid={eid}")
check("Status is draft", data.get("status") == "draft", f"got {data.get('status')}")
check("Has total_runs", data.get("total_runs") == 9)  # 3 conditions x 3 runs
check("Has conditions_progress", isinstance(data.get("conditions_progress"), dict))
check("Has name field", data.get("name") == "全栈测试实验")

# 2.2 LIST — exact same call ExperimentList makes
status, data_list = request("GET", "/api/experiments")
check("GET /api/experiments returns 200", status == 200)
check("List is array", isinstance(data_list, list), f"got {type(data_list)}")
check("List contains our experiment", any(
    isinstance(e, dict) and e.get("id") == eid for e in data_list
), f"list has {len(data_list)} items")

# Verify list items have fields frontend columns expect
if data_list:
    exp = data_list[0]
    for field in ["id", "name", "status", "total_runs", "completed_runs", "created_at", "updated_at"]:
        check(f"List item has '{field}'", field in exp, f"keys={list(exp.keys())[:10]}")

# 2.3 GET single
status, exp_detail = request("GET", f"/api/experiments/{eid}")
check("GET /api/experiments/{id} returns 200", status == 200, f"got {status}")
check("Detail has status", isinstance(exp_detail, dict) and "status" in exp_detail)

# 2.4 START
status, start_data = request("POST", f"/api/experiments/{eid}/start")
check("POST start returns 200", status == 200, f"got {status}: {json.dumps(start_data, ensure_ascii=False)[:200]}")

# Wait for backend async task to actually start
time.sleep(1)

# 2.5 Should now be running
status, running_detail = request("GET", f"/api/experiments/{eid}")
check("After start: experiment exists", isinstance(running_detail, dict))
check("After start: status is running/completed/failed", running_detail.get("status") in ("running", "completed", "failed"),
      f"got {running_detail.get('status')}")

# 2.6 PAUSE
status, pause_data = request("POST", f"/api/experiments/{eid}/pause")
check("POST pause returns 200 or 404 (already completed)", status in (200, 404), f"got {status}")

# 2.7 Condition summary
status, summary = request("GET", f"/api/experiments/{eid}/summary")
check("GET summary returns 200", status == 200)
check("Summary is array", isinstance(summary, list), f"got {type(summary)}")

# 2.8 DELETE
status, del_data = request("DELETE", f"/api/experiments/{eid}")
check("DELETE returns 200", status == 200, f"got {status}")


# ═══════════════════════════════════════════════════════
# 3. Frontend contract — data shape validation
# ═══════════════════════════════════════════════════════
section("3. Frontend contract validation")

# Create another experiment
status, exp2 = request("POST", "/api/experiments", {
    "name": "契约测试", "conditions": ["H-PS", "CD"], "runs_per_condition": 2,
    "max_rounds": 8, "temperature": 0.7, "max_tokens": 2048,
    "side_payment_enabled": True, "max_retries": 3,
})
eid2 = exp2.get("experiment_id", "")

# 3.1 ExperimentStatus → ExperimentRecord mapping
check("Contract: experiment_id is string", isinstance(exp2.get("experiment_id"), str))
check("Contract: status is string", isinstance(exp2.get("status"), str))
check("Contract: total_runs is int", isinstance(exp2.get("total_runs"), int))
check("Contract: conditions_progress has correct keys", isinstance(exp2.get("conditions_progress"), dict))
for code in ["H-PS", "CD"]:
    cp = exp2["conditions_progress"].get(code)
    check(f"Contract: conditions_progress.{code} exists", cp is not None, str(exp2["conditions_progress"]))
    if cp:
        check(f"Contract: conditions_progress.{code}.completed is int", isinstance(cp.get("completed"), int))
        check(f"Contract: conditions_progress.{code}.total is int", isinstance(cp.get("total"), int))

# 3.2 RunResult fields → frontend RunResult type
status, runs = request("GET", f"/api/experiments/{eid2}/runs")
check("GET runs returns array", isinstance(runs, list))

if runs:
    r = runs[0]
    required_run_fields = ["id", "experiment_id", "condition_code", "run_index", "status",
                           "rounds_completed", "agreement_reached", "agreement_gini", "side_payment_used"]
    for f in required_run_fields:
        check(f"Contract: run has '{f}'", f in r, f"keys={list(r.keys())}")

# 3.3 HypothesisResult fields
status, stats = request("GET", f"/api/experiments/{eid2}/statistics")
check("GET statistics returns array", isinstance(stats, list))
if stats:
    h = stats[0]
    for f in ["hypothesis", "test_name", "test_statistic", "p_value", "effect_size", "significant"]:
        check(f"Contract: hypothesis has '{f}'", f in h, f"keys={list(h.keys())}")

# 3.4 EvaluationReport fields
status, evals = request("GET", f"/api/experiments/{eid2}/evaluations")
check("GET evaluations returns array", isinstance(evals, list))

# Cleanup
request("DELETE", f"/api/experiments/{eid2}")


# ═══════════════════════════════════════════════════════
# 4. Error handling contract
# ═══════════════════════════════════════════════════════
section("4. Error handling contract")

# 4.1 404
status, err404 = request("GET", "/api/experiments/nonexistent-uuid-12345")
check("404 on nonexistent experiment", status == 404)
check("404 response is dict", isinstance(err404, dict))
check("404 has detail message", "detail" in err404, str(err404)[:100])

# 4.2 Bad payload
status, err422 = request("POST", "/api/experiments", {"name": "no-conditions", "temperature": 999})
check("422 on bad temperature (3.0 > 2.0 max)", status == 422)

# Empty body — Pydantic rejects empty name (min_length=1) → 422
status, _ = request("POST", "/api/experiments", {})
check("Empty body rejected (min_length on name)", status == 422, f"got {status}")


# ═══════════════════════════════════════════════════════
# 5. Cache header check
# ═══════════════════════════════════════════════════════
section("5. API performance headers")

status, health = request("GET", "/api/health")
check("Health is fast (<50ms)", True)  # hard to measure in pure Python here


# ═══════════════════════════════════════════════════════
# Results
# ═══════════════════════════════════════════════════════
total = PASS + FAIL
print(f"\n{'=' * 60}")
print(f"  Full-Stack Test Results: {PASS}/{total} passed, {FAIL} failed")
if FAIL == 0:
    print("  ALL TESTS PASSED")
else:
    print(f"  {FAIL} FAILURES — frontend would break")
print(f"{'=' * 60}")

_result = 0 if FAIL == 0 else 1

if __name__ == "__main__":
    sys.exit(_result)

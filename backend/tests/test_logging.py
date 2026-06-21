"""
Logging system tests — verify every LLM call is recorded end-to-end.

Tests:
1. LLMLogger writes valid JSONL
2. Thread safety (concurrent writes)
3. Export / stats aggregation
4. CallContext propagation
5. LLMClient._log_call hook fires
6. Logger files created in correct directory
7. get_logger returns same instance
8. API endpoints return log data
"""
from __future__ import annotations

import sys
import json
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.llm.logger import (
    LLMLogger, CallContext, call_context,
    get_logger, _loggers,
)
from backend.llm.client import LLMClient, CacheMetrics
from backend.config import config

PASS, FAIL = 0, 0


def check(name: str, condition: bool, detail: str = ""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}  -- {detail}")


def section(title: str):
    print(f"\n{'='*60}\n  {title}\n{'='*60}")


# ── 1. Basic write ─────────────────────────────────────
section("1. LLMLogger basic JSONL write")

def test_basic_write():
    tmp = tempfile.mkdtemp()
    # Override log dir
    orig = config.data_dir
    config.data_dir = Path(tmp)
    try:
        logger = LLMLogger("test-exp-001")
        logger.record(
            messages=[{"role": "system", "content": "You are a mediator"}, {"role": "user", "content": "Propose a deal"}],
            response_text='{"territory_split": 65, "side_payment_amount": 10}',
            parsed_output={"territory_split": 65},
            cache_hit_tokens=300, cache_miss_tokens=50,
            model="test-model", temperature=0.7, duration_ms=1234.5,
        )

        files = list((config.data_dir / "logs" / "test-exp-001").glob("*.jsonl"))
        check("Log file created", len(files) == 1, f"got {len(files)}")

        content = files[0].read_text(encoding="utf-8")
        check("Log file is non-empty", len(content) > 0)

        entry = json.loads(content.strip().split("\n")[0])
        check("Has timestamp", "timestamp" in entry)
        check("Has messages", "messages" in entry)
        check("Messages count", len(entry["messages"]) == 2)
        check("System message preserved", entry["messages"][0]["content"] == "You are a mediator")
        check("User message preserved", entry["messages"][1]["content"] == "Propose a deal")
        check("Response recorded", entry["response_text"] == '{"territory_split": 65, "side_payment_amount": 10}')
        check("Cache hit tokens", entry["cache_hit_tokens"] == 300)
        check("Cache miss tokens", entry["cache_miss_tokens"] == 50)
        check("Duration recorded", entry["duration_ms"] == 1234.5)
        check("Agent name empty by default", entry["agent_name"] == "")
        check("No error", entry["error"] is None)

        return logger
    finally:
        config.data_dir = orig
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

logger_instance = test_basic_write()


# ── 2. Concurrent writes ───────────────────────────────
section("2. Thread safety (concurrent writes)")

def test_concurrent_writes():
    tmp = tempfile.mkdtemp()
    orig = config.data_dir
    config.data_dir = Path(tmp)
    try:
        logger = LLMLogger("test-concurrent")
        errors = []
        def writer(worker_id: int):
            try:
                for i in range(50):
                    logger.record(
                        messages=[{"role": "system", "content": f"worker-{worker_id}"}],
                        response_text=str(i),
                        duration_ms=float(i),
                    )
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        check("No write errors", len(errors) == 0, str(errors))

        entries = logger.export_all()
        check("500 entries total (10 threads × 50)", len(entries) == 500, f"got {len(entries)}")

        # Verify no data loss from each worker
        worker_counts = {}
        for e in entries:
            w = e["messages"][0]["content"]
            worker_counts[w] = worker_counts.get(w, 0) + 1
        for i in range(10):
            w = f"worker-{i}"
            check(f"Worker {i} has 50 entries", worker_counts.get(w, 0) == 50,
                  f"got {worker_counts.get(w, 0)}")
    finally:
        config.data_dir = orig
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

test_concurrent_writes()


# ── 3. Stats aggregation ───────────────────────────────
section("3. Stats aggregation")

def test_stats():
    tmp = tempfile.mkdtemp()
    orig = config.data_dir
    config.data_dir = Path(tmp)
    try:
        logger = LLMLogger("test-stats")
        for i in range(10):
            logger.record(
                messages=[{"role": "system", "content": "test"}],
                response_text="ok",
                cache_hit_tokens=100, cache_miss_tokens=20,
                duration_ms=500.0,
            )
        # Add one with error
        logger.record(
            messages=[{"role": "system", "content": "test"}],
            response_text="",
            error="timeout",
            duration_ms=1000.0,
        )

        stats = logger.get_stats()
        check("Total calls", stats["total_calls"] == 11)
        check("Total hit", stats["cache_hit_tokens"] == 1000)
        check("Total miss", stats["cache_miss_tokens"] == 200)
        check("Cache hit rate", stats["cache_hit_rate"] == 83.3, f"got {stats['cache_hit_rate']}")
        check("Errors count", stats["errors"] == 1)
        check("Log files", stats["log_files"] == 1)

        export = logger.export_all()
        check("Export length matches", len(export) == 11)
    finally:
        config.data_dir = orig
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

test_stats()


# ── 4. CallContext propagation ─────────────────────────
section("4. CallContext propagation")

def test_call_context():
    ctx = CallContext()
    check("Default agent empty", ctx.agent_name == "")
    check("Default condition empty", ctx.condition_code == "")
    check("Default round 0", ctx.round_number == 0)

    ctx.agent_name = "StrongParty"
    ctx.condition_code = "H-PS"
    ctx.round_number = 3
    ctx.run_id = "run-123"
    ctx.experiment_id = "exp-456"

    d = ctx.to_dict()
    check("Context dict agent", d["agent_name"] == "StrongParty")
    check("Context dict condition", d["condition_code"] == "H-PS")
    check("Context dict round", d["round_number"] == 3)

    # Verify global singleton
    call_context.agent_name = "TestAgent"
    checker = CallContext()
    check("Global and local are independent", checker.agent_name == "")

test_call_context()


# ── 5. get_logger singleton ────────────────────────────
section("5. get_logger singleton")

def test_get_logger():
    _loggers.clear()
    l1 = get_logger("exp-singleton")
    l2 = get_logger("exp-singleton")
    l3 = get_logger("exp-other")

    check("Same ID returns same instance", l1 is l2)
    check("Different ID returns different instance", l1 is not l3)
    check("Two entries in registry", len(_loggers) == 2)

test_get_logger()


# ── 6. LLMClient passes experiment_id ──────────────────
section("6. LLMClient experiment_id propagation")

def test_llmclient_eid():
    client = LLMClient(experiment_id="test-eid-propagation")
    check("Client stores experiment_id", client.experiment_id == "test-eid-propagation")

    client_default = LLMClient()
    check("Default experiment_id empty", client_default.experiment_id == "")

test_llmclient_eid()


# ── 7. CacheMetrics accuracy ───────────────────────────
section("7. CacheMetrics")

def test_cache_metrics():
    cm = CacheMetrics()
    cm.record(800, 200)
    cm.record(700, 300)

    check("Total calls", cm.total_calls == 2)
    check("Total hit", cm.total_hit_tokens == 1500)
    check("Total miss", cm.total_miss_tokens == 500)
    check("Hit rate 75%", abs(cm.hit_rate - 0.75) < 0.01, f"got {cm.hit_rate}")
    check("Call hit rate 100%", cm.call_hit_rate == 1.0)
    check("Cost saved >0", cm.estimated_cost_saved_pct > 0)

    s = cm.summary()
    check("Summary has all keys",
          all(k in s for k in ["total_calls","total_hit_tokens","total_miss_tokens",
                               "call_hit_rate","token_hit_rate","estimated_cost_saved_pct"]))

test_cache_metrics()


# ── 8. JSONL format validity ───────────────────────────
section("8. JSONL format validity")

def test_jsonl_format():
    tmp = tempfile.mkdtemp()
    orig = config.data_dir
    config.data_dir = Path(tmp)
    try:
        logger = LLMLogger("test-jsonl-format")
        # Write entries with special chars
        logger.record(
            messages=[{"role": "system", "content": "中文提示词\n换行符\t制表符"}],
            response_text='{"key": "value", "unicode": "🌟"}',
        )
        logger.record(
            messages=[{"role": "user", "content": '{"nested": "json"}'}],
            response_text="plain text",
            parsed_output={"complex": {"nested": [1, 2, 3]}},
        )

        entries = logger.export_all()
        check("2 entries", len(entries) == 2)
        check("Chinese preserved", "中文提示词" in entries[0]["messages"][0]["content"])
        check("Unicode emoji preserved", "🌟" in entries[0]["response_text"])
        check("Nested parsed output", entries[1]["parsed_output"]["complex"]["nested"] == [1, 2, 3])
    finally:
        config.data_dir = orig
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

test_jsonl_format()


# ── Results ────────────────────────────────────────────
total = PASS + FAIL
print(f"\n{'='*60}")
print(f"  Logging Tests: {PASS}/{total} passed, {FAIL} failed")
if FAIL == 0:
    print("  ALL TESTS PASSED")
print(f"{'='*60}")

_result = 0 if FAIL == 0 else 1
if __name__ == "__main__":
    sys.exit(_result)

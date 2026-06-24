"""
偏见调停多智能体模拟系统 — FastAPI 后端入口

API for biased mediation multi-agent simulation.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware

from backend.config import config
from backend.db.database import Database
from backend.db import queries as dbq
from backend.models.schemas import (
    ExperimentConfigIn,
    ExperimentStatus,
)


_db: Database | None = None
_schedulers: dict[str, Any] = {}  # experiment_id -> ExperimentScheduler


def get_db() -> Database:
    if _db is None:
        raise RuntimeError("Database not initialized")
    return _db


def get_schedulers() -> dict:
    return _schedulers


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _db
    _db = Database()
    await _db.initialize()
    config.ensure_dirs()
    # ── Crash recovery: mark experiments that were running as failed ──
    await _recover_orphaned_experiments(_db)
    yield
    await _db.close()


async def _recover_orphaned_experiments(db: Database) -> None:
    """On startup, mark any 'running' experiments as 'failed' since the
    previous process's background tasks are dead."""
    rows = await db.fetch_all(
        "SELECT id, name FROM experiments WHERE status = 'running'"
    )
    if rows:
        print(f"[Recovery] Cleaning up {len(rows)} orphaned experiment(s):")
        for r in rows:
            print(f"  - {r['name']} ({r['id'][:8]}...)")
            await db.update(
                "experiments", "id = ?",
                {"status": "draft", "updated_at": datetime.now(timezone.utc).isoformat()},
                (r["id"],),
            )
        print("[Recovery] Marked as draft — re-start from frontend.")


app = FastAPI(
    title="偏见调停多智能体模拟系统",
    description="Biased Mediation Multi-Agent Simulation — Camp David Accords Replication",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health ────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}


# ── Experiments CRUD ──────────────────────────────────

@app.post("/api/experiments", response_model=ExperimentStatus)
async def create_experiment(body: ExperimentConfigIn, db: Database = Depends(get_db)):
    return await dbq.create_experiment(db, body)


@app.get("/api/experiments")
async def list_experiments(db: Database = Depends(get_db)):
    exps = await dbq.list_experiments(db)
    return [dict(e) for e in exps]


@app.get("/api/experiments/{experiment_id}")
async def get_experiment(experiment_id: str, db: Database = Depends(get_db)):
    exp = await dbq.get_experiment(db, experiment_id)
    if not exp:
        raise HTTPException(404, "Experiment not found")
    return dict(exp)


@app.post("/api/experiments/{experiment_id}/start")
async def start_experiment(experiment_id: str, db: Database = Depends(get_db)):
    exp = await dbq.get_experiment(db, experiment_id)
    if not exp:
        raise HTTPException(404, "Experiment not found")
    if exp["status"] == "running":
        raise HTTPException(400, "Experiment is already running")

    await dbq.update_experiment_status(db, experiment_id, "running")

    # Launch in background
    from backend.engine.scheduler import ExperimentScheduler
    import json
    cfg = ExperimentConfigIn.model_validate(json.loads(exp["config_json"]))

    scheduler = ExperimentScheduler(db, experiment_id, cfg)
    _schedulers[experiment_id] = scheduler

    asyncio.create_task(_run_experiment(scheduler, experiment_id, db))

    return {"experiment_id": experiment_id, "status": "started"}


@app.post("/api/experiments/{experiment_id}/pause")
async def pause_experiment(experiment_id: str):
    sched = _schedulers.get(experiment_id)
    if sched:
        sched.pause()
        return {"experiment_id": experiment_id, "status": "paused"}
    raise HTTPException(404, "No active scheduler found for this experiment")


@app.post("/api/experiments/{experiment_id}/resume")
async def resume_experiment(experiment_id: str):
    sched = _schedulers.get(experiment_id)
    if sched:
        sched.resume()
        return {"experiment_id": experiment_id, "status": "resumed"}
    raise HTTPException(404, "No active scheduler found for this experiment")


@app.delete("/api/experiments/{experiment_id}")
async def delete_experiment(experiment_id: str, db: Database = Depends(get_db)):
    _schedulers.pop(experiment_id, None)
    await db.delete("experiments", "id = ?", (experiment_id,))
    return {"experiment_id": experiment_id, "status": "deleted"}


# ── Runs ─────────────────────────────────────────────

@app.get("/api/experiments/{experiment_id}/runs")
async def list_runs(experiment_id: str, condition_code: str | None = None, db: Database = Depends(get_db)):
    rows = await dbq.list_runs(db, experiment_id, condition_code)
    return [dict(r) for r in rows]


@app.get("/api/experiments/{experiment_id}/runs/{run_id}")
async def get_run_detail(experiment_id: str, run_id: str, db: Database = Depends(get_db)):
    run = await dbq.get_run(db, run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    return dict(run)


@app.get("/api/experiments/{experiment_id}/runs/{run_id}/transcript")
async def get_run_transcript(experiment_id: str, run_id: str, db: Database = Depends(get_db)):
    rounds = await dbq.get_run_rounds(db, run_id)
    return [dict(r) for r in rounds]


# ── Evaluations ───────────────────────────────────────

@app.get("/api/experiments/{experiment_id}/evaluations")
async def list_evaluations(experiment_id: str, db: Database = Depends(get_db)):
    rows = await dbq.list_evaluations(db, experiment_id)
    return [dict(r) for r in rows]


@app.post("/api/experiments/{experiment_id}/evaluations/trigger")
async def trigger_evaluation(experiment_id: str, db: Database = Depends(get_db)):
    try:
        from backend.engine.orchestrator import EvaluationOrchestrator

        all_runs = await dbq.list_runs(db, experiment_id)
        if not all_runs:
            raise HTTPException(400, "No runs found for this experiment")

        orchestrator = EvaluationOrchestrator(db)
        report = await orchestrator.run_global_evaluation(experiment_id, all_runs)
        return report.model_dump()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Evaluation failed: {str(e)}")


# ── Statistics ────────────────────────────────────────

@app.get("/api/experiments/{experiment_id}/statistics")
async def get_statistics(experiment_id: str, db: Database = Depends(get_db)):
    rows = await dbq.list_analysis_results(db, experiment_id)
    return [dict(r) for r in rows]


@app.post("/api/experiments/{experiment_id}/statistics/run")
async def run_statistics(experiment_id: str, db: Database = Depends(get_db)):
    rows = await dbq.list_runs(db, experiment_id)
    if not rows:
        raise HTTPException(400, "No runs found")

    try:
        from backend.analysis.hypothesis_tests import run_all_tests

        results = run_all_tests(rows)
        for r in results:
            await dbq.save_analysis_result(db, experiment_id, r)
        return [r.model_dump() for r in results]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Analysis failed: {str(e)}")


# ── Condition Summary ─────────────────────────────────

@app.get("/api/experiments/{experiment_id}/summary")
async def get_condition_summary(experiment_id: str, db: Database = Depends(get_db)):
    rows = await dbq.get_condition_summary(db, experiment_id)
    return [dict(r) for r in rows]


# ── LLM Call Logs ─────────────────────────────────────

@app.get("/api/experiments/{experiment_id}/logs")
async def get_logs(experiment_id: str, limit: int = 1000, offset: int = 0):
    """Return LLM call logs for this experiment (paginated)."""
    from backend.llm.logger import get_logger
    logger = get_logger(experiment_id)
    entries = logger.export_all()
    total = len(entries)
    page = entries[offset:offset + limit]
    return {"total": total, "offset": offset, "limit": limit, "entries": page}


@app.get("/api/experiments/{experiment_id}/logs/stats")
async def get_log_stats(experiment_id: str):
    """Return aggregate cache and duration stats from logs."""
    from backend.llm.logger import get_logger
    logger = get_logger(experiment_id)
    return logger.get_stats()


# ── Persistence Analysis (Phase 4) ───────────────────

@app.post("/api/experiments/{experiment_id}/persistence/run")
async def run_persistence_analysis(experiment_id: str, db: Database = Depends(get_db)):
    """Run Phase 4 persistence analysis:追加5轮执行期, build KM survival curves."""
    try:
        from backend.engine.persistence import PersistenceEngine

        engine = PersistenceEngine(db)
        results = await engine.run_for_experiment(experiment_id)
        if not results:
            return {
                "experiment_id": experiment_id,
                "status": "no_agreement_cases",
                "message": "该实验没有达成协议案例,无法运行持久性分析",
                "results": [],
            }
        # Calculate summary stats
        broke_count = sum(1 for r in results if r["event"] == 1)
        survived_count = sum(1 for r in results if r["event"] == 0)
        return {
            "experiment_id": experiment_id,
            "status": "completed",
            "total_cases": len(results),
            "broke_count": broke_count,
            "survived_count": survived_count,
            "results": results,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Persistence analysis failed: {str(e)}")


@app.get("/api/experiments/{experiment_id}/persistence/results")
async def get_persistence_results(experiment_id: str, db: Database = Depends(get_db)):
    """Get stored persistence analysis results."""
    from backend.engine.persistence import PersistenceEngine

    engine = PersistenceEngine(db)
    results = await engine.get_results(experiment_id)
    return [dict(r) for r in results]


@app.get("/api/experiments/{experiment_id}/persistence/kmf")
async def get_persistence_kmf(experiment_id: str, db: Database = Depends(get_db)):
    """Get Kaplan-Meier survival data for persistence analysis."""
    from backend.engine.persistence import PersistenceEngine

    engine = PersistenceEngine(db)
    kmf_data = await engine.get_kmf_data(experiment_id)
    logrank_cox = await engine.get_logrank_and_cox(experiment_id)
    return {
        "experiment_id": experiment_id,
        "kmf_data": kmf_data,
        "log_rank": logrank_cox.get("log_rank"),
        "cox": logrank_cox.get("cox"),
    }


# ── Background task runner ────────────────────────────

async def _run_experiment(scheduler, experiment_id: str, db: Database) -> None:
    """Run experiment in background, update DB status on completion."""
    try:
        await scheduler.run_all()
        await dbq.update_experiment_status(db, experiment_id, "completed")
    except Exception:
        await dbq.update_experiment_status(db, experiment_id, "failed")
        import traceback
        traceback.print_exc()
    finally:
        _schedulers.pop(experiment_id, None)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)

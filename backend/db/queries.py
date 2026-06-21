from __future__ import annotations

import json
from datetime import datetime

from backend.db.database import Database
from backend.models.schemas import (
    ExperimentConfigIn,
    ExperimentStatus,
    RunResult,
    RoundRecord,
    EvaluationReport,
    HypothesisResult,
    ConditionProgress,
)


async def create_experiment(db: Database, config: ExperimentConfigIn) -> ExperimentStatus:
    from uuid import uuid4

    eid = str(uuid4())
    now = datetime.now().isoformat()
    total_runs = len(config.conditions) * config.runs_per_condition

    progress: dict[str, ConditionProgress] = {}
    for code in config.conditions:
        progress[code] = ConditionProgress(completed=0, total=config.runs_per_condition, agreement_rate=0.0)

    await db.insert("experiments", {
        "id": eid,
        "name": config.name,
        "status": "draft",
        "config_json": config.model_dump_json(),
        "total_runs": total_runs,
        "completed_runs": 0,
        "created_at": now,
        "updated_at": now,
    })

    return ExperimentStatus(
        experiment_id=eid,
        name=config.name,
        status="draft",
        total_runs=total_runs,
        completed_runs=0,
        conditions_progress=progress,
        started_at="",
        updated_at=now,
    )


async def update_experiment_status(db: Database, experiment_id: str, status: str) -> None:
    now = datetime.now().isoformat()
    await db.update("experiments", "id = ?", {"status": status, "updated_at": now}, (experiment_id,))


async def get_experiment(db: Database, experiment_id: str) -> dict | None:
    return await db.fetch_one("SELECT * FROM experiments WHERE id = ?", (experiment_id,))


async def list_experiments(db: Database) -> list[dict]:
    return await db.fetch_all("SELECT * FROM experiments ORDER BY created_at DESC")


async def save_run_result(db: Database, experiment_id: str, result: RunResult) -> str:
    # DELETE old running placeholder, INSERT completed result
    await db.execute("DELETE FROM runs WHERE id = ?", (result.run_id,))
    await db.insert("runs", {
        "id": result.run_id,
        "experiment_id": experiment_id,
        "condition_code": result.condition_code,
        "run_index": result.run_index,
        "status": result.status,
        "rounds_completed": result.rounds_completed,
        "agreement_reached": int(result.agreement_reached),
        "agreement_gini": result.agreement_gini,
        "side_payment_used": result.side_payment_used_total,
        "result_json": result.model_dump_json(),
        "created_at": result.created_at,
    })

    # save round records
    for rr in result.round_records:
        await save_round(db, result.run_id, rr)

    return result.run_id


async def upsert_run_progress(
    db: Database, run_id: str, experiment_id: str,
    condition_code: str, run_index: int, rounds_done: int, status: str = "running",
) -> None:
    """Insert or update a lightweight progress record for live monitoring."""
    await db.execute(
        """INSERT INTO runs (id, experiment_id, condition_code, run_index, status,
           rounds_completed, agreement_reached, result_json, created_at)
           VALUES (?, ?, ?, ?, ?, ?, 0, '{}', datetime('now'))
           ON CONFLICT(id) DO UPDATE SET
           rounds_completed=excluded.rounds_completed, status=excluded.status""",
        (run_id, experiment_id, condition_code, run_index, status, rounds_done),
    )
    await db._conn.commit()


async def get_run(db: Database, run_id: str) -> dict | None:
    return await db.fetch_one("SELECT * FROM runs WHERE id = ?", (run_id,))


async def list_runs(db: Database, experiment_id: str, condition_code: str | None = None) -> list[dict]:
    if condition_code:
        return await db.fetch_all(
            "SELECT * FROM runs WHERE experiment_id = ? AND condition_code = ? ORDER BY run_index",
            (experiment_id, condition_code),
        )
    return await db.fetch_all(
        "SELECT * FROM runs WHERE experiment_id = ? ORDER BY condition_code, run_index",
        (experiment_id,),
    )


async def save_round(db: Database, run_id: str, record: RoundRecord) -> str:
    from uuid import uuid4

    rid = str(uuid4())
    await db.insert("rounds", {
        "id": rid,
        "run_id": run_id,
        "round_number": record.round_number,
        "proposal_json": record.mediator_proposal.model_dump_json(),
        "strong_response_json": record.strong_response.model_dump_json(),
        "weak_response_json": record.weak_response.model_dump_json(),
        "domestic_scores_json": json.dumps({
            "strong": record.domestic_strong_score.model_dump(),
            "weak": record.domestic_weak_score.model_dump(),
        }),
        "agreement_reached": int(record.agreement_reached),
        "created_at": datetime.now().isoformat(),
    })
    return rid


async def get_run_rounds(db: Database, run_id: str) -> list[dict]:
    return await db.fetch_all(
        "SELECT * FROM rounds WHERE run_id = ? ORDER BY round_number",
        (run_id,),
    )


async def save_evaluation(db: Database, experiment_id: str, report: EvaluationReport) -> str:
    from uuid import uuid4

    eid = str(uuid4())
    await db.insert("evaluations", {
        "id": eid,
        "experiment_id": experiment_id,
        "batch_start": report.batch_start,
        "batch_end": report.batch_end,
        "condition_code": report.condition_code,
        "dimensions_json": json.dumps([d.model_dump() for d in report.dimensions]),
        "overall_score": report.overall_score,
        "adjustments_json": json.dumps(report.parameter_adjustments),
        "created_at": report.created_at,
    })
    return eid


async def list_evaluations(db: Database, experiment_id: str) -> list[dict]:
    return await db.fetch_all(
        "SELECT * FROM evaluations WHERE experiment_id = ? ORDER BY created_at DESC",
        (experiment_id,),
    )


async def save_analysis_result(db: Database, experiment_id: str, result: HypothesisResult) -> str:
    from uuid import uuid4
    from math import isnan

    aid = str(uuid4())
    await db.insert("analysis_results", {
        "id": aid,
        "experiment_id": experiment_id,
        "hypothesis": result.hypothesis,
        "test_name": result.test_name,
        "test_statistic": 0.0 if isnan(result.test_statistic) else result.test_statistic,
        "p_value": 1.0 if isnan(result.p_value) else result.p_value,
        "effect_size": 0.0 if isnan(result.effect_size) else result.effect_size,
        "confidence_interval_json": json.dumps(result.confidence_interval),
        "significant": int(result.significant),
        "result_json": result.model_dump_json(),
        "created_at": datetime.now().isoformat(),
    })
    return aid


async def list_analysis_results(db: Database, experiment_id: str) -> list[dict]:
    return await db.fetch_all(
        "SELECT * FROM analysis_results WHERE experiment_id = ? ORDER BY hypothesis",
        (experiment_id,),
    )


async def get_condition_summary(db: Database, experiment_id: str) -> list[dict]:
    rows = await db.fetch_all(
        """SELECT condition_code,
                  COUNT(*) as total,
                  SUM(CASE WHEN status = 'running' THEN 1 ELSE 0 END) as running,
                  SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                  SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
                  SUM(CASE WHEN status = 'completed' AND agreement_reached = 1 THEN 1 ELSE 0 END) as agreements,
                  AVG(CASE WHEN status = 'completed' THEN agreement_gini END) as mean_gini,
                  AVG(CASE WHEN status = 'completed' THEN rounds_completed END) as mean_rounds,
                  AVG(side_payment_used) as mean_payment
           FROM runs
           WHERE experiment_id = ?
           GROUP BY condition_code
           ORDER BY condition_code""",
        (experiment_id,),
    )
    return rows

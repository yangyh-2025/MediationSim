from __future__ import annotations

import asyncio
import time
import traceback
import uuid

from backend.db.database import Database
from backend.db import queries as dbq
from backend.models.schemas import ExperimentConfigIn, RunResult
from backend.config import config
from backend.engine.negotiation import NegotiationEngine
from backend.engine.orchestrator import EvaluationOrchestrator


class ExperimentScheduler:
    """Orchestrates multi-condition experiment execution.

    - Every run (condition × run_index) is an independent parallel task.
    - Global concurrency capped by config.max_concurrent_runs.
    - Supports pause / resume / cancel for graceful interruption.
    - Triggers fast & medium iteration evaluations automatically.
    """

    def __init__(
        self,
        db: Database,
        experiment_id: str,
        exp_config: ExperimentConfigIn,
    ) -> None:
        self.db = db
        self.experiment_id = experiment_id
        self.exp_config = exp_config
        self._paused = False
        self._cancelled = False
        self._results: list[RunResult] = []
        self._orchestrator = EvaluationOrchestrator(db)

    # ------------------------------------------------------------------
    # Control
    # ------------------------------------------------------------------

    def pause(self) -> None:
        self._paused = True

    def resume(self) -> None:
        self._paused = False

    def cancel(self) -> None:
        self._cancelled = True

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def run_all(self) -> list[RunResult]:
        """Execute every condition × run_index as an independent parallel task.

        Global concurrency capped by config.max_concurrent_runs.
        """
        conditions = [
            c for c in config.conditions
            if c["code"] in self.exp_config.conditions
        ]

        # Flatten into individual run tasks
        run_specs: list[dict] = []
        for cond in conditions:
            for i in range(self.exp_config.runs_per_condition):
                run_specs.append({"condition": cond, "run_index": i})
        total_runs = len(run_specs)

        # Shared state for progress tracking & evaluation triggers
        completed_count = [0]  # list for mutable closure
        lock = asyncio.Lock()
        cond_results: dict[str, list[RunResult]] = {c["code"]: [] for c in conditions}
        # Track which conditions have been warmed already
        warmed_conditions: set = set()

        sem = asyncio.Semaphore(config.max_concurrent_runs)

        async def _run_one(spec: dict) -> RunResult:
            nonlocal warmed_conditions
            cond = spec["condition"]
            code: str = cond["code"]
            ar: float = cond["ar"]
            bias: float = cond["bias"]
            side_payment: bool = self.exp_config.side_payment_enabled
            idx: int = spec["run_index"]

            async with sem:
                if self._cancelled:
                    return RunResult(condition_code=code, run_index=idx,
                                     status="cancelled", rounds_completed=0,
                                     agreement_reached=False)

                while self._paused:
                    await asyncio.sleep(1.0)

                run_id = str(uuid.uuid4())

                # ── One-shot cache warm per condition ──
                if code not in warmed_conditions:
                    warmed_conditions.add(code)  # claim first to avoid concurrent warm
                    try:
                        warm_engine = NegotiationEngine(
                            code, ar, bias, side_payment,
                            experiment_id=self.experiment_id)
                        await warm_engine.warm_caches()
                        print(f"[Scheduler] Cache warmed for condition {code}")
                    except Exception:
                        pass

                await dbq.upsert_run_progress(
                    self.db, run_id, self.experiment_id, code, idx, 0, "running",
                )

                async def _on_round(rounds_done: int, _rid=run_id, _idx=idx) -> None:
                    await dbq.upsert_run_progress(
                        self.db, _rid, self.experiment_id, code, _idx,
                        rounds_done, "running",
                    )

                engine = NegotiationEngine(
                    code, ar, bias, side_payment,
                    experiment_id=self.experiment_id,
                    run_id=run_id,
                    on_round_complete=_on_round,
                )

                try:
                    result = await engine.run()
                except Exception as exc:
                    print(f"[Scheduler] Run {code}[{idx}] failed: {exc}")
                    traceback.print_exc()
                    result = RunResult(
                        condition_code=code, run_index=idx,
                        status="failed", rounds_completed=0,
                        agreement_reached=False,
                    )

            result.run_index = idx
            result.condition_code = code
            result.experiment_id = self.experiment_id

            await dbq.save_run_result(self.db, self.experiment_id, result)

            # ── Thread-safe progress & evaluation ──
            async with lock:
                cond_results[code].append(result)
                self._results.append(result)
                completed_count[0] += 1

                # Update experiment-level progress
                await self.db.update(
                    "experiments", "id = ?",
                    {"completed_runs": completed_count[0],
                     "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S")},
                    (self.experiment_id,),
                )

                # Fast evaluation (per-condition, every 10 runs)
                cr = cond_results[code]
                if len(cr) % config.fast_iteration_interval == 0 and len(cr) >= 10:
                    try:
                        await self._orchestrator.run_fast_evaluation(
                            self.experiment_id, code, cr[-10:]
                        )
                    except Exception:
                        print("[Scheduler] Fast evaluation failed, continuing...")
                        traceback.print_exc()

                # Medium evaluation (per-condition, every 30 runs)
                if len(cr) % config.medium_iteration_interval == 0 and len(cr) > 0:
                    try:
                        await self._orchestrator.run_medium_evaluation(
                            self.experiment_id, code, cr
                        )
                    except Exception:
                        print("[Scheduler] Medium evaluation failed, continuing...")
                        traceback.print_exc()

            return result

        tasks = [_run_one(spec) for spec in run_specs]
        all_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out exceptions (individual errors already caught inside _run_one)
        final_results: list[RunResult] = []
        for r in all_results:
            if isinstance(r, RunResult):
                final_results.append(r)
            elif isinstance(r, Exception):
                print(f"[Scheduler] Uncaught worker crash: {r}")
                traceback.print_exception(type(r), r, r.__traceback__)

        self._results = final_results

        # ── Cache metrics summary ──
        from backend.llm.client import cache_metrics
        cm = cache_metrics.summary()
        print(
            f"\n[Scheduler] Cache: {cm['total_calls']} calls, "
            f"token hit rate {cm['token_hit_rate']}%, "
            f"call hit rate {cm['call_hit_rate']}%, "
            f"estimated cost saved {cm['estimated_cost_saved_pct']}%"
        )

        # Final global evaluation (Step 8)
        if final_results and not self._cancelled:
            try:
                await self._orchestrator.run_global_evaluation(
                    self.experiment_id, final_results
                )
            except Exception:
                print("[Scheduler] Global evaluation failed, continuing...")
                traceback.print_exc()

        return final_results

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _count_completed_runs(self) -> int:
        rows = await self.db.fetch_all(
            "SELECT COUNT(*) as cnt FROM runs WHERE experiment_id = ? AND status = 'completed'",
            (self.experiment_id,),
        )
        return rows[0]["cnt"] if rows else 0

    def get_progress(self) -> dict:
        total = len(self.exp_config.conditions) * self.exp_config.runs_per_condition
        return {
            "total": total,
            "completed": len(self._results),
            "status": "paused" if self._paused else "running",
        }

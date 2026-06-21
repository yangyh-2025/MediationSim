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

    - Conditions declared in the experiment config are executed in parallel.
    - Within a condition, runs are sequential (stateful LLM agents).
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
        """Execute every condition in the experiment config.

        Conditions are parallelized up to config.max_concurrent_conditions.
        Each condition runs its simulations sequentially (cache affinity).
        """
        conditions = [
            c for c in config.conditions
            if c["code"] in self.exp_config.conditions
        ]

        sem = asyncio.Semaphore(config.max_concurrent_conditions)

        async def _run_with_limit(cond: dict) -> list[RunResult]:
            async with sem:
                return await self._run_condition(cond)

        tasks = [_run_with_limit(c) for c in conditions]
        results_per_condition = await asyncio.gather(*tasks, return_exceptions=True)

        all_results: list[RunResult] = []
        for r in results_per_condition:
            if isinstance(r, list):
                all_results.extend(r)
            elif isinstance(r, Exception):
                print(f"[Scheduler] Condition worker crashed: {r}")
                traceback.print_exception(type(r), r, r.__traceback__)

        self._results = all_results

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
        if all_results and not self._cancelled:
            try:
                await self._orchestrator.run_global_evaluation(
                    self.experiment_id, all_results
                )
            except Exception:
                print("[Scheduler] Global evaluation failed, continuing...")
                traceback.print_exc()

        return all_results

    # ------------------------------------------------------------------
    # Per-condition worker
    # ------------------------------------------------------------------

    async def _run_condition(self, condition: dict) -> list[RunResult]:
        results: list[RunResult] = []
        code: str = condition["code"]
        ar: float = condition["ar"]
        bias: float = condition["bias"]
        side_payment: bool = self.exp_config.side_payment_enabled

        # ── Cache warm for this condition (once) ──
        # First run of each condition pays the cache-miss cost once via
        # warm_caches(). All subsequent runs in this condition hit the cache.
        warm_engine = NegotiationEngine(code, ar, bias, side_payment, experiment_id=self.experiment_id)
        try:
            await warm_engine.warm_caches()
            print(f"[Scheduler] Cache warmed for condition {code}")
        except Exception:
            pass  # warming failure is non-fatal

        for i in range(self.exp_config.runs_per_condition):
            if self._cancelled:
                break

            while self._paused:
                await asyncio.sleep(1.0)

            run_id = str(uuid.uuid4())

            # ── Flush initial "running" record so monitor sees it ──
            await dbq.upsert_run_progress(
                self.db, run_id, self.experiment_id, code, i, 0, "running",
            )

            async def _on_round(rounds_done: int, _rid=run_id, _idx=i) -> None:
                await dbq.upsert_run_progress(
                    self.db, _rid, self.experiment_id, code, _idx, rounds_done, "running",
                )
                # bump completed count (DB-driven)
                await self.db.update(
                    "experiments", "id = ?",
                    {"updated_at": time.strftime("%Y-%m-%dT%H:%M:%S")},
                    (self.experiment_id,),
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
                print(f"[Scheduler] Run {code}[{i}] failed: {exc}")
                traceback.print_exc()
                result = RunResult(
                    condition_code=code,
                    run_index=i,
                    status="failed",
                    rounds_completed=0,
                    agreement_reached=False,
                )

            result.run_index = i
            result.condition_code = code
            result.experiment_id = self.experiment_id

            await dbq.save_run_result(self.db, self.experiment_id, result)
            results.append(result)

            # Update experiment progress
            completed = await self._count_completed_runs()
            await self.db.update(
                "experiments",
                "id = ?",
                {"completed_runs": completed, "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S")},
                (self.experiment_id,),
            )

            # Fast iteration evaluation (every 10 runs)
            if (i + 1) % config.fast_iteration_interval == 0 and len(results) >= 10:
                try:
                    await self._orchestrator.run_fast_evaluation(
                        self.experiment_id, code, results[-10:]
                    )
                except Exception:
                    print("[Scheduler] Fast evaluation failed, continuing...")
                    traceback.print_exc()

            # Medium iteration evaluation (every 30 runs)
            if (i + 1) % config.medium_iteration_interval == 0:
                try:
                    await self._orchestrator.run_medium_evaluation(
                        self.experiment_id, code, results
                    )
                except Exception:
                    print("[Scheduler] Medium evaluation failed, continuing...")
                    traceback.print_exc()

        return results

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

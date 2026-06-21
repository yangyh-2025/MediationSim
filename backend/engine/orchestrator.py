from __future__ import annotations

from backend.db.database import Database
from backend.db import queries as dbq
from backend.models.schemas import EvaluationReport, RunResult
from backend.llm.client import LLMClient
from backend.agents.evaluator import Evaluator


class EvaluationOrchestrator:
    """Manages iteration-level and global evaluation passes.

    - fast  (every 10 runs):  lightweight batch diagnostics
    - medium (every 30 runs):  deeper per-condition analysis
    - global (after all runs): cross-condition comparison
    """

    def __init__(self, db: Database) -> None:
        self.db = db
        llm = LLMClient()
        self.evaluator = Evaluator(llm)
        self.iteration_history: list[dict] = []

    # ------------------------------------------------------------------
    # Fast iteration
    # ------------------------------------------------------------------

    async def run_fast_evaluation(
        self,
        experiment_id: str,
        condition_code: str,
        batch_results: list[RunResult],
    ) -> EvaluationReport:
        report = await self.evaluator.evaluate_batch(
            batch_results, iteration_type="fast"
        )
        report.batch_start = (
            batch_results[0].run_index if batch_results else 0
        )
        report.batch_end = (
            batch_results[-1].run_index if batch_results else 0
        )
        report.condition_code = condition_code

        await dbq.save_evaluation(self.db, experiment_id, report)
        self.iteration_history.append(
            {"type": "fast", "condition": condition_code, "report": report}
        )
        return report

    # ------------------------------------------------------------------
    # Medium iteration
    # ------------------------------------------------------------------

    async def run_medium_evaluation(
        self,
        experiment_id: str,
        condition_code: str,
        all_results: list[RunResult],
    ) -> EvaluationReport:
        report = await self.evaluator.evaluate_batch(
            all_results, iteration_type="medium"
        )
        report.condition_code = condition_code

        await dbq.save_evaluation(self.db, experiment_id, report)
        self.iteration_history.append(
            {"type": "medium", "condition": condition_code, "report": report}
        )
        return report

    # ------------------------------------------------------------------
    # Global evaluation (post-experiment, Step 8)
    # ------------------------------------------------------------------

    async def run_global_evaluation(
        self,
        experiment_id: str,
        all_results: list[RunResult],
    ) -> EvaluationReport:
        report = await self.evaluator.evaluate_batch(
            all_results, iteration_type="global"
        )

        await dbq.save_evaluation(self.db, experiment_id, report)
        self.iteration_history.append(
            {"type": "global", "report": report}
        )
        return report

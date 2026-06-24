from __future__ import annotations

import json

from backend.agents.base import BaseAgent
from backend.llm.client import LLMClient
from backend.models.schemas import (
    EvaluationReport,
    EvaluationDimension,
    RunResult,
    NegotiationContext,
)


class Evaluator(BaseAgent):
    """Independent research evaluator assessing simulation quality across six dimensions."""

    def __init__(self, llm: LLMClient) -> None:
        prompt = self._load_prompt("evaluator.txt")
        super().__init__("Evaluator", "evaluator", prompt, llm, EvaluationReport)

    async def act(self, context: NegotiationContext) -> EvaluationReport:
        """Evaluator does not participate in the negotiation loop directly.
        Use evaluate_batch() for batch evaluation instead.
        """
        raise NotImplementedError(
            "Evaluator.act() is not used in the negotiation loop. "
            "Use Evaluator.evaluate_batch() for batch evaluation."
        )

    @staticmethod
    def _summarize_runs(runs: list[RunResult]) -> str:
        """Build a structured summary of a batch of runs for the LLM evaluator."""
        lines: list[str] = [f"本批次共 {len(runs)} 次运行。\n"]

        for i, run in enumerate(runs):
            lines.append(f"### 运行 {i + 1}: {run.run_id[:8]}...")
            lines.append(f"- 实验条件: {run.condition_code}")
            lines.append(f"- 完成轮次: {run.rounds_completed}")
            lines.append(f"- 协议达成: {'是' if run.agreement_reached else '否'}")
            lines.append(f"- 边支付总计: {run.side_payment_used_total:.2f}")
            lines.append(f"- 运行时间: {run.total_duration_seconds:.1f}s")

            if run.final_proposal:
                lines.append(
                    f"- 最终提案: 领土划分 {run.final_proposal.territory_split}%, "
                    f"边支付 {run.final_proposal.side_payment_amount}"
                )

            if run.agreement_gini is not None:
                lines.append(f"- 协议基尼系数: {run.agreement_gini:.4f}")

            if run.round_records:
                lines.append("- 轮次详情:")
                for record in run.round_records:
                    lines.append(
                        f"  第{record.round_number}轮: "
                        f"强方={record.strong_response.action}, "
                        f"弱方={record.weak_response.action}, "
                        f"强方国内={record.domestic_strong_score.political_acceptability:.2f}, "
                        f"弱方国内={record.domestic_weak_score.political_acceptability:.2f}"
                    )

        return "\n".join(lines)

    @staticmethod
    def _compute_batch_stats(runs: list[RunResult]) -> str:
        """Compute descriptive statistics for the batch."""
        if not runs:
            return "（无数据）"

        n = len(runs)
        agreement_count = sum(1 for r in runs if r.agreement_reached)
        avg_rounds = sum(r.rounds_completed for r in runs) / n
        avg_payment = sum(r.side_payment_used_total for r in runs) / n

        conditions: dict[str, int] = {}
        for r in runs:
            conditions[r.condition_code] = conditions.get(r.condition_code, 0) + 1

        stats = (
            f"批次统计:\n"
            f"- 总运行数: {n}\n"
            f"- 协议达成率: {agreement_count}/{n} ({agreement_count / n * 100:.1f}%)\n"
            f"- 平均完成轮次: {avg_rounds:.2f}\n"
            f"- 平均边支付: {avg_payment:.2f}\n"
            f"- 条件分布: {json.dumps(conditions, ensure_ascii=False)}\n"
        )

        # Compute condition-specific agreement rates
        condition_agreements: dict[str, list[bool]] = {}
        for r in runs:
            condition_agreements.setdefault(r.condition_code, []).append(r.agreement_reached)
        for code, agreements in condition_agreements.items():
            rate = sum(agreements) / len(agreements)
            stats += f"- {code} 协议率: {rate * 100:.1f}%\n"

        return stats

    async def evaluate_batch(
        self, runs: list[RunResult], iteration_type: str = "fast"
    ) -> EvaluationReport:
        """Evaluate a batch of simulation runs across 6 quality dimensions.

        Args:
            runs: List of RunResult objects from the current batch.
            iteration_type: "fast" (every 10), "medium" (every 30), or "final".
        """
        if not runs:
            return EvaluationReport(
                batch_start=0,
                batch_end=0,
                condition_code="",
                dimensions=[
                    EvaluationDimension(
                        name="无数据",
                        score=0.0,
                        issues=["批次中没有运行数据"],
                        suggestions=["请确保模拟引擎正在产生运行结果"],
                    )
                ],
                overall_score=0.0,
            )

        batch_summary = self._summarize_runs(runs)
        batch_stats = self._compute_batch_stats(runs)

        condition_code = runs[0].condition_code if runs else ""

        iteration_guidance = {
            "fast": (
            "这是快速迭代评估（每10次运行）。"
            "重点关注明显的操作性问题、提案格式是否正确、行为是否符合基本预期。"
        ),
            "medium": "这是中期迭代评估（每30次运行）。除基本检查外，还需评估策略多样性、行为合理性的趋势、以及条件间的初步差异。",
            "final": "这是终期评估。请进行全面深度的六维评估，包括跨条件的比较分析和参数调整建议。",
        }
        guidance = iteration_guidance.get(iteration_type, iteration_guidance["fast"])

        user_message = (
            f"## 评估批次信息\n\n"
            f"- 批次规模: {len(runs)} 次运行\n"
            f"- 首要条件: {condition_code}\n"
            f"- 评估类型: {iteration_type}\n"
            f"- 评估指导: {guidance}\n\n"
            f"## 批次统计\n\n{batch_stats}\n\n"
            f"## 运行详情\n\n{batch_summary}\n\n"
            f"## 评估要求\n\n"
            f"请按照evaluator系统提示中的六维框架，对以上批次数据进行全面评估。\n"
            f"输出 EvaluationReport，其中 dimensions 必须恰好包含6个 EvaluationDimension，"
            f"顺序为：外部效度、内部一致性、行为合理性、策略多样性、随机充分性、操作检查。\n"
            f"每个维度评分为0-10，需列出至少1个问题和至少1条改进建议。"
        )

        # Build a synthetic context for the evaluator (not a real negotiation)
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_message},
        ]

        result = await self.llm.chat(messages, response_schema=EvaluationReport)
        assert isinstance(result, EvaluationReport)

        # Populate batch metadata
        result.batch_start = 0
        result.batch_end = len(runs) - 1
        if not result.condition_code:
            result.condition_code = condition_code

        return result

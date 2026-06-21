from __future__ import annotations

from backend.agents.base import BaseAgent
from backend.llm.client import LLMClient
from backend.models.schemas import NegotiationContext, Proposal


class Mediator(BaseAgent):
    """Biased mediator agent with optional side payment capability.

    The mediator's bias determines its strategy:
    - bias > 0.3: pro-strong, with side payment capability
    - bias < -0.3: pro-weak, no side payments
    - otherwise: neutral, no side payments
    """

    def __init__(
        self,
        llm: LLMClient,
        bias: float,
        side_payment_budget: float,
        side_payment_enabled: bool = True,
    ) -> None:
        if bias > 0.3:
            filename = "mediator_pro_strong.txt"
        elif bias < -0.3:
            filename = "mediator_pro_weak.txt"
        else:
            filename = "mediator_neutral.txt"

        prompt = self._load_prompt(
            filename, bias=f"{bias:.1f}", budget=f"{side_payment_budget:.2f}"
        )
        super().__init__("Mediator", "mediator", prompt, llm)
        self.bias = bias
        self.side_payment_budget = side_payment_budget
        # Side payments only for pro-strong mediators
        self.side_payment_enabled = side_payment_enabled and (bias > 0.3)

    def _build_side_payment_guidance(self, context: NegotiationContext) -> str:
        """Build the 3-layer side payment decision guidance."""
        if not self.side_payment_enabled:
            return "边支付功能未启用。请仅通过提案条款来推进谈判。"

        remaining = self.side_payment_budget - context.side_payment_used
        return (
            f"## 边支付决策（三层逻辑）\n\n"
            f"可用的边支付预算: {remaining:.2f}（总预算: {self.side_payment_budget:.2f}）\n\n"
            f"在决定边支付金额和接收方时，请严格按照以下三层逻辑逐步分析：\n\n"
            f"**第一层：必要性检查（Necessity）**\n"
            f"- 强方当前效用为 {context.strong_current_utility:.2f}\n"
            f"- 如果该效用低于强方的保留阈值（通常为初始效用的60%，即 {context.strong_initial_utility * 0.6:.2f}），"
            f"则强方很可能拒绝当前提案，边支付可能成为必要的激励手段\n"
            f"- 如果强方效用高于阈值，边支付可能不需要\n\n"
            f"**第二层：效用缺口分析（Utility Gap）**\n"
            f"- 计算强方当前效用与保留阈值之间的差距\n"
            f"- 弱方当前效用为 {context.weak_current_utility:.2f}\n"
            f"- 判断边支付是否能够有效弥合这一差距：支付给弱方可以提高其接受度，支付给强方可以补偿其让步损失\n"
            f"- 边支付金额应该与效用缺口成正比\n\n"
            f"**第三层：可负担性检查（Affordability）**\n"
            f"- 提议的边支付金额必须在剩余预算 {remaining:.2f} 之内\n"
            f"- 不要耗尽所有预算，为后续轮次留有余地（建议单轮不超过剩余预算的50%）\n"
            f"- 如果预算不足，考虑调整提案条款而非增加边支付"
        )

    async def act(self, context: NegotiationContext) -> Proposal:
        """Generate a mediation proposal with optional side payment."""
        if context.history:
            latest_record = context.history[-1]
            history_summary = (
                f"上一轮提案回顾：\n"
                f"- 你的提案: 领土划分 {latest_record.mediator_proposal.territory_split}%\n"
                f"- 强方回应: {latest_record.strong_response.action}\n"
                f"- 弱方回应: {latest_record.weak_response.action}\n"
                f"- 协议达成: {'是' if latest_record.agreement_reached else '否'}\n\n"
                f"根据双方的回应调整你的新一轮提案。如果一方或双方拒绝了上一轮提案，"
                f"请分析原因并在新提案中做出调整。"
            )
        else:
            history_summary = "这是第一轮谈判，请根据你的偏见和策略提出初始提案。"

        side_payment_guidance = self._build_side_payment_guidance(context)

        user_message = (
            f"作为调停者，请提出本轮谈判的正式提案。\n\n"
            f"{history_summary}\n\n"
            f"{side_payment_guidance}\n\n"
            f"## 提案要求\n\n"
            f"请生成一个 Proposal，包含以下要素：\n"
            f"1. **territory_split**: 领土划分方案（强方占比0-100）。"
            f"你的偏见为 {self.bias:.1f}，提案方向应与此一致\n"
            f"2. **resource_allocation**: 资源分配方案，以字典形式给出"
            f"（如 {{\"economic\": 0.6, \"military\": 0.7}}）\n"
            f"3. **side_payment_amount**: 根据三层逻辑确定的边支付金额（无则为0）\n"
            f"4. **side_payment_recipient**: 边支付接收方（strong/weak/none）\n"
            f"5. **justification**: 详尽的提案理由，解释为什么此提案公平合理、为什么双方应该接受\n"
            f"6. **round_number**: 当前轮次 {context.round_number}\n"
            f"7. **mediator_bias**: {self.bias}\n\n"
            f"{'⚠️ 这是最后一轮谈判！请提出一个双方都能接受的最优方案。' if context.is_final_round else ''}"
        )

        messages = self._build_messages(context, user_message)
        result = await self.llm.chat(messages, response_schema=Proposal)
        assert isinstance(result, Proposal)
        return result

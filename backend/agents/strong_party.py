from __future__ import annotations

from typing import Any

from backend.agents.base import BaseAgent
from backend.llm.client import LLMClient
from backend.models.schemas import NegotiationContext, AgentResponse, Proposal


class StrongParty(BaseAgent):
    """Agent representing a militarily superior state in asymmetric negotiations."""

    def __init__(self, llm: LLMClient, ar: float) -> None:
        prompt = self._load_prompt("strong_party.txt", ar=f"{ar:.1f}")
        super().__init__("StrongParty", "strong_party", prompt, llm, AgentResponse)
        self.ar = ar

    async def act(self, context: NegotiationContext) -> AgentResponse:
        """Make a position statement or respond to a proposal."""
        if context.history:
            latest = context.history[-1]
            # Detect own previous accept (anti-oscillation)
            prev_self_accepts = [
                r for r in context.history
                if r.strong_response.action == "accept"
            ]
            osc_note = ""
            if prev_self_accepts:
                osc_note = (
                    f"\n⚠️ 注意：你在第 {prev_self_accepts[-1].round_number} 轮已接受过当时的提案。"
                    f"除非本轮的提案条款明确劣于你上次接受时的条款，否则继续维持接受立场。"
                    f"不要因为等待'更好的条件'而错失已达成的合理协议。"
                )

            user_message = (
                f"上一轮调停者提出了以下提案：\n"
                f"- 领土划分（强方占比）: {latest.mediator_proposal.territory_split}%\n"
                f"- 资源分配: {latest.mediator_proposal.resource_allocation}\n"
                f"- 边支付金额: {latest.mediator_proposal.side_payment_amount}\n"
                f"- 边支付接收方: {latest.mediator_proposal.side_payment_recipient}\n"
                f"- 调停者理由: {latest.mediator_proposal.justification}\n\n"
                f"请评估该提案。你需要决定：接受(accept)、拒绝(reject)、或提出反提案(counter_proposal)。\n"
                f"参考因素：\n"
                f"1. AR={self.ar:.1f}，议价能力强但僵局也有成本\n"
                f"2. 国内鹰派对领土损失敏感，但长期僵局也会削弱执政合法性\n"
                f"3. 当前效用: {context.strong_current_utility:.2f}（初始: {context.strong_initial_utility:.2f}，阈值: {context.strong_initial_utility * 0.3:.1f}）\n"
                f"4. 效用缓冲空间: {max(0, context.strong_current_utility - context.strong_initial_utility * 0.3):.1f}\n"
                f"5. {'⚠️ 最后一轮！不接受协议 = 至少3-5年僵局和关系恶化。不完美协议 > 长期僵局。' if context.is_final_round else ''}\n\n"
                f"## 效用变化\n"
                f"- accept: utility_change = -8 到 -18（让步有成本）\n"
                f"- reject: utility_change = 0（但无协议长期损失远超短期节省）\n"
                f"- counter_proposal: utility_change = 0 到 -5\n"
                f"{osc_note}"
            )
        else:
            user_message = (
                f"这是谈判的第一轮。请提出你的开场立场声明。\n"
                f"作为军事优势方(AR={self.ar:.1f})，你的开场立场应该：\n"
                f"1. 明确你对领土控制的要求（当前效用: {context.strong_current_utility:.2f}）\n"
                f"2. 阐述你的安全缓冲区需求\n"
                f"3. 表达你对资源保留的立场\n"
                f"4. 设定谈判的基调——你拥有实力优势，但也要为可能的妥协留出空间"
            )

        messages = self._build_messages(context, user_message)
        result = await self.llm.chat(messages, response_schema=AgentResponse)
        assert isinstance(result, AgentResponse)
        return result

    async def respond_to_proposal(
        self, context: NegotiationContext, proposal: Proposal, domestic: Any
    ) -> AgentResponse:
        """Respond to a specific proposal, incorporating domestic pressure."""
        pressure = getattr(domestic, "pressure_level", 0.0)

        pressure_note = ""
        if pressure > 0.9:
            pressure_note = (
                f"\n\n⚠️ 国内政治压力极高({pressure:.2f})。鹰派对领土让步极为敏感，"
                f"需要强有力的安全保证或战略利益补偿才能说服国内接受。"
            )
        elif pressure > 0.7:
            pressure_note = (
                f"\n\n国内存在较高政治压力({pressure:.2f})，但长期僵局同样消耗执政资源。"
                f"如果提案在可接受范围内（领土相对有利+有边支付/安全补偿），可慎重考虑接受。"
            )

        final_note = ""
        if context.is_final_round:
            final_note = (
                f"\n\n🚨 最后一轮警告：这是达成协议的最后机会。"
                f"拒绝 = 至少3-5年僵局 + 国际孤立 + 经济持续失血——这些代价远超一次性的让步。"
                f"如果你曾在之前轮次接受过类似条款，没有任何理由现在拒绝。"
                f"不完美协议的价值 > 长期僵局的累积损失。"
            )

        # Anti-oscillation: if self accepted in any prior round, signal strongly
        osc_note = ""
        for rec in reversed(context.history):
            if rec.strong_response.action == "accept":
                osc_note = (
                    f"\n\n⚠️ 你在第{rec.round_number}轮已接受过当时的提案。"
                    f"本提案的条款是否明显劣于那次？如果不是，你应该维持接受以避免谈判失败。"
                )
                break

        user_message = (
            f"调停者提出了以下提案，你需要做出回应：\n"
            f"- 领土划分（强方占比）: {proposal.territory_split}%\n"
            f"- 资源分配: {proposal.resource_allocation}\n"
            f"- 边支付金额: {proposal.side_payment_amount}\n"
            f"- 边支付接收方: {proposal.side_payment_recipient}\n"
            f"- 调停者理由: {proposal.justification}\n"
            f"- 你的当前效用: {context.strong_current_utility:.2f}\n"
            f"- 国内政治接受度: {getattr(domestic, 'political_acceptability', 0.0):.2f}"
            f"{pressure_note}"
            f"{final_note}"
            f"{osc_note}"
        )

        messages = self._build_messages(context, user_message)
        result = await self.llm.chat(messages, response_schema=AgentResponse)
        assert isinstance(result, AgentResponse)
        return result

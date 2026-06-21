from __future__ import annotations

from typing import Any

from backend.agents.base import BaseAgent
from backend.llm.client import LLMClient
from backend.models.schemas import NegotiationContext, AgentResponse, Proposal


class StrongParty(BaseAgent):
    """Agent representing a militarily superior state in asymmetric negotiations."""

    def __init__(self, llm: LLMClient, ar: float) -> None:
        prompt = self._load_prompt("strong_party.txt", ar=f"{ar:.1f}")
        super().__init__("StrongParty", "strong_party", prompt, llm)
        self.ar = ar

    async def act(self, context: NegotiationContext) -> AgentResponse:
        """Make a position statement or respond to a proposal."""
        if context.history:
            latest = context.history[-1]
            user_message = (
                f"上一轮调停者提出了以下提案：\n"
                f"- 领土划分（强方占比）: {latest.mediator_proposal.territory_split}%\n"
                f"- 资源分配: {latest.mediator_proposal.resource_allocation}\n"
                f"- 边支付金额: {latest.mediator_proposal.side_payment_amount}\n"
                f"- 边支付接收方: {latest.mediator_proposal.side_payment_recipient}\n"
                f"- 调停者理由: {latest.mediator_proposal.justification}\n\n"
                f"请评估该提案是否符合你的核心利益。你需要决定：接受(accept)、拒绝(reject)、或提出反提案(counter_proposal)。\n"
                f"在做出决定时，请考虑以下因素：\n"
                f"1. 你的军事实力优势(AR={self.ar:.1f})赋予你更大的议价能力\n"
                f"2. 国内的鹰派议会对领土损失高度敏感\n"
                f"3. 当前的效用水平: {context.strong_current_utility:.2f}（初始: {context.strong_initial_utility:.2f}）\n"
                f"4. 如果这是最后一轮谈判，失败的代价是什么\n\n"
                f"## 效用变化指导\n"
                f"- 接受(accept)：utility_change = -5 到 -15（接受意味着一定的让步损失）\n"
                f"- 拒绝(reject)：utility_change = 0（维持现状，但无协议意味着至少3-5年僵局）\n"
                f"- 反提案(counter_proposal)：utility_change = 0 到 -5（你希望对方让步）\n"
                f"- 你的保留效用阈值是初始效用的30%（即{context.strong_initial_utility * 0.3:.1f}）——当前效用为{context.strong_current_utility:.2f}，距阈值还有{max(0, context.strong_current_utility - context.strong_initial_utility * 0.3):.1f}的缓冲空间\n"
                f"- {'⚠️ 这是最后一轮——无协议的长期代价可能远远超过一次性的让步损失' if context.is_final_round else ''}"
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
        if pressure > 0.7:
            pressure_note = (
                f"\n\n⚠️ 重要警告：国内政治压力极高({pressure:.2f})。"
                f"鹰派议会对任何领土让步都非常敏感。"
                f"如果你接受此提案，可能面临国内政治危机。请优先考虑拒绝或要求更有利的条件。"
            )
        elif pressure > 0.4:
            pressure_note = (
                f"\n\n注意：国内存在一定的政治压力({pressure:.2f})。"
                f"在做出让步时需要提供充分的安全保障或战略利益作为理由。"
            )

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
        )

        messages = self._build_messages(context, user_message)
        result = await self.llm.chat(messages, response_schema=AgentResponse)
        assert isinstance(result, AgentResponse)
        return result

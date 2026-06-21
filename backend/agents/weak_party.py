from __future__ import annotations

from typing import Any

from backend.agents.base import BaseAgent
from backend.llm.client import LLMClient
from backend.models.schemas import NegotiationContext, AgentResponse, Proposal


class WeakParty(BaseAgent):
    """Agent representing a militarily weaker state seeking territorial recovery."""

    def __init__(self, llm: LLMClient, ar: float) -> None:
        prompt = self._load_prompt("weak_party.txt", ar=f"{ar:.1f}")
        super().__init__("WeakParty", "weak_party", prompt, llm)
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
                f"请评估该提案。你需要决定：接受(accept)、拒绝(reject)、或提出反提案(counter_proposal)。\n"
                f"在做出决定时，请考虑以下因素：\n"
                f"1. 你的核心目标是收复领土和恢复主权(AR={self.ar:.1f}，你处于劣势)\n"
                f"2. 国际法和联合国决议支持你的领土主张\n"
                f"3. 国内公众对不公平条款高度敏感——不平等协议可能引发政治危机\n"
                f"4. 当前的效用水平: {context.weak_current_utility:.2f}（初始: {context.weak_initial_utility:.2f}）\n"
                f"5. 大额边支付（>1.0 单位）可以作为分阶段收复领土的过渡期补偿——这不等于放弃主权\n\n"
                f"## 效用变化指导\n"
                f"- 接受(accept)：utility_change = -5 到 -15（接受意味着一定的让步损失）\n"
                f"- 拒绝(reject)：utility_change = 0（维持现状，但无协议意味着至少3-5年僵局，现状将进一步固化）\n"
                f"- 反提案(counter_proposal)：utility_change = 0 到 -5（你希望对方让步）\n"
                f"- 你的保留效用阈值是初始效用的30%（即{context.weak_initial_utility * 0.3:.1f}）——当前效用为{context.weak_current_utility:.2f}，距阈值还有{max(0, context.weak_current_utility - context.weak_initial_utility * 0.3):.1f}的缓冲空间\n"
                f"- {'⚠️ 这是最后一轮——拒绝可能意味着至少3-5年维持更糟糕的现状' if context.is_final_round else ''}"
            )
        else:
            user_message = (
                f"这是谈判的第一轮。请提出你的开场立场声明。\n"
                f"作为弱势方(AR={self.ar:.1f})，你的开场立场应该：\n"
                f"1. 援引国际法和联合国决议，明确你对领土主权的合法主张\n"
                f"2. 强调公平正义原则和自决权\n"
                f"3. 表达你对和平解决争端的承诺\n"
                f"4. 设定谈判的道德和法律框架\n"
                f"5. 你的当前效用: {context.weak_current_utility:.2f}"
            )

        messages = self._build_messages(context, user_message)
        result = await self.llm.chat(messages, response_schema=AgentResponse)
        assert isinstance(result, AgentResponse)
        return result

    async def respond_to_proposal(
        self, context: NegotiationContext, proposal: Proposal, domestic: Any
    ) -> AgentResponse:
        """Respond to a specific proposal, incorporating domestic pressure.

        When Gini coefficient exceeds 0.65, the rejection tendency increases
        due to elevated domestic political crisis risk.
        """
        pressure = getattr(domestic, "pressure_level", 0.0)
        acceptability = getattr(domestic, "political_acceptability", 0.0)

        # Gini-based crisis risk: >0.65 raises rejection tendency
        gini_note = ""
        if hasattr(domestic, "gini") and domestic.gini > 0.65:
            gini_note = (
                f"\n\n⚠️ 关键警告：国内基尼系数为 {domestic.gini:.2f}，已超过0.65的政治危机阈值。"
                f"持续的不平等加上不利的谈判条件可能引发严重的国内政治动荡。"
                f"在面对不公平提案时，你需要展现更强的抵抗姿态以维护执政合法性。"
            )

        pressure_note = ""
        if pressure > 0.7:
            pressure_note = (
                f"\n\n⚠️ 重要警告：国内政治压力极高({pressure:.2f})。"
                f"公众高度关注谈判结果，任何被视为'投降'的协议都将引发强烈反弹。"
                f"请优先考虑维护主权和民族尊严，必要时宁可拖延谈判也不能接受屈辱条件。"
            )
        elif pressure > 0.4:
            pressure_note = (
                f"\n\n注意：国内存在一定的政治压力({pressure:.2f})。"
                f"公众期待谈判能够取得实质性进展，但不会接受核心利益的重大让步。"
            )

        user_message = (
            f"调停者提出了以下提案，你需要做出回应：\n"
            f"- 领土划分（强方占比）: {proposal.territory_split}%\n"
            f"- 资源分配: {proposal.resource_allocation}\n"
            f"- 边支付金额: {proposal.side_payment_amount}\n"
            f"- 边支付接收方: {proposal.side_payment_recipient}\n"
            f"- 调停者理由: {proposal.justification}\n"
            f"- 你的当前效用: {context.weak_current_utility:.2f}\n"
            f"- 国内政治接受度: {acceptability:.2f}"
            f"{gini_note}"
            f"{pressure_note}"
        )

        messages = self._build_messages(context, user_message)
        result = await self.llm.chat(messages, response_schema=AgentResponse)
        assert isinstance(result, AgentResponse)
        return result

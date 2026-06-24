from __future__ import annotations

from typing import Any

from backend.agents.base import BaseAgent
from backend.llm.client import LLMClient
from backend.models.schemas import NegotiationContext, AgentResponse, Proposal


class WeakParty(BaseAgent):
    """Agent representing a militarily weaker state seeking territorial recovery."""

    def __init__(self, llm: LLMClient, ar: float) -> None:
        prompt = self._load_prompt("weak_party.txt", ar=f"{ar:.1f}")
        super().__init__("WeakParty", "weak_party", prompt, llm, AgentResponse)
        self.ar = ar

    async def act(self, context: NegotiationContext) -> AgentResponse:
        """Make a position statement or respond to a proposal."""
        if context.history:
            latest = context.history[-1]
            prev_self_accepts = [
                r for r in context.history
                if r.weak_response.action == "accept"
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
                f"1. AR={self.ar:.1f}，你处于劣势但国际法支持你\n"
                f"2. 国内公众对不平等条款高度敏感——但长期僵局对国力损耗更大\n"
                f"3. 当前效用: {context.weak_current_utility:.2f}（初始: {context.weak_initial_utility:.2f}，阈值: {context.weak_initial_utility * 0.3:.1f}）\n"
                f"4. 效用缓冲空间: {max(0, context.weak_current_utility - context.weak_initial_utility * 0.3):.1f}\n"
                f"5. 大额边支付(>1.0单位)可作为分阶段收复的过渡期补偿\n"
                f"6. {'⚠️ 最后一轮！拒绝 = 至少3-5年更糟的现状。启动收复进程的不完美协议 > 永远等待。但如果提案包含实质性领土收复或大额边支付(>1.0)，接受优于继续僵持。' if context.is_final_round else ''}\n\n"
                f"## 效用变化\n"
                f"- accept: utility_change = -8 到 -18（让步有成本）\n"
                f"- reject: utility_change = 0（但无协议长期损失远超短期节省）\n"
                f"- counter_proposal: utility_change = 0 到 -5\n"
                f"{osc_note}"
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
        if pressure > 0.9:
            pressure_note = (
                f"\n\n⚠️ 国内政治压力极高({pressure:.2f})。公众拒绝任何'投降'协议，"
                f"必须确保协议包含实质性的领土收复承诺或国际监督保障。"
            )
        elif pressure > 0.7:
            pressure_note = (
                f"\n\n国内存在较高政治压力({pressure:.2f})，但长期僵局会固化既成事实。"
                f"务实的分阶段方案 + 边支付过渡补偿可以是可接受的出路。"
            )

        final_note = ""
        if context.is_final_round:
            final_note = (
                f"\n\n🚨 最后一轮警告：这是达成协议的最后机会。"
                f"拒绝 = 至少3-5年更糟的现状 + 既成事实进一步固化。"
                f"如果你曾在之前轮次接受过类似条款，没有任何理由现在拒绝。"
                f"启动收复进程的不完美协议 > 完美但不现实的方案。"
            )

        osc_note = ""
        for rec in reversed(context.history):
            if rec.weak_response.action == "accept":
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
            f"- 你的当前效用: {context.weak_current_utility:.2f}\n"
            f"- 国内政治接受度: {acceptability:.2f}"
            f"{gini_note}"
            f"{pressure_note}"
            f"{final_note}"
            f"{osc_note}"
        )

        messages = self._build_messages(context, user_message)
        result = await self.llm.chat(messages, response_schema=AgentResponse)
        assert isinstance(result, AgentResponse)
        return result

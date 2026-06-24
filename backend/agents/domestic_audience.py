from __future__ import annotations

from backend.agents.base import BaseAgent
from backend.llm.client import LLMClient
from backend.models.schemas import NegotiationContext, DomesticScore, Proposal


class DomesticAudience(BaseAgent):
    """Evaluates the political acceptability of proposals from the domestic audience perspective."""

    def __init__(self, llm: LLMClient) -> None:
        prompt = self._load_prompt("domestic_audience.txt")
        super().__init__("DomesticAudience", "domestic_audience", prompt, llm, DomesticScore)

    async def act(
        self,
        context: NegotiationContext,
        proposal: Proposal,
        audience_for: str,
    ) -> DomesticScore:
        """Evaluate a proposal's political acceptability for the given party.

        Args:
            context: Current negotiation context.
            proposal: The proposal to evaluate.
            audience_for: Either 'strong' or 'weak' — which party's domestic audience to simulate.
        """
        if audience_for not in ("strong", "weak"):
            raise ValueError(f"audience_for must be 'strong' or 'weak', got '{audience_for}'")

        party_name = "强方（军事优势国）" if audience_for == "strong" else "弱方（领土主张国）"
        current_utility = (
            context.strong_current_utility if audience_for == "strong"
            else context.weak_current_utility
        )
        initial_utility = (
            context.strong_initial_utility if audience_for == "strong"
            else context.weak_initial_utility
        )

        user_message = (
            f"## 评估任务\n\n"
            f"你代表**{party_name}**的国内政治受众（议会、媒体、公众），"
            f"请评估以下调停提案在该国国内的政治可接受度。\n\n"
            f"### 调停者提案\n"
            f"- 领土划分（强方占比）: {proposal.territory_split}%\n"
            f"- 资源分配: {proposal.resource_allocation}\n"
            f"- 边支付金额: {proposal.side_payment_amount}\n"
            f"- 边支付接收方: {proposal.side_payment_recipient}\n"
            f"- 调停者理由: {proposal.justification}\n\n"
            f"### 背景信息\n"
            f"- 当前效用: {current_utility:.2f}（初始: {initial_utility:.2f}）\n"
            f"- 不对称比率(AR): {context.ar:.2f}\n"
            f"- 调停者偏见: {context.mediator_bias:.2f}\n"
            f"- 当前轮次: {context.round_number}\n"
            f"- 是否最后一轮: {'是' if context.is_final_round else '否'}\n\n"
            f"### 评估指导\n\n"
            f"请输出 DomesticScore，包含：\n"
            f"1. **political_acceptability** (0-1): 国内政治可接受度\n"
            f"   - 综合考虑领土得失、经济成本收益、民族尊严、安全保障\n"
            f"   - 使用全量程：有利提案 0.55-0.95，中等提案 0.25-0.70，不利提案 0.05-0.35\n"
            f"   - 边支付流入本国应显著提高可接受度(+0.15~0.30)\n"
            f"2. **pressure_level** (0-1): 对谈判代表的国内政治压力\n"
            f"   - 大致映射为 1.0 - acceptability，但允许±0.2的偏差\n"
            f"   - 大部分轮次应在 0.25-0.75 之间，仅极端不利时 >0.85\n"
            f"3. **key_concerns**: 国内各方最关心的2-5个关键问题列表\n"
            f"4. **agent_type**: 设为 \"{audience_for}\"\n\n"
            f"⚠️ 注意：{'强方国内对领土损失高度敏感，但边支付补偿和最后轮次的紧迫感应被充分考虑' if audience_for == 'strong' else '弱方国内对不平等条款高度敏感，但边支付补偿和分阶段方案的可行性应被充分考虑'}\n\n"
            f"【格式警告】你必须严格输出 DomesticScore 对象，包含且仅包含以下字段：\n"
            f'{{"agent_type": "{audience_for}", "political_acceptability": <0到1的浮点数>, "pressure_level": <0到1的浮点数>, "key_concerns": [<2到5个字符串>]}}\n'
            f"禁止输出 action、counter_proposal、reasoning、utility_change（那是 AgentResponse 的字段）。\n"
            f"禁止输出 territory_split、resource_allocation、side_payment_amount、justification（那是 Proposal 的字段）。\n"
            f"你唯一的任务是评估政治可接受度——仅此而已。"
        )

        messages = self._build_messages(context, user_message)
        result = await self.llm.chat(messages, response_schema=DomesticScore)
        assert isinstance(result, DomesticScore)
        return result

from __future__ import annotations

from backend.agents.base import BaseAgent
from backend.llm.client import LLMClient
from backend.models.schemas import NegotiationContext, Proposal
from backend.config import config


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
        super().__init__("Mediator", "mediator", prompt, llm, Proposal)
        self.bias = bias
        self.side_payment_budget = side_payment_budget
        # Side payments only for pro-strong mediators
        self.side_payment_enabled = side_payment_enabled and (bias > 0.3)

    def _build_side_payment_guidance(self, context: NegotiationContext) -> str:
        """Build the 3-layer side payment decision guidance."""
        if not self.side_payment_enabled:
            return "边支付功能未启用。请仅通过提案条款来推进谈判。"

        remaining = self.side_payment_budget - context.side_payment_used
        total = self.side_payment_budget
        r = context.round_number
        if r <= 4:
            max_this_round = total * 0.08
            pace_note = f"本轮最高: {max_this_round:.2f}（早期，节省预算——你还有{8-r}轮要谈）"
        elif r <= 6:
            max_this_round = total * 0.12
            pace_note = f"本轮最高: {max_this_round:.2f}（中期，适度增加——为最后两轮保留弹药）"
        elif r == 7:
            max_this_round = min(remaining * 0.5, total * 0.25)
            pace_note = f"本轮最高: {max_this_round:.2f}（倒数第2轮，用一半剩余——必须为R8预留至少{remaining*0.5:.1f}）"
        else:
            max_this_round = remaining
            pace_note = f"本轮最高: {max_this_round:.2f}（最后一轮！倾尽全力，全部花光——没有下次了）"
        return (
            f"## 边支付决策（三层逻辑）\n\n"
            f"总预算: {self.side_payment_budget:.2f}，已使用: {context.side_payment_used:.2f}，剩余: {remaining:.2f}\n\n"
            f"在决定边支付金额和接收方时，请严格按照以下三层逻辑逐步分析：\n\n"
            f"**第一层：必要性检查（Necessity）**\n"
            f"- 强方当前效用为 {context.strong_current_utility:.2f}\n"
            f"- 弱方当前效用为 {context.weak_current_utility:.2f}\n"
            f"- 如果一方或双方的效用接近或低于保留阈值（30%初始效用），边支付可能成为必要的激励手段\n\n"
            f"**第二层：效用缺口分析（Utility Gap）**\n"
            f"- 计算双方的效用与保留阈值之间的差距\n"
            f"- 判断边支付是否能够有效弥合这一差距：支付给弱方可以提高其接受度，支付给强方可以补偿其让步损失\n"
            f"- 边支付金额应该与效用缺口成正比\n\n"
            f"**第三层：可负担性检查（Affordability）**\n"
            f"- 总预算: {total:.2f}，已使用: {context.side_payment_used:.2f}，剩余: {remaining:.2f}\n"
            f"- {pace_note}\n"
            f"- **关键约束**：你的 side_payment_amount 不能超过本轮最高限额 {max_this_round:.2f}\n"
            f"- **R7-R8 终极策略**：将剩余预算的 100% 全部使用——这是达成协议的最后机会\n"
        )

    async def act(self, context: NegotiationContext) -> Proposal:
        """Generate a mediation proposal with optional side payment."""
        if context.history:
            # Build rich history showing full negotiation trajectory
            lines = [f"## 谈判轨迹（共 {len(context.history)} 轮）\n"]
            prev_strong_accepted = False
            prev_weak_accepted = False
            for rec in context.history[-6:]:  # last 6 rounds max
                s_pa = rec.domestic_strong_score.political_acceptability
                w_pa = rec.domestic_weak_score.political_acceptability
                s_pr = rec.domestic_strong_score.pressure_level
                w_pr = rec.domestic_weak_score.pressure_level
                lines.append(
                    f"R{rec.round_number}: 领土{rec.mediator_proposal.territory_split:.0f}% "
                    f"边支付{rec.mediator_proposal.side_payment_amount:.2f}→{rec.mediator_proposal.side_payment_recipient} | "
                    f"强方:{rec.strong_response.action}(接受度{100*s_pa:.0f}%压力{100*s_pr:.0f}%) "
                    f"弱方:{rec.weak_response.action}(接受度{100*w_pa:.0f}%压力{100*w_pr:.0f}%)"
                )
                if rec.strong_response.action == "accept":
                    prev_strong_accepted = True
                if rec.weak_response.action == "accept":
                    prev_weak_accepted = True
            lines.append("")
            lines.append(f"强方效用: {context.strong_current_utility:.1f}/{context.strong_initial_utility:.1f} "
                         f"(阈值 {context.strong_initial_utility*0.3:.1f})")
            lines.append(f"弱方效用: {context.weak_current_utility:.1f}/{context.weak_initial_utility:.1f} "
                         f"(阈值 {context.weak_initial_utility*0.3:.1f})")

            # Oscillation detection
            osc_warnings = []
            if prev_strong_accepted:
                osc_warnings.append("⚠️ 强方曾在本谈判中接受过提案——不要降低强方的条款（缩小领土占比/减少资源分配/削减边支付），也不要在对方拒绝时大幅提高弱方让步要求。维持让强方满意的方向不变。")
            if prev_weak_accepted:
                osc_warnings.append("⚠️ 弱方曾在本谈判中接受过提案——不要改变让弱方满意的条款方向，只调整针对拒绝方的参数。例如强方接受弱方拒绝，保持弱方的领土和资源份额不变，增加对强方的安全保障作为平衡。")
            if osc_warnings:
                lines.append("\n### ⚠️ 防震荡警告")
                lines.extend(osc_warnings)

            lines.append(f"\n请分析双方回应模式，提出新一轮提案。")
            history_summary = "\n".join(lines)
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

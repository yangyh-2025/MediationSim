from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from pydantic import BaseModel

from backend.llm.client import LLMClient
from backend.models.schemas import NegotiationContext

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


class BaseAgent(ABC):
    """Abstract base for all negotiation simulation agents.

    CACHE STRATEGY (DeepSeek V4 prefix caching):
    - system_prompt is LOADED ONCE in __init__ and NEVER modified
    - _build_messages always puts system prompt as messages[0]
    - dynamic content (context summary + user message) goes in the user message ONLY
    - This ensures byte-exact prefix matching for cache hits across rounds
    """

    def __init__(
        self,
        name: str,
        role: str,
        system_prompt: str,
        llm: LLMClient,
    ) -> None:
        self.name = name
        self.role = role
        self.system_prompt = system_prompt  # IMMUTABLE — never modify
        self.llm = llm

    @staticmethod
    def _load_prompt(filename: str, **kwargs: object) -> str:
        path = PROMPTS_DIR / filename
        text = path.read_text(encoding="utf-8")
        for k, v in kwargs.items():
            text = text.replace("{" + k + "}", str(v))
        return text

    def _build_context_summary(self, context: NegotiationContext) -> str:
        lines: list[str] = []
        lines.append(f"- 实验条件代码: {context.condition_code}")
        lines.append(f"- 不对称比率 (AR): {context.ar:.2f}")
        lines.append(f"- 调停者偏见 (bias): {context.mediator_bias:.2f}")
        lines.append(f"- 当前轮次: {context.round_number}")
        lines.append(f"- 是否最后一轮: {'是' if context.is_final_round else '否'}")
        lines.append(f"- 强方初始效用: {context.strong_initial_utility:.2f}")
        lines.append(f"- 强方当前效用: {context.strong_current_utility:.2f}")
        lines.append(f"- 弱方初始效用: {context.weak_initial_utility:.2f}")
        lines.append(f"- 弱方当前效用: {context.weak_current_utility:.2f}")
        lines.append(f"- 边支付预算: {context.side_payment_budget:.2f}")
        lines.append(f"- 边支付已使用: {context.side_payment_used:.2f}")

        if context.history:
            lines.append(f"\n历史谈判记录（共{len(context.history)}轮）:")
            for record in context.history[-5:]:
                lines.append(f"  第{record.round_number}轮:")
                lines.append(
                    f"    调停者提案: 领土划分 {record.mediator_proposal.territory_split}%, "
                    f"边支付 {record.mediator_proposal.side_payment_amount}, "
                    f"接收方 {record.mediator_proposal.side_payment_recipient}"
                )
                lines.append(f"    强方回应: {record.strong_response.action}")
                lines.append(f"    弱方回应: {record.weak_response.action}")
                lines.append(f"    协议达成: {'是' if record.agreement_reached else '否'}")
                lines.append(
                    f"    强方国内接受度: {record.domestic_strong_score.political_acceptability:.2f}, "
                    f"压力: {record.domestic_strong_score.pressure_level:.2f}"
                )
                lines.append(
                    f"    弱方国内接受度: {record.domestic_weak_score.political_acceptability:.2f}, "
                    f"压力: {record.domestic_weak_score.pressure_level:.2f}"
                )
        else:
            lines.append("\n（尚无历史记录，这是第一轮谈判）")

        return "\n".join(lines)

    def _build_messages(
        self, context: NegotiationContext, user_message: str
    ) -> list[dict]:
        """
        Build LLM messages optimized for DeepSeek V4 prefix caching.

        KEY: system prompt (immutable) goes first → byte-exact prefix match
        Dynamic content (context + instructions) goes in the user message → never in prefix
        """
        return [
            {"role": "system", "content": self.system_prompt},
            {
                "role": "user",
                "content": (
                    f"## 当前谈判状态\n\n"
                    f"{self._build_context_summary(context)}\n\n"
                    f"## 你需要做什么\n\n"
                    f"{user_message}"
                ),
            },
        ]

    @abstractmethod
    async def act(self, context: NegotiationContext) -> BaseModel:
        """Receive negotiation context, return a structured action."""
        ...

from __future__ import annotations

import time
import uuid

from backend.llm.client import LLMClient
from backend.llm.logger import call_context
from backend.models.schemas import (
    NegotiationContext,
    Proposal,
    AgentResponse,
    DomesticScore,
    RoundRecord,
    RunResult,
)
from backend.config import config


class NegotiationEngine:
    """8-step negotiation protocol for one simulation run."""

    def __init__(
        self,
        condition_code: str,
        ar: float,
        mediator_bias: float,
        side_payment_enabled: bool = True,
        *,
        experiment_id: str = "",
        run_id: str = "",
        on_round_complete: object = None,  # async callback(rounds_completed: int)
    ) -> None:
        self.condition_code = condition_code
        self.ar = ar
        self.mediator_bias = mediator_bias
        self.side_payment_enabled = side_payment_enabled
        self.experiment_id = experiment_id
        self._run_id = run_id
        self._on_round_complete = on_round_complete

        # Shared LLM client — ONE instance for all agents → cache affinity
        self._llm = LLMClient(experiment_id=experiment_id)

        side_payment_budget = (config.side_payment_budget_pct / 100.0) * 200.0

        from backend.agents.strong_party import StrongParty
        from backend.agents.weak_party import WeakParty
        from backend.agents.mediator import Mediator
        from backend.agents.domestic_audience import DomesticAudience

        self.strong = StrongParty(self._llm, ar)
        self.weak = WeakParty(self._llm, ar)
        self.mediator = Mediator(self._llm, mediator_bias, side_payment_budget, side_payment_enabled)
        self.audience = DomesticAudience(self._llm)

        # Initialize context (Step 1)
        self.context = NegotiationContext(
            condition_code=condition_code,
            ar=ar,
            mediator_bias=mediator_bias,
            strong_initial_utility=self._initial_utility_strong(),
            weak_initial_utility=self._initial_utility_weak(),
            strong_current_utility=self._initial_utility_strong(),
            weak_current_utility=self._initial_utility_weak(),
            side_payment_budget=side_payment_budget,
        )

    # ── Cache warming ────────────────────────────────────

    async def warm_caches(self) -> None:
        """
        Pre-heat DeepSeek V4 prefix caches for all agent system prompts.

        Each agent's system prompt is its cache prefix. By sending one
        tiny request per agent, subsequent real calls start with a cache HIT.
        This turns the first round's 5 cache-miss calls into 5 cache-hit calls.
        """
        agents = [
            (self.strong.system_prompt, AgentResponse),
            (self.weak.system_prompt, AgentResponse),
            (self.mediator.system_prompt, Proposal),
        ]
        # Domestic audience warms both "strong" and "weak" variants via the same prompt
        for prompt, schema in agents:
            await self._llm.warm_cache(prompt, schema)
        await self._llm.warm_cache(self.audience.system_prompt, DomesticScore)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _initial_utility_strong(self) -> float:
        """Utility scales linearly with AR: stronger party starts higher."""
        return 100.0 * self.ar

    def _initial_utility_weak(self) -> float:
        return 100.0

    # ------------------------------------------------------------------
    # Main run loop (Steps 2–7)
    # ------------------------------------------------------------------

    async def run(self) -> RunResult:
        run_id = self._run_id or str(uuid.uuid4())
        start_time = time.time()
        rounds: list[RoundRecord] = []

        # Hydrate call context
        call_context.condition_code = self.condition_code
        call_context.run_id = run_id
        call_context.experiment_id = self.experiment_id

        for rnd in range(1, config.max_rounds + 1):
            self.context.round_number = rnd
            self.context.is_final_round = (rnd == config.max_rounds)
            call_context.round_number = rnd

            round_record = await self._execute_round(rnd)
            rounds.append(round_record)

            # ── Live progress callback ──
            if self._on_round_complete is not None:
                try:
                    await self._on_round_complete(len(rounds))
                except Exception:
                    pass

            if round_record.agreement_reached:
                break

        elapsed = time.time() - start_time

        agreement = any(r.agreement_reached for r in rounds)
        final_proposal = rounds[-1].mediator_proposal if rounds else None
        gini = self._calculate_gini(final_proposal) if final_proposal else None
        total_payment = sum(
            r.mediator_proposal.side_payment_amount
            for r in rounds
            if r.mediator_proposal is not None
        )

        return RunResult(
            run_id=run_id,
            condition_code=self.condition_code,
            run_index=0,
            status="completed",
            rounds_completed=len(rounds),
            agreement_reached=agreement,
            final_proposal=final_proposal,
            agreement_gini=gini,
            side_payment_used_total=total_payment,
            round_records=rounds,
            total_duration_seconds=elapsed,
        )

    async def _execute_round(self, round_num: int) -> RoundRecord:
        t0 = time.time()

        call_context.agent_name = "StrongParty"
        strong_statement = await self.strong.act(self.context)

        call_context.agent_name = "WeakParty"
        weak_statement = await self.weak.act(self.context)

        call_context.agent_name = "Mediator"
        proposal = await self.mediator.act(self.context)

        call_context.agent_name = "DomesticAudience-强"
        dom_strong = await self.audience.act(self.context, proposal, "strong")

        call_context.agent_name = "DomesticAudience-弱"
        dom_weak = await self.audience.act(self.context, proposal, "weak")

        call_context.agent_name = "StrongParty-response"
        strong_resp = await self.strong.respond_to_proposal(
            self.context, proposal, dom_strong
        )

        call_context.agent_name = "WeakParty-response"
        weak_resp = await self.weak.respond_to_proposal(
            self.context, proposal, dom_weak
        )

        # Step 6: Agreement check (both accept)
        agreement = (
            strong_resp.action == "accept" and weak_resp.action == "accept"
        )

        # Persist round
        record = RoundRecord(
            round_number=round_num,
            mediator_proposal=proposal,
            strong_response=strong_resp,
            weak_response=weak_resp,
            domestic_strong_score=dom_strong,
            domestic_weak_score=dom_weak,
            agreement_reached=agreement,
            round_duration_seconds=time.time() - t0,
        )
        self.context.history.append(record)

        # Update current utility estimates from responses
        self.context.strong_current_utility += strong_resp.utility_change
        self.context.weak_current_utility += weak_resp.utility_change
        if proposal.side_payment_amount > 0:
            self.context.side_payment_used += proposal.side_payment_amount

        return record

    # ------------------------------------------------------------------
    # Gini calculation
    # ------------------------------------------------------------------

    def _calculate_gini(self, proposal: Proposal) -> float:
        """Gini coefficient for the final agreement.

        Territory-driven base: |strong_pct - weak_pct| / 100.
        Adjusted by resource allocation skew and side-payment direction.
        """
        territory_gini = abs(
            proposal.territory_split - (100.0 - proposal.territory_split)
        ) / 100.0

        # Resource allocation skew
        if proposal.resource_allocation:
            values = list(proposal.resource_allocation.values())
            if values and sum(values) > 0:
                sorted_vals = sorted(values)
                n = len(sorted_vals)
                gini_res = (
                    sum((2 * i - n - 1) * v for i, v in enumerate(sorted_vals, 1))
                    / (n * sum(sorted_vals))
                )
                territory_gini = 0.6 * territory_gini + 0.4 * abs(gini_res)

        # Side-payment direction adjustment
        if (
            proposal.side_payment_recipient == "weak"
            and proposal.side_payment_amount > 0
        ):
            territory_gini = max(0.0, territory_gini - 0.05)
        elif (
            proposal.side_payment_recipient == "strong"
            and proposal.side_payment_amount > 0
        ):
            territory_gini = min(1.0, territory_gini + 0.05)

        return round(territory_gini, 4)

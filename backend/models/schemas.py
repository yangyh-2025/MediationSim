from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import uuid4

from math import isnan

from pydantic import BaseModel, Field, field_validator, field_serializer


# ═══════════════════════════════════════════════════════
# Negotiation Data Models
# ═══════════════════════════════════════════════════════

class ResourceDistribution(BaseModel):
    territory_pct: float = Field(..., ge=0, le=100, description="领土划分比例（强方占比）")
    economic_aid: float = Field(..., ge=0, description="经济援助额度")
    military_aid: float = Field(..., ge=0, description="军事援助额度")
    security_guarantees: list[str] = Field(default_factory=list)

    @field_validator("territory_pct")
    @classmethod
    def pct_range(cls, v: float) -> float:
        if not (0 <= v <= 100):
            raise ValueError(f"territory_pct must be 0-100, got {v}")
        return v


class Proposal(BaseModel):
    round_number: int = Field(..., ge=1)
    mediator_bias: float = Field(..., description="调停者偏见值 b")
    territory_split: float = Field(..., ge=0, le=100, description="领土分配（强方百分比）")
    resource_allocation: dict[str, float] = Field(default_factory=dict)
    side_payment_amount: float = Field(0, ge=0)
    side_payment_recipient: str = Field("none", pattern="^(strong|weak|none)$")
    justification: str = ""

    @field_validator("territory_split")
    @classmethod
    def valid_territory(cls, v: float) -> float:
        if not (0 <= v <= 100):
            raise ValueError(f"territory_split must be 0-100, got {v}")
        return v

    @field_validator("side_payment_recipient")
    @classmethod
    def valid_recipient(cls, v: str) -> str:
        if v not in ("strong", "weak", "none"):
            raise ValueError(f"recipient must be strong|weak|none, got {v}")
        return v


class AgentResponse(BaseModel):
    agent_type: str = ""
    action: str = Field(..., pattern="^(accept|reject|counter_proposal)$")
    counter_proposal: Optional[Proposal] = None
    reasoning: str = ""
    utility_change: float = 0.0


class DomesticScore(BaseModel):
    agent_type: str = ""
    political_acceptability: float = Field(..., ge=0, le=1)
    pressure_level: float = Field(..., ge=0, le=1)
    key_concerns: list[str] = Field(default_factory=list)


class RoundRecord(BaseModel):
    round_number: int = Field(..., ge=1)
    mediator_proposal: Proposal
    strong_response: AgentResponse
    weak_response: AgentResponse
    domestic_strong_score: DomesticScore
    domestic_weak_score: DomesticScore
    agreement_reached: bool = False
    round_duration_seconds: float = 0.0


# ═══════════════════════════════════════════════════════
# Context & State
# ═══════════════════════════════════════════════════════

class NegotiationContext(BaseModel):
    condition_code: str = ""
    ar: float = 1.0  # asymmetry ratio
    mediator_bias: float = 0.0
    round_number: int = 0
    history: list[RoundRecord] = Field(default_factory=list)
    strong_initial_utility: float = 100.0
    weak_initial_utility: float = 100.0
    strong_current_utility: float = 100.0
    weak_current_utility: float = 100.0
    side_payment_budget: float = 0.0
    side_payment_used: float = 0.0
    is_final_round: bool = False


# ═══════════════════════════════════════════════════════
# Run & Experiment Results
# ═══════════════════════════════════════════════════════

class RunResult(BaseModel):
    run_id: str = Field(default_factory=lambda: str(uuid4()))
    experiment_id: str = ""
    condition_code: str = ""
    run_index: int = 0
    status: str = "pending"
    rounds_completed: int = 0
    agreement_reached: bool = False
    final_proposal: Optional[Proposal] = None
    agreement_gini: Optional[float] = None
    side_payment_used_total: float = 0.0
    round_records: list[RoundRecord] = Field(default_factory=list)
    total_duration_seconds: float = 0.0
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())


# ═══════════════════════════════════════════════════════
# Evaluation
# ═══════════════════════════════════════════════════════

class EvaluationDimension(BaseModel):
    name: str = ""
    score: float = Field(0.0, ge=0, le=10)
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class EvaluationReport(BaseModel):
    batch_start: int = 0
    batch_end: int = 0
    condition_code: str = ""
    dimensions: list[EvaluationDimension] = Field(default_factory=list)
    overall_score: float = Field(0.0, ge=0, le=10)
    trend_vs_previous: Optional[dict] = None
    parameter_adjustments: list[dict] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())


# ═══════════════════════════════════════════════════════
# Experiment Configuration & Status
# ═══════════════════════════════════════════════════════

class ExperimentConfigIn(BaseModel):
    name: str = Field("默认实验", min_length=1, max_length=200)
    conditions: list[str] = Field(default_factory=lambda: ["H-PS", "H-N", "H-PW", "L-PS", "L-N", "L-PW", "CD"])
    runs_per_condition: int = Field(10, ge=1, le=100)
    max_rounds: int = Field(8, ge=1, le=50)
    temperature: float = Field(0.7, ge=0, le=2.0)
    max_tokens: int = Field(2048, ge=100, le=16384)
    side_payment_enabled: bool = True
    max_retries: int = Field(3, ge=0, le=10)

    @field_validator("conditions")
    @classmethod
    def valid_conditions(cls, v: list[str]) -> list[str]:
        valid_codes = {"H-PS", "H-N", "H-PW", "L-PS", "L-N", "L-PW", "CD"}
        for code in v:
            if code not in valid_codes:
                raise ValueError(f"Invalid condition code: {code}. Must be one of {valid_codes}")
        return v


class ConditionProgress(BaseModel):
    completed: int = 0
    total: int = 0
    agreement_rate: float = 0.0


class ExperimentStatus(BaseModel):
    experiment_id: str = Field(default_factory=lambda: str(uuid4()))
    name: str = ""
    status: str = "draft"
    total_runs: int = 0
    completed_runs: int = 0
    conditions_progress: dict[str, ConditionProgress] = Field(default_factory=dict)
    started_at: str = ""
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())


# ═══════════════════════════════════════════════════════
# Hypothesis Testing
# ═══════════════════════════════════════════════════════

class HypothesisResult(BaseModel):
    hypothesis: str = ""
    test_name: str = ""
    test_statistic: float = 0.0
    p_value: float = 1.0
    effect_size: float = 0.0
    confidence_interval: tuple[float, float] = (0.0, 0.0)
    significant: bool = False
    interpretation: str = ""

    @field_serializer("test_statistic")
    def serialize_statistic(self, v: float) -> float:
        return 0.0 if isnan(v) else float(v)

    @field_serializer("p_value")
    def serialize_p(self, v: float) -> float:
        return 1.0 if isnan(v) else float(v)

    @field_serializer("effect_size")
    def serialize_effect(self, v: float) -> float:
        return 0.0 if isnan(v) else float(v)

    @field_serializer("confidence_interval")
    def serialize_ci(self, v: tuple[float, float]) -> tuple[float, float]:
        return tuple(0.0 if isnan(x) else float(x) for x in v)


# ═══════════════════════════════════════════════════════
# API Request/Response helpers
# ═══════════════════════════════════════════════════════

class APIResponse(BaseModel):
    success: bool = True
    message: str = ""
    data: Optional[dict] = None

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 加载 .env 文件（如果存在）
try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass


@dataclass
class Config:
    # ── LLM ───────────────────────────────────────────
    llm_model: str = "gpt-4o"
    llm_temperature: float = 0.7
    llm_max_tokens: int = 2048
    llm_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    llm_base_url: str = field(default_factory=lambda: os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"))

    # ── Experiment ────────────────────────────────────
    max_rounds: int = 8
    runs_per_condition: int = 10
    max_proposals_per_round: int = 3
    side_payment_budget_pct: float = 2.0  # % of mediator GDP

    # ── Concurrency ───────────────────────────────────
    max_concurrent_conditions: int = 7    # DeepSeek 500并发 → 全部条件并行
    llm_concurrency: int = 50             # LLM 调用全局并发上限

    # ── Evaluation ────────────────────────────────────
    fast_iteration_interval: int = 10
    medium_iteration_interval: int = 30
    alpha: float = 0.05  # significance level

    # ── Paths ─────────────────────────────────────────
    data_dir: Path = PROJECT_ROOT / "data"
    experiments_dir: Path = PROJECT_ROOT / "data" / "experiments"
    evaluations_dir: Path = PROJECT_ROOT / "data" / "evaluations"
    results_dir: Path = PROJECT_ROOT / "data" / "results"
    db_path: Path = PROJECT_ROOT / "data" / "mediation_sim.db"

    # ── Experiment Conditions ─────────────────────────
    conditions: list[dict] = field(default_factory=lambda: [
        {"code": "H-PS",  "ar": 3.0, "bias":  0.7, "label": "高不对称-亲强调停"},
        {"code": "H-N",   "ar": 3.0, "bias":  0.0, "label": "高不对称-中立调停"},
        {"code": "H-PW",  "ar": 3.0, "bias": -0.7, "label": "高不对称-亲弱调停"},
        {"code": "L-PS",  "ar": 1.5, "bias":  0.7, "label": "低不对称-亲强调停"},
        {"code": "L-N",   "ar": 1.5, "bias":  0.0, "label": "低不对称-中立调停"},
        {"code": "L-PW",  "ar": 1.5, "bias": -0.7, "label": "低不对称-亲弱调停"},
        {"code": "CD",    "ar": 2.0, "bias":  0.7, "label": "戴维营参照组"},
    ])

    def get_condition(self, code: str) -> dict:
        for c in self.conditions:
            if c["code"] == code:
                return c
        raise KeyError(f"Unknown condition: {code}")

    def get_all_conditions(self) -> list[dict]:
        return list(self.conditions)

    def ensure_dirs(self) -> None:
        for d in [self.data_dir, self.experiments_dir, self.evaluations_dir, self.results_dir]:
            d.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_env(cls) -> Config:
        return cls(
            llm_api_key=os.getenv("OPENAI_API_KEY", ""),
            llm_base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            llm_model=os.getenv("LLM_MODEL", "gpt-4o"),
            max_concurrent_conditions=int(os.getenv("MAX_CONCURRENT_CONDITIONS", "7")),
            llm_concurrency=int(os.getenv("LLM_CONCURRENCY", "50")),
        )


config = Config.from_env()

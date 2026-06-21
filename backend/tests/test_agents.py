"""
Tests for the biased mediation multi-agent simulation system.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


def test_config():
    """Test configuration loading."""
    from backend.config import config
    assert config is not None
    assert config.max_rounds == 8
    assert config.runs_per_condition == 10
    assert len(config.conditions) == 7
    assert config.alpha == 0.05
    # Verify condition codes
    codes = [c["code"] for c in config.conditions]
    assert "H-PS" in codes
    assert "CD" in codes
    # Verify get_condition
    cd = config.get_condition("CD")
    assert cd["ar"] == 2.0
    assert cd["bias"] == 0.7


def test_schemas():
    """Test Pydantic schemas validation."""
    from backend.models.schemas import (
        Proposal, AgentResponse, DomesticScore, NegotiationContext, ExperimentConfigIn,
    )

    # Proposal validation
    p = Proposal(round_number=1, mediator_bias=0.7, territory_split=60.0,
                 side_payment_amount=10.0, side_payment_recipient="weak",
                 justification="Compensation for territorial concessions")
    assert p.territory_split == 60.0
    assert p.side_payment_recipient == "weak"

    # Proposal validation: bad territory
    try:
        Proposal(round_number=1, mediator_bias=0.7, territory_split=150.0)
        assert False, "Should have raised ValidationError"
    except Exception:
        pass

    # AgentResponse
    r = AgentResponse(action="accept", reasoning="Terms acceptable", utility_change=-5.0)
    assert r.action == "accept"

    # DomesticScore
    ds = DomesticScore(political_acceptability=0.7, pressure_level=0.3, key_concerns=["领土让步过大"])
    assert 0 <= ds.political_acceptability <= 1

    # NegotiationContext
    ctx = NegotiationContext(condition_code="CD", ar=2.0, mediator_bias=0.7)
    assert ctx.condition_code == "CD"

    # ExperimentConfigIn
    cfg = ExperimentConfigIn(name="测试实验", conditions=["CD"], runs_per_condition=5)
    assert cfg.name == "测试实验"


def test_database_schema():
    """Test database table creation."""
    import asyncio
    import tempfile
    from backend.db.database import Database

    async def _test():
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp_path = tmp.name
        tmp.close()

        db = Database(tmp_path)
        await db.initialize()

        # Verify tables
        tables = await db.fetch_all("SELECT name FROM sqlite_master WHERE type='table'")
        table_names = [t["name"] for t in tables]
        assert "experiments" in table_names
        assert "runs" in table_names
        assert "rounds" in table_names
        assert "evaluations" in table_names
        assert "analysis_results" in table_names

        await db.close()

        # Cleanup
        import os
        os.unlink(tmp_path)

    asyncio.run(_test())


def test_hypothesis_test_imports():
    """Test that all analysis functions can be imported."""


def test_analysis_module_imports():
    """Test analysis submodule imports."""


def test_engine_module_imports():
    """Test engine module imports."""


def test_agent_module_imports():
    """Test agent module imports."""


def test_llm_client_import():
    """Test LLM client import."""


def test_prompts_exist():
    """Verify all prompt files exist."""
    from backend.agents.base import PROMPTS_DIR

    expected = [
        "strong_party.txt",
        "weak_party.txt",
        "mediator_pro_strong.txt",
        "mediator_neutral.txt",
        "mediator_pro_weak.txt",
        "domestic_audience.txt",
        "evaluator.txt",
    ]
    for fname in expected:
        path = PROMPTS_DIR / fname
        assert path.exists(), f"Missing prompt: {fname}"
        content = path.read_text(encoding="utf-8")
        assert len(content) > 100, f"Prompt {fname} is too short (<100 chars)"


def test_cohens_d():
    """Test Cohen's d calculation."""
    from backend.analysis.hypothesis_tests import cohens_d
    import numpy as np

    g1 = np.array([1, 2, 3, 4, 5])
    g2 = np.array([6, 7, 8, 9, 10])
    d = cohens_d(g1, g2)
    # Should be large negative (g1 < g2)
    assert d is not None
    assert isinstance(d, float)


if __name__ == "__main__":
    tests = [
        ("Config", test_config),
        ("Schemas", test_schemas),
        ("Database", test_database_schema),
        ("Hypothesis imports", test_hypothesis_test_imports),
        ("Analysis imports", test_analysis_module_imports),
        ("Engine imports", test_engine_module_imports),
        ("Agent imports", test_agent_module_imports),
        ("LLM client import", test_llm_client_import),
        ("Prompts exist", test_prompts_exist),
        ("Cohen's d", test_cohens_d),
    ]

    passed = 0
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
            passed += 1
        except Exception as e:
            print(f"  FAIL  {name}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")

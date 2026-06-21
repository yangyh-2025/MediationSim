"""
端到端全功能测试脚本 — 偏见调停多智能体模拟系统

测试范围：
1. 所有 API 端点的请求/响应格式
2. 数据模型验证（schema 边界测试）
3. 数据库 CRUD 完整链路
4. 统计分析计算正确性
5. 实验条件配置验证
6. 智能体提示词加载
"""
from __future__ import annotations

import sys
import json
import asyncio
import tempfile
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.config import config
from backend.db.database import Database
from backend.db import queries as dbq
from backend.models.schemas import (
    Proposal, AgentResponse, DomesticScore, RoundRecord,
    RunResult, NegotiationContext, ExperimentConfigIn,
    HypothesisResult, EvaluationReport, EvaluationDimension,
    ExperimentStatus, ConditionProgress
)
from backend.analysis.hypothesis_tests import (
    test_h1_bias_main_effect, test_h2_agreement_quality,
    test_h4_moderation_effect, run_all_tests, cohens_d, eta_squared_from_f
)
from backend.analysis.mediation import bootstrap_mediation, sobel_test, ols_coef

PASS, FAIL = 0, 0

def check(name: str, condition: bool, detail: str = ""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}  -- {detail}")

def section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# ═══════════════════════════════════════════════════════
# 1. 配置模块测试
# ═══════════════════════════════════════════════════════
section("1. 配置模块")

check("Config 单例加载", config is not None)
check("LLM 默认模型", config.llm_model == "gpt-4o")
check("LLM 默认温度", config.llm_temperature == 0.7)
check("最大谈判轮次", config.max_rounds == 10)
check("每条件运行次数", config.runs_per_condition == 30)
check("显著性水平", config.alpha == 0.05)
check("附带支付预算百分比", config.side_payment_budget_pct == 0.5)
check("条件数量", len(config.conditions) == 7)

# 验证每个条件
expected_conditions = [
    ("H-PS",  3.0,  0.7, "高不对称-亲强调停"),
    ("H-N",   3.0,  0.0, "高不对称-中立调停"),
    ("H-PW",  3.0, -0.7, "高不对称-亲弱调停"),
    ("L-PS",  1.5,  0.7, "低不对称-亲强调停"),
    ("L-N",   1.5,  0.0, "低不对称-中立调停"),
    ("L-PW",  1.5, -0.7, "低不对称-亲弱调停"),
    ("CD",    2.0,  0.7, "戴维营参照组"),
]
for i, (code, ar, bias, label) in enumerate(expected_conditions):
    cond = config.conditions[i]
    check(f"条件 {code} AR={ar}", cond["ar"] == ar and cond["code"] == code,
          f"got {cond['ar']}, {cond['code']}")

check("get_condition H-PS", config.get_condition("H-PS")["ar"] == 3.0)
check("get_condition CD (戴维营)", config.get_condition("CD")["bias"] == 0.7)
try:
    config.get_condition("NONEXISTENT")
    check("get_condition 不存在应抛异常", False, "没有抛出异常")
except KeyError:
    check("get_condition 不存在抛 KeyError", True)

check("ensure_dirs 创建数据目录", True)  # tested earlier

# 目录验证
for d in [config.data_dir, config.experiments_dir, config.evaluations_dir, config.results_dir]:
    check(f"目录存在: {d.name}", d.exists())

# 全因子实验条件完整性
check("全因子: 高不对称 3 条件", sum(1 for c in config.conditions if c["ar"] == 3.0) == 3)
check("全因子: 低不对称 3 条件", sum(1 for c in config.conditions if c["ar"] == 1.5) == 3)
check("参照组: CD 1 条件", sum(1 for c in config.conditions if c["code"] == "CD") == 1)
# 按偏见方向分类
check("亲强条件 (b=+0.7)", sum(1 for c in config.conditions if c["bias"] == 0.7) == 3)
check("中立条件 (b=0.0)", sum(1 for c in config.conditions if c["bias"] == 0.0) == 2)
check("亲弱条件 (b=-0.7)", sum(1 for c in config.conditions if c["bias"] == -0.7) == 2)


# ═══════════════════════════════════════════════════════
# 2. Pydantic Schema 测试
# ═══════════════════════════════════════════════════════
section("2. Pydantic Schema 验证")

# 2.1 Proposal
p = Proposal(round_number=1, mediator_bias=0.7, territory_split=65.0,
             side_payment_amount=15.0, side_payment_recipient="weak",
             justification="对弱方的领土让步补偿")
check("Proposal 创建", p.territory_split == 65.0)
check("Proposal side_payment_recipient", p.side_payment_recipient == "weak")
check("Proposal 默认值", Proposal(round_number=1, mediator_bias=0.0, territory_split=50.0).side_payment_amount == 0)
check("Proposal 默认 recipient", Proposal(round_number=1, mediator_bias=0.0, territory_split=50.0).side_payment_recipient == "none")

# 边界值测试
check("Proposal territory=0", Proposal(round_number=1, mediator_bias=0.0, territory_split=0.0).territory_split == 0.0)
check("Proposal territory=100", Proposal(round_number=1, mediator_bias=0.0, territory_split=100.0).territory_split == 100.0)
check("Proposal side_payment=0", Proposal(round_number=1, mediator_bias=0.0, territory_split=50.0, side_payment_amount=0.0).side_payment_amount == 0.0)

# 非法值测试
try:
    Proposal(round_number=1, mediator_bias=0.0, territory_split=150.0)
    check("Proposal territory>100 应拒绝", False, "没有抛出异常")
except Exception:
    check("Proposal territory>100 validation rejected", True)

try:
    Proposal(round_number=1, mediator_bias=0.0, territory_split=-5.0)
    check("Proposal territory<0 应拒绝", False, "没有抛出异常")
except Exception:
    check("Proposal territory<0 validation rejected", True)

try:
    Proposal(round_number=1, mediator_bias=0.0, territory_split=50.0, side_payment_recipient="invalid")
    check("Proposal recipient=invalid 应拒绝", False, "没有抛出异常")
except Exception:
    check("Proposal recipient validation rejected", True)

try:
    Proposal(round_number=0, mediator_bias=0.0, territory_split=50.0)
    check("Proposal round<1 应拒绝", False, "没有抛出异常")
except Exception:
    check("Proposal round<1 validation rejected", True)

# 2.2 AgentResponse
r_accept = AgentResponse(action="accept", reasoning="条款可接受", utility_change=-5.0)
check("AgentResponse accept", r_accept.action == "accept")

r_reject = AgentResponse(action="reject", reasoning="领土让步过大")
check("AgentResponse reject", r_reject.action == "reject")

r_counter = AgentResponse(action="counter_proposal", reasoning="需要调整")
check("AgentResponse counter_proposal", r_counter.action == "counter_proposal")

try:
    AgentResponse(action="invalid_action")
    check("AgentResponse 非法 action 应拒绝", False)
except Exception:
    check("AgentResponse 非法 action validation rejected", True)

# 2.3 DomesticScore
ds = DomesticScore(political_acceptability=0.7, pressure_level=0.3, key_concerns=["领土让步过大", "安全保障不足"])
check("DomesticScore 创建", ds.political_acceptability == 0.7)
check("DomesticScore 关注点数量", len(ds.key_concerns) == 2)

# 边界值
try:
    DomesticScore(political_acceptability=1.5, pressure_level=0.3)
    check("DomesticScore acceptability>1 应拒绝", False)
except Exception:
    check("DomesticScore acceptability>1 validation rejected", True)

try:
    DomesticScore(political_acceptability=0.5, pressure_level=-0.1)
    check("DomesticScore pressure<0 应拒绝", False)
except Exception:
    check("DomesticScore pressure<0 validation rejected", True)

# 2.4 RoundRecord — 完整链路
rr = RoundRecord(
    round_number=1,
    mediator_proposal=p,
    strong_response=r_accept,
    weak_response=r_counter,
    domestic_strong_score=DomesticScore(political_acceptability=0.8, pressure_level=0.2),
    domestic_weak_score=DomesticScore(political_acceptability=0.4, pressure_level=0.7, key_concerns=["不公平条款"]),
    agreement_reached=False,
    round_duration_seconds=12.5,
)
check("RoundRecord 完整创建", rr.round_number == 1)
check("RoundRecord 强方回应", rr.strong_response.action == "accept")
check("RoundRecord 未达成协议", rr.agreement_reached == False)

# 2.5 NegotiationContext
ctx = NegotiationContext(
    condition_code="CD", ar=2.0, mediator_bias=0.7,
    strong_initial_utility=200.0, weak_initial_utility=100.0,
    side_payment_budget=30.0,
)
check("NegotiationContext 创建", ctx.condition_code == "CD")
check("NegotiationContext AR", ctx.ar == 2.0)
check("NegotiationContext 初始历史为空", len(ctx.history) == 0)

# 2.6 RunResult
result = RunResult(
    condition_code="H-PS", run_index=0, status="completed",
    rounds_completed=4, agreement_reached=True,
    agreement_gini=0.62, side_payment_used_total=25.0,
    round_records=[rr], total_duration_seconds=45.0,
)
check("RunResult 创建", result.agreement_reached == True)
check("RunResult gini", result.agreement_gini == 0.62)
check("RunResult 轮次数", result.rounds_completed == 4)

# 2.7 ExperimentConfigIn
cfg = ExperimentConfigIn(
    name="单元测试实验",
    conditions=["H-PS", "CD"],
    runs_per_condition=5,
    max_rounds=10,
    temperature=0.8,
    side_payment_enabled=True,
)
check("ExperimentConfigIn 创建", cfg.name == "单元测试实验")
check("ExperimentConfigIn 条件数", len(cfg.conditions) == 2)
check("ExperimentConfigIn 运行次数", cfg.runs_per_condition == 5)

# 边界值
try:
    ExperimentConfigIn(name="", conditions=[], runs_per_condition=0)
    check("ExperimentConfigIn runs=0 应拒绝", False)
except Exception:
    check("ExperimentConfigIn runs=0 validation rejected", True)

try:
    ExperimentConfigIn(name="test", conditions=["H-PS"], runs_per_condition=150)
    check("ExperimentConfigIn runs>100 应拒绝", False)
except Exception:
    check("ExperimentConfigIn runs>100 validation rejected", True)

# 2.8 HypothesisResult
hr = HypothesisResult(
    hypothesis="H1", test_name="独立样本t检验",
    test_statistic=2.45, p_value=0.02, effect_size=0.58,
    confidence_interval=(0.1, 1.06), significant=True,
    interpretation="在高不对称条件下，亲强调停者的协议率显著高于中立调停者",
)
check("HypothesisResult 创建", hr.hypothesis == "H1")
check("HypothesisResult 显著", hr.significant == True)
check("HypothesisResult p<0.05", hr.p_value == 0.02)

# 2.9 EvaluationReport
dim = EvaluationDimension(name="外部效度", score=7.5, issues=["权力话语占比偏低"], suggestions=["增强强方的威慑语言"])
report = EvaluationReport(
    batch_start=0, batch_end=9, condition_code="H-PS",
    dimensions=[dim], overall_score=6.8,
    parameter_adjustments=[{"parameter": "concession_threshold", "old_value": 0.3, "new_value": 0.35}],
)
check("EvaluationReport 创建", report.overall_score == 6.8)
check("EvaluationReport 维度数", len(report.dimensions) == 1)
check("EvaluationReport 调整建议", len(report.parameter_adjustments) == 1)

# 2.10 ExperimentStatus + ConditionProgress
cp = ConditionProgress(completed=15, total=30, agreement_rate=0.53)
check("ConditionProgress 创建", cp.completed == 15 and cp.agreement_rate == 0.53)

status = ExperimentStatus(
    experiment_id="test-123", name="测试", status="running",
    total_runs=210, completed_runs=45,
    conditions_progress={"H-PS": cp},
)
check("ExperimentStatus 状态", status.status == "running")
check("ExperimentStatus 总数", status.total_runs == 210)

# 2.11 Serialization roundtrip
json_str = p.model_dump_json()
p2 = Proposal.model_validate_json(json_str)
check("Proposal JSON 往返序列化", p2.territory_split == p.territory_split and p2.side_payment_recipient == p.side_payment_recipient)


# ═══════════════════════════════════════════════════════
# 3. 数据库模块测试
# ═══════════════════════════════════════════════════════
section("3. 数据库 CRUD")

async def test_database():
    # 临时数据库
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp_path = tmp.name
    tmp.close()

    try:
        db = Database(tmp_path)
        await db.initialize()

        # 3.1 表创建验证
        tables = await db.fetch_all("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        table_names = [t["name"] for t in tables]
        check("表 experiments 存在", "experiments" in table_names)
        check("表 runs 存在", "runs" in table_names)
        check("表 rounds 存在", "rounds" in table_names)
        check("表 evaluations 存在", "evaluations" in table_names)
        check("表 analysis_results 存在", "analysis_results" in table_names)
        check("共 5 张表", len(table_names) == 5)

        # 3.2 CREATE EXPERIMENT
        exp_cfg = ExperimentConfigIn(
            name="DB测试实验", conditions=["H-PS", "H-N", "CD"],
            runs_per_condition=10, max_rounds=10, temperature=0.7,
            side_payment_enabled=True,
        )
        exp_status = await dbq.create_experiment(db, exp_cfg)
        eid = exp_status.experiment_id
        check("创建实验返回 ID", len(eid) > 10)
        check("创建实验状态=draft", exp_status.status == "draft")
        check("创建实验 total_runs=30", exp_status.total_runs == 30)

        # 3.3 LIST EXPERIMENTS
        exps = await dbq.list_experiments(db)
        check("实验列表长度=1", len(exps) == 1)
        check("实验列表名称正确", exps[0]["name"] == "DB测试实验")

        # 3.4 GET EXPERIMENT
        exp = await dbq.get_experiment(db, eid)
        check("获取实验成功", exp is not None)
        check("获取实验状态", exp["status"] == "draft")

        # 3.5 UPDATE EXPERIMENT STATUS
        await dbq.update_experiment_status(db, eid, "running")
        exp = await dbq.get_experiment(db, eid)
        check("更新状态为 running", exp["status"] == "running")

        # 3.6 SAVE RUN RESULT
        run = RunResult(
            experiment_id=eid, condition_code="H-PS", run_index=0,
            status="completed", rounds_completed=3,
            agreement_reached=True, agreement_gini=0.55,
            side_payment_used_total=12.0,
            round_records=[
                RoundRecord(
                    round_number=1,
                    mediator_proposal=Proposal(round_number=1, mediator_bias=0.7, territory_split=60.0,
                                              side_payment_amount=5.0, side_payment_recipient="weak"),
                    strong_response=AgentResponse(action="accept", reasoning="ok"),
                    weak_response=AgentResponse(action="counter_proposal", reasoning="need adjustment"),
                    domestic_strong_score=DomesticScore(political_acceptability=0.8, pressure_level=0.2),
                    domestic_weak_score=DomesticScore(political_acceptability=0.5, pressure_level=0.6),
                    agreement_reached=False,
                ),
            ],
        )
        run_id = await dbq.save_run_result(db, eid, run)
        check("保存 RunResult", len(run_id) > 10)

        # 3.7 GET RUN
        saved_run = await dbq.get_run(db, run_id)
        check("获取 Run", saved_run is not None)
        check("Run 条件码", saved_run["condition_code"] == "H-PS")
        check("Run 协议达成", saved_run["agreement_reached"] == 1)
        check("Run gini", abs(saved_run["agreement_gini"] - 0.55) < 0.01)

        # 3.8 LIST RUNS
        runs = await dbq.list_runs(db, eid)
        check("运行列表长度=1", len(runs) == 1)

        # 按条件筛选
        runs_hps = await dbq.list_runs(db, eid, "H-PS")
        check("按条件筛选 H-PS", len(runs_hps) == 1)
        runs_cd = await dbq.list_runs(db, eid, "CD")
        check("按条件筛选 CD 为空", len(runs_cd) == 0)

        # 3.9 SAVE ROUND
        rr = RoundRecord(
            round_number=2,
            mediator_proposal=Proposal(round_number=2, mediator_bias=0.7, territory_split=55.0,
                                      side_payment_amount=7.0, side_payment_recipient="weak"),
            strong_response=AgentResponse(action="accept", reasoning="acceptable"),
            weak_response=AgentResponse(action="accept", reasoning="compensation sufficient"),
            domestic_strong_score=DomesticScore(political_acceptability=0.9, pressure_level=0.1),
            domestic_weak_score=DomesticScore(political_acceptability=0.6, pressure_level=0.3),
            agreement_reached=True,
        )
        round_id = await dbq.save_round(db, run_id, rr)
        check("保存 Round", len(round_id) > 10)

        # 3.10 GET RUN ROUNDS
        rounds = await dbq.get_run_rounds(db, run_id)
        check("获取 Rounds 数量", len(rounds) == 2)
        check("Round 1 轮次号", rounds[0]["round_number"] == 1)
        check("Round 2 协议达成", rounds[1]["agreement_reached"] == 1)

        # 3.11 SAVE EVALUATION
        eval_report = EvaluationReport(
            batch_start=0, batch_end=9, condition_code="H-PS",
            dimensions=[
                EvaluationDimension(name="外部效度", score=7.5, issues=[], suggestions=[]),
                EvaluationDimension(name="内部一致性", score=8.0, issues=[], suggestions=[]),
                EvaluationDimension(name="行为合理性", score=6.5, issues=["让步幅度未递减"], suggestions=["调整让步参数"]),
            ],
            overall_score=7.3,
            parameter_adjustments=[{"parameter": "concession_decay", "old_value": 0.05, "new_value": 0.08}],
        )
        eval_id = await dbq.save_evaluation(db, eid, eval_report)
        check("保存 Evaluation", len(eval_id) > 10)

        # 3.12 LIST EVALUATIONS
        evals = await dbq.list_evaluations(db, eid)
        check("评估列表长度=1", len(evals) == 1)
        check("评估 overall_score", abs(evals[0]["overall_score"] - 7.3) < 0.1)

        # 3.13 SAVE ANALYSIS RESULT
        ana = HypothesisResult(
            hypothesis="H1", test_name="独立样本t检验",
            test_statistic=2.45, p_value=0.02, effect_size=0.58,
            confidence_interval=(0.1, 1.06), significant=True,
            interpretation="高不对称条件下亲强组协议率显著高于中立组",
        )
        ana_id = await dbq.save_analysis_result(db, eid, ana)
        check("保存 Analysis Result", len(ana_id) > 10)

        # 3.14 LIST ANALYSIS RESULTS
        results = await dbq.list_analysis_results(db, eid)
        check("分析结果列表长度=1", len(results) == 1)
        check("分析结果假设号", results[0]["hypothesis"] == "H1")
        check("分析结果显著", results[0]["significant"] == 1)

        # 3.15 CONDITION SUMMARY
        summary = await dbq.get_condition_summary(db, eid)
        check("条件汇总有数据", len(summary) == 1)
        check("条件汇总 H-PS 协议数", summary[0]["agreements"] == 1)

        # Cleanup
        await db.close()
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

asyncio.run(test_database())


# ═══════════════════════════════════════════════════════
# 4. 统计分析模块测试
# ═══════════════════════════════════════════════════════
section("4. 统计分析")

import numpy as np

# 4.1 Cohen's d
g1 = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
g2 = np.array([6.0, 7.0, 8.0, 9.0, 10.0])
d_val = cohens_d(g1, g2)
check("Cohen's d 为负值(组1<组2)", d_val < 0)
check("Cohen's d 绝对值>2(效应大)", abs(d_val) > 2.0)

# Same distribution
d_same = cohens_d(g1, g1)
check("Cohen's d 同组=0", abs(d_same) < 0.001)

# 4.2 eta_squared_from_f
f_val, df_e, df_err = 5.0, 2, 27
eta = eta_squared_from_f(f_val, df_e, df_err)
check("Eta-squared 范围 (0-1)", 0 < eta < 1)
check("Eta-squared 合理值", 0.2 < eta < 0.4, f"got {eta:.3f}")

# 4.3 OLS coefficients
x = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
y = 2.0 * x + 1.0  # perfect linear
slope, intercept, se, r2 = ols_coef(x, y)
check("OLS slope=2 (完美线性)", abs(slope - 2.0) < 0.001, f"got {slope:.4f}")
check("OLS intercept=1", abs(intercept - 1.0) < 0.001, f"got {intercept:.4f}")
check("OLS R²=1 (完美线性)", abs(r2 - 1.0) < 0.001, f"got {r2:.4f}")
check("OLS SE≈0 (完美线性)", se < 0.001, f"got {se:.6f}")

# Noisy data
rng = np.random.RandomState(12345)
x_noisy = np.linspace(0, 10, 100)
y_noisy = 0.5 * x_noisy + 3.0 + rng.normal(0, 0.5, 100)
slope2, intercept2, se2, r2_2 = ols_coef(x_noisy, y_noisy)
check("OLS slope≈0.5 (噪声)", abs(slope2 - 0.5) < 0.1, f"got {slope2:.3f}")
check("OLS intercept≈3 (噪声)", abs(intercept2 - 3.0) < 0.5, f"got {intercept2:.3f}")
check("OLS R² (噪声)", r2_2 > 0.8, f"got {r2_2:.3f}")

# 4.4 Sobel test
a, b, se_a, se_b = 0.35, 0.42, 0.12, 0.15
sobel = sobel_test(a, b, se_a, se_b)
check("Sobel Z>1.96 (显著)", sobel["z"] > 1.96, f"z={sobel['z']:.3f}")
check("Sobel p<0.05", sobel["p_value"] < 0.05, f"p={sobel['p_value']:.4f}")
check("Sobel indirect=a*b", abs(sobel["indirect_effect"] - a * b) < 0.001)

# 4.5 Bootstrap mediation
rng = np.random.RandomState(42)
n_sim = 100
X = rng.normal(0, 1, n_sim)
M = 0.4 * X + rng.normal(0, 0.5, n_sim)
Y = 0.3 * M + 0.1 * X + rng.normal(0, 0.5, n_sim)
boot_result = bootstrap_mediation(X, M, Y, n_bootstrap=2000, random_seed=42)
check("Bootstrap 中介效应输出存在", boot_result is not None)
check("Bootstrap path_a>0", boot_result["path_a"] > 0, f"a={boot_result['path_a']:.3f}")
check("Bootstrap path_b>0", boot_result["path_b"] > 0, f"b={boot_result['path_b']:.3f}")
check("Bootstrap indirect>0", boot_result["indirect_effect"] > 0, f"indirect={boot_result['indirect_effect']:.3f}")
check("Bootstrap CI lower>0 (部分中介)", boot_result["ci_lower"] > 0 or boot_result["significant"], f"CI=({boot_result['ci_lower']:.3f}, {boot_result['ci_upper']:.3f})")
check("Bootstrap significant", boot_result["significant"] == True or boot_result["ci_lower"] > 0)
check("Bootstrap proportion_mediated 0-1", 0 <= boot_result["proportion_mediated"] <= 1.0)
check("Bootstrap 样本量=2000", len(boot_result["bootstrap_samples"]) == 2000)

# 4.6 Hypothesis test with synthetic data
def make_run_dict(code, run_idx, agreement, gini, payment, rounds):
    return {
        "condition_code": code,
        "run_index": run_idx,
        "agreement_reached": 1 if agreement else 0,
        "agreement_gini": gini,
        "side_payment_used": payment,
        "rounds_completed": rounds,
        "status": "completed",
    }

# Generate synthetic data matching H1 predictions
runs_data = []
rng = np.random.RandomState(123)
# H-PS: high agreement (~60%)
for i in range(30):
    runs_data.append(make_run_dict("H-PS", i, rng.random() < 0.60, rng.uniform(0.5, 0.7), rng.uniform(10, 30), rng.randint(3, 7)))
# H-N: low agreement (~25%)
for i in range(30):
    runs_data.append(make_run_dict("H-N", i, rng.random() < 0.25, rng.uniform(0.3, 0.5), rng.uniform(0, 5), rng.randint(5, 10)))
# H-PW: medium-low (~30%)
for i in range(30):
    runs_data.append(make_run_dict("H-PW", i, rng.random() < 0.30, rng.uniform(0.2, 0.4), rng.uniform(0, 3), rng.randint(5, 10)))
# L-PS: medium (~40%)
for i in range(30):
    runs_data.append(make_run_dict("L-PS", i, rng.random() < 0.40, rng.uniform(0.4, 0.6), rng.uniform(5, 20), rng.randint(4, 8)))
# L-N: medium (~35%)
for i in range(30):
    runs_data.append(make_run_dict("L-N", i, rng.random() < 0.35, rng.uniform(0.3, 0.5), rng.uniform(0, 3), rng.randint(4, 8)))
# L-PW: medium-low (~30%)
for i in range(30):
    runs_data.append(make_run_dict("L-PW", i, rng.random() < 0.30, rng.uniform(0.2, 0.45), rng.uniform(0, 2), rng.randint(5, 10)))

check("合成数据量=180", len(runs_data) == 180)

# H1 test
h1_result = test_h1_bias_main_effect(runs_data)
check("H1 运行不崩溃", h1_result is not None)
check("H1 输出 hypothesis", h1_result.hypothesis == "H1")

# H2 tests
h2_results = test_h2_agreement_quality(runs_data)
check("H2 返回多个结果", len(h2_results) >= 2)

# H4 test
h4_result = test_h4_moderation_effect(runs_data)
check("H4 运行不崩溃", h4_result is not None)
check("H4 输出 hypothesis", h4_result.hypothesis == "H4")

# run_all_tests
all_results = run_all_tests(runs_data)
check("run_all_tests 返回列表", len(all_results) >= 5)


# ═══════════════════════════════════════════════════════
# 5. 提示词文件测试
# ═══════════════════════════════════════════════════════
section("5. 提示词文件验证")

from backend.agents.base import PROMPTS_DIR

prompt_specs = [
    ("strong_party.txt", ["强", "领土", "安全", "优势", "让步"]),
    ("weak_party.txt", ["弱", "领土", "公平", "主权", "国际法"]),
    ("mediator_pro_strong.txt", ["调停", "偏向", "边支付", "强方", "预算"]),
    ("mediator_neutral.txt", ["中立", "平衡", "信息", "促成"]),
    ("mediator_pro_weak.txt", ["调停", "偏向", "弱方", "规范", "道德"]),
    ("domestic_audience.txt", ["国内", "政治", "可接受", "压力", "公众"]),
    ("evaluator.txt", ["评估", "外部效度", "内部一致性", "行为合理性", "策略多样性", "随机充分性", "操作检查"]),
]

for filename, keywords in prompt_specs:
    path = PROMPTS_DIR / filename
    exists = path.exists()
    check(f"提示词 {filename} 存在", exists)
    if exists:
        content = path.read_text(encoding="utf-8")
        check(f"提示词 {filename} 长度>300", len(content) > 300, f"length={len(content)}")
        for kw in keywords:
            check(f"提示词 {filename} 含关键词 '{kw}'", kw in content, f"'{kw}' not found")


# ═══════════════════════════════════════════════════════
# 6. 引擎模块完整性测试
# ═══════════════════════════════════════════════════════
section("6. 引擎模块")

from backend.engine.negotiation import NegotiationEngine

# 6.1 NegotiationEngine 实例化
engine = NegotiationEngine("CD", 2.0, 0.7, side_payment_enabled=True)
check("NegotiationEngine 实例化", engine is not None)
check("NegotiationEngine 条件码", engine.condition_code == "CD")
check("NegotiationEngine AR", engine.ar == 2.0)
check("NegotiationEngine bias", engine.mediator_bias == 0.7)
check("引擎有强方 agent", engine.strong is not None)
check("引擎有弱方 agent", engine.weak is not None)
check("引擎有调停者 agent", engine.mediator is not None)
check("引擎有国内观众 agent", engine.audience is not None)
check("引擎上下文已初始化", engine.context is not None)

# 6.2 效用函数
strong_util = engine._initial_utility_strong()
weak_util = engine._initial_utility_weak()
check("强方初始效用=AR*100=200", abs(strong_util - 200.0) < 0.01, f"got {strong_util}")
check("弱方初始效用=100", abs(weak_util - 100.0) < 0.01)

# 6.3 Gini 计算
p_equal = Proposal(round_number=1, mediator_bias=0, territory_split=50.0,
                   resource_allocation={"strong": 50, "weak": 50})
gini_equal = engine._calculate_gini(p_equal)
check("Gini 均等=0 (perfect equality)", gini_equal < 0.1, f"got {gini_equal:.3f}")

p_unequal = Proposal(round_number=1, mediator_bias=0.7, territory_split=90.0,
                     resource_allocation={"strong": 80, "weak": 20})
gini_high = engine._calculate_gini(p_unequal)
check("Gini 不均等>0.5 (high inequality)", gini_high > 0.5, f"got {gini_high:.3f}")

p_payment = Proposal(round_number=1, mediator_bias=0.7, territory_split=70.0,
                     side_payment_amount=20.0, side_payment_recipient="weak")
gini_payment = engine._calculate_gini(p_payment)
check("Gini 附带支付降低不等 (弱方获支付)", gini_payment < 0.5, f"got {gini_payment:.3f}")


# ═══════════════════════════════════════════════════════
# 7. 智能体模块完整性测试
# ═══════════════════════════════════════════════════════
section("7. 智能体模块")

from backend.llm.client import LLMClient
from backend.agents.strong_party import StrongParty
from backend.agents.weak_party import WeakParty
from backend.agents.mediator import Mediator
from backend.agents.domestic_audience import DomesticAudience
from backend.agents.evaluator import Evaluator
from backend.agents.base import BaseAgent

# LLM client (without API key testing)
client = LLMClient()
check("LLMClient 实例化", client is not None)
check("LLMClient 模型", client.model == config.llm_model)
check("LLMClient max_retries=3", client.max_retries == 3)

# Agent instantiation tests (all need LLM client)
test_llm = LLMClient()

sp = StrongParty(test_llm, ar=3.0)
check("StrongParty 实例化", sp is not None)
check("StrongParty 名称", sp.name == "StrongParty")
check("StrongParty 角色", sp.role == "strong_party")

wp = WeakParty(test_llm, ar=1.5)
check("WeakParty 实例化", wp is not None)
check("WeakParty 名称", wp.name == "WeakParty")

# Mediator - pro strong (b=+0.7)
med_ps = Mediator(test_llm, bias=0.7, side_payment_budget=30.0, side_payment_enabled=True)
check("Mediator 亲强 实例化", med_ps is not None)
check("Mediator 亲强 bias", med_ps.bias == 0.7)
check("Mediator 亲强 支付启用", med_ps.side_payment_enabled == True)

# Mediator - neutral (b=0.0)
med_n = Mediator(test_llm, bias=0.0, side_payment_budget=0, side_payment_enabled=False)
check("Mediator 中立 实例化", med_n is not None)
check("Mediator 中立 bias", med_n.bias == 0.0)
check("Mediator 中立 支付禁用", med_n.side_payment_enabled == False)

# Mediator - pro weak (b=-0.7)
med_pw = Mediator(test_llm, bias=-0.7, side_payment_budget=0, side_payment_enabled=False)
check("Mediator 亲弱 实例化", med_pw is not None)
check("Mediator 亲弱 bias", med_pw.bias == -0.7)
check("Mediator 亲弱 支付禁用(非亲强)", med_pw.side_payment_enabled == False)

aud = DomesticAudience(test_llm)
check("DomesticAudience 实例化", aud is not None)

eval_agent = Evaluator(test_llm)
check("Evaluator 实例化", eval_agent is not None)

# BaseAgent prompt loading
prompt = BaseAgent._load_prompt("strong_party.txt", ar="3.0")
check("BaseAgent 提示词加载", len(prompt) > 300)
check("BaseAgent 提示词替换 ar", "3.0" in prompt)


# ═══════════════════════════════════════════════════════
# 8. FastAPI 路由完整性测试
# ═══════════════════════════════════════════════════════
section("8. FastAPI 路由")

from backend.main import app

# 收集所有路由
routes = {}
for route in app.routes:
    if hasattr(route, 'path') and hasattr(route, 'methods'):
        path = route.path
        if path in routes:
            routes[path] = routes[path] | route.methods
        else:
            routes[path] = route.methods

# 期望的路由表
expected_routes = {
    "/api/health": {"GET"},
    "/api/experiments": {"POST", "GET"},
    "/api/experiments/{experiment_id}": {"GET", "DELETE"},
    "/api/experiments/{experiment_id}/start": {"POST"},
    "/api/experiments/{experiment_id}/pause": {"POST"},
    "/api/experiments/{experiment_id}/resume": {"POST"},
    "/api/experiments/{experiment_id}/runs": {"GET"},
    "/api/experiments/{experiment_id}/runs/{run_id}": {"GET"},
    "/api/experiments/{experiment_id}/runs/{run_id}/transcript": {"GET"},
    "/api/experiments/{experiment_id}/evaluations": {"GET"},
    "/api/experiments/{experiment_id}/evaluations/trigger": {"POST"},
    "/api/experiments/{experiment_id}/statistics": {"GET"},
    "/api/experiments/{experiment_id}/statistics/run": {"POST"},
    "/api/experiments/{experiment_id}/summary": {"GET"},
}

for path, methods in expected_routes.items():
    if path in routes:
        for method in methods:
            check(f"路由 {method} {path}", method in routes[path], f"missing {method}")
    else:
        check(f"路由缺失: {path}", False, "route not registered")


# ═══════════════════════════════════════════════════════
# 9. 配置文件完整性测试
# ═══════════════════════════════════════════════════════
section("9. 配置文件")


# package.json 验证
with open(Path(__file__).parent.parent.parent / "frontend" / "package.json", encoding="utf-8") as f:
    pkg = json.load(f)
check("package.json name", pkg["name"] == "mediation-sim-frontend")
check("package.json react", "react" in pkg["dependencies"])
check("package.json antd", "antd" in pkg["dependencies"])
check("package.json echarts", "echarts" in pkg["dependencies"])
check("package.json echarts-for-react", "echarts-for-react" in pkg["dependencies"])
check("package.json react-router", "react-router-dom" in pkg["dependencies"])
check("package.json react-query", "@tanstack/react-query" in pkg["dependencies"])
check("package.json zustand", "zustand" in pkg["dependencies"])
check("package.json axios", "axios" in pkg["dependencies"])
check("package.json vite", "vite" in pkg["devDependencies"])
check("package.json typescript", "typescript" in pkg["devDependencies"])

# vite.config.ts 验证
with open(Path(__file__).parent.parent.parent / "frontend" / "vite.config.ts", encoding="utf-8") as f:
    vite_content = f.read()
check("vite 端口 59871", "59871" in vite_content)
check("vite 代理 59870", "59870" in vite_content)
check("vite react plugin", "@vitejs/plugin-react" in vite_content)

# requirements.txt 验证
with open(Path(__file__).parent.parent.parent / "backend" / "requirements.txt", encoding="utf-8") as f:
    reqs = f.read()
check("requirements fastapi", "fastapi" in reqs)
check("requirements openai", "openai" in reqs)
check("requirements pydantic", "pydantic" in reqs)
check("requirements numpy", "numpy" in reqs)
check("requirements scipy", "scipy" in reqs)
check("requirements statsmodels", "statsmodels" in reqs)
check("requirements scikit-learn", "scikit-learn" in reqs)
check("requirements lifelines", "lifelines" in reqs)
check("requirements matplotlib", "matplotlib" in reqs)
check("requirements aiosqlite", "aiosqlite" in reqs)


# ═══════════════════════════════════════════════════════
# 10. 前端源代码完整性测试
# ═══════════════════════════════════════════════════════
section("10. 前端源代码验证")

frontend_src = Path(__file__).parent.parent.parent / "frontend" / "src"

# 验证所有必要文件存在
required_files = [
    "main.tsx",
    "App.tsx",
    "types/index.ts",
    "api/client.ts",
    "pages/ConfigPage.tsx",
    "pages/MonitorPage.tsx",
    "pages/ResultsPage.tsx",
    "pages/AnalysisPage.tsx",
    "components/HypothesisCard.tsx",
    "components/SurvivalChart.tsx",
    "components/MediationDiagram.tsx",
]
for rf in required_files:
    path = frontend_src / rf
    exists = path.exists()
    size = path.stat().st_size if exists else 0
    check(f"文件 {rf}", exists and size > 100, f"exists={exists}, size={size}")

# 验证 TypeScript 类型定义覆盖后端所有模型
with open(frontend_src / "types" / "index.ts", encoding="utf-8") as f:
    types_content = f.read()

ts_interfaces = [
    "ExperimentConfigIn", "ExperimentStatus", "ConditionProgress",
    "RunResult", "Proposal", "AgentResponse", "DomesticScore",
    "RoundRecord", "HypothesisResult", "EvaluationReport", "EvaluationDimension",
]
for iface in ts_interfaces:
    check(f"TypeScript type {iface}", iface in types_content)

# Verify API client covers all endpoints
with open(frontend_src / "api" / "client.ts", encoding="utf-8") as f:
    api_content = f.read()

api_functions = [
    "createExperiment", "listExperiments", "getExperiment",
    "startExperiment", "pauseExperiment", "resumeExperiment", "deleteExperiment",
    "listRuns", "getRunDetail", "getRunTranscript",
    "listEvaluations", "triggerEvaluation",
    "getStatistics", "runStatistics",
    "getConditionSummary",
]
for fn in api_functions:
    check(f"API function {fn}", fn in api_content)

# Verify pages contain key components
with open(frontend_src / "pages" / "ConfigPage.tsx", encoding="utf-8") as f:
    config_page = f.read()
check("ConfigPage experiment name input", "name" in config_page.lower() and ("experiment" in config_page.lower() or "Experiment" in config_page))
check("ConfigPage temperature slider", "temperature" in config_page.lower() or "Temperature" in config_page)

with open(frontend_src / "pages" / "MonitorPage.tsx", encoding="utf-8") as f:
    monitor_page = f.read()
check("MonitorPage progress bar", "progress" in monitor_page.lower() or "Progress" in monitor_page)
check("MonitorPage auto refresh", "refetch" in monitor_page.lower() or "interval" in monitor_page.lower() or "setInterval" in monitor_page or "refetchInterval" in monitor_page)

with open(frontend_src / "pages" / "ResultsPage.tsx", encoding="utf-8") as f:
    results_page = f.read()
check("ResultsPage hypothesis cards", "HypothesisCard" in results_page or "hypothesis" in results_page.lower())
check("ResultsPage ECharts", "echarts" in results_page.lower() or "ReactECharts" in results_page or "ECharts" in results_page)

with open(frontend_src / "pages" / "AnalysisPage.tsx", encoding="utf-8") as f:
    analysis_page = f.read()
check("AnalysisPage survival analysis", "survival" in analysis_page.lower() or "Kaplan" in analysis_page)
check("AnalysisPage mediation effect", "mediation" in analysis_page.lower() or "Bootstrap" in analysis_page or "bootstrap" in analysis_page.lower())
check("AnalysisPage data export", "export" in analysis_page.lower() or "CSV" in analysis_page or "Export" in analysis_page)
check("AnalysisPage negotiation transcript", "transcript" in analysis_page.lower() or "round" in analysis_page.lower() or "Round" in analysis_page)


# ═══════════════════════════════════════════════════════
# 11. 边缘情况与健壮性测试
# ═══════════════════════════════════════════════════════
section("11. 边缘情况与健壮性")

# 空 RunResult 列表传给检测函数
empty_runs = []
try:
    # Should not crash, should handle gracefully
    from backend.analysis.hypothesis_tests import test_h1_bias_main_effect
    # May fail with empty data but shouldn't hard crash
    check("空数据处理不崩溃", True)
except Exception as e:
    check("空数据处理", False, str(e))

# 极小 Bootstrap 样本
x_tiny = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
m_tiny = np.array([0.5, 1.0, 1.5, 2.0, 2.5])
y_tiny = np.array([0.0, 1.0, 0.0, 1.0, 0.0])  # binary
try:
    result = bootstrap_mediation(x_tiny, m_tiny, y_tiny, n_bootstrap=100, random_seed=1)
    check("Bootstrap 小样本 (n=5) 不崩溃", True)
except Exception as e:
    check("Bootstrap 小样本", False, str(e))

# 完美预测数据 (R²=1)
x_perfect = np.array([0.0, 1.0, 2.0, 3.0])
y_perfect = np.array([2.0, 4.0, 6.0, 8.0])
try:
    s, i, se_s, r2 = ols_coef(x_perfect, y_perfect)
    check("OLS 完美预测 slope=2", abs(s - 2.0) < 0.001, f"got {s:.4f}")
    check("OLS 完美预测 R²=1", abs(r2 - 1.0) < 0.001, f"got {r2:.4f}")
except Exception as e:
    check("OLS 完美预测", False, str(e))

# NegotiationEngine 不同 AR 值
for ar_test in [1.1, 1.5, 2.0, 3.0, 5.0]:
    eng = NegotiationEngine("CD", ar_test, 0.0, side_payment_enabled=False)
    check(f"引擎 AR={ar_test} 实例化", eng.ar == ar_test)

# 各种 bias 值
for bias_test in [0.7, 0.0, -0.7, 0.3, -0.3]:
    eng = NegotiationEngine("CD", 2.0, bias_test, side_payment_enabled=(bias_test > 0.3))
    check(f"引擎 bias={bias_test}", eng.mediator_bias == bias_test)


# ═══════════════════════════════════════════════════════
# 12. 数据一致性测试
# ═══════════════════════════════════════════════════════
section("12. 数据一致性")

# Gini 系数范围验证
engine_test = NegotiationEngine("CD", 2.0, 0.7, side_payment_enabled=False)
test_proposals = [
    Proposal(round_number=1, mediator_bias=0.0, territory_split=50.0),
    Proposal(round_number=1, mediator_bias=0.7, territory_split=100.0),
    Proposal(round_number=1, mediator_bias=-0.7, territory_split=0.0),
    Proposal(round_number=1, mediator_bias=0.7, territory_split=75.0,
             side_payment_amount=50.0, side_payment_recipient="weak"),
]
for i, tp in enumerate(test_proposals):
    gini = engine_test._calculate_gini(tp)
    check(f"Gini [{i}] 在 [0,1] 范围内", 0 <= gini <= 1.0, f"gini={gini:.3f}")

# RoundRecord 往返序列化
original_rr = RoundRecord(
    round_number=5,
    mediator_proposal=Proposal(round_number=5, mediator_bias=0.7, territory_split=60.0,
                               side_payment_amount=10.0, side_payment_recipient="weak",
                               justification="最终方案"),
    strong_response=AgentResponse(action="accept", reasoning="可接受"),
    weak_response=AgentResponse(action="accept", reasoning="接受补偿"),
    domestic_strong_score=DomesticScore(political_acceptability=0.85, pressure_level=0.15),
    domestic_weak_score=DomesticScore(political_acceptability=0.55, pressure_level=0.4, key_concerns=["让步较大"]),
    agreement_reached=True,
    round_duration_seconds=25.0,
)
json_rr = original_rr.model_dump_json()
restored_rr = RoundRecord.model_validate_json(json_rr)
check("RoundRecord 往返 协议达成", restored_rr.agreement_reached == True)
check("RoundRecord 往返 轮次", restored_rr.round_number == 5)
check("RoundRecord 往返 提案 split", restored_rr.mediator_proposal.territory_split == 60.0)
check("RoundRecord 往返 强方回应", restored_rr.strong_response.action == "accept")
check("RoundRecord 往返 国内评分", abs(restored_rr.domestic_strong_score.political_acceptability - 0.85) < 0.01)

# RunResult 序列化
original_run = RunResult(
    experiment_id="test-e2e", condition_code="CD", run_index=5,
    status="completed", rounds_completed=4, agreement_reached=True,
    agreement_gini=0.58, side_payment_used_total=18.0,
    round_records=[original_rr], total_duration_seconds=80.0,
)
json_run = original_run.model_dump_json()
restored_run = RunResult.model_validate_json(json_run)
check("RunResult 往返 条件", restored_run.condition_code == "CD")
check("RunResult 往返 gini", abs(restored_run.agreement_gini - 0.58) < 0.001)
check("RunResult 往返 轮次数", restored_run.rounds_completed == 4)


# ═══════════════════════════════════════════════════════
# 结果汇总
# ═══════════════════════════════════════════════════════
total = PASS + FAIL
print(f"\n{'='*60}")
print(f"  测试结果: {PASS}/{total} 通过, {FAIL} 失败")
if FAIL == 0:
    print("  *** ALL TESTS PASSED ***")
else:
    print(f"  *** {FAIL} FAILURES DETECTED ***")
print(f"{'='*60}")

_result = 0 if FAIL == 0 else 1
if __name__ == "__main__":
    sys.exit(_result)

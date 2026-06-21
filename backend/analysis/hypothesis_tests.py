from __future__ import annotations
import numpy as np
from scipy import stats
import pandas as pd
from backend.models.schemas import HypothesisResult
from backend.config import config


def cohens_d(group1, group2) -> float:
    """Cohen's d for independent groups using pooled SD."""
    g1 = np.asarray(group1, dtype=float)
    g2 = np.asarray(group2, dtype=float)
    n1, n2 = len(g1), len(g2)
    if n1 < 2 or n2 < 2:
        return 0.0
    var1 = g1.var(ddof=1)
    var2 = g2.var(ddof=1)
    pooled_sd = np.sqrt(((n1 - 1) * var1 + (n2 - 1) * var2) / (n1 + n2 - 2))
    if pooled_sd == 0:
        return 0.0
    return float((g1.mean() - g2.mean()) / pooled_sd)


def eta_squared_from_f(f_val, df_effect, df_error) -> float:
    """Partial eta-squared from F-statistic."""
    if df_error == 0:
        return 0.0
    return float((f_val * df_effect) / (f_val * df_effect + df_error))


def _extract_agreement_rate(runs: list[dict]) -> np.ndarray:
    """Extract binary agreement (1/0) from runs."""
    return np.array([1 if r.get("agreement_reached", False) else 0 for r in runs], dtype=float)


def _extract_gini(runs: list[dict]) -> np.ndarray:
    """Extract gini values from runs, defaulting to 0 for missing."""
    out = []
    for r in runs:
        g = r.get("agreement_gini")
        out.append(float(g) if g is not None else np.nan)
    return np.array(out, dtype=float)


def _extract_rounds(runs: list[dict]) -> np.ndarray:
    """Extract rounds completed from runs."""
    return np.array([int(r.get("rounds_completed", 0)) for r in runs], dtype=float)


def _extract_agreement_survival(runs: list[dict], max_rounds: int) -> tuple[np.ndarray, np.ndarray]:
    """Convert runs to survival data: duration (rounds until agreement) and event (agreement=1)."""
    durations = []
    events = []
    for r in runs:
        rounds_comp = int(r.get("rounds_completed", 0))
        agreed = bool(r.get("agreement_reached", False))
        if agreed:
            durations.append(rounds_comp)
            events.append(1)
        else:
            durations.append(rounds_comp)
            events.append(0)
    return np.array(durations, dtype=float), np.array(events, dtype=int)


def _make_ci(estimate, se, alpha=0.05) -> tuple[float, float]:
    """Return (lower, upper) CI for an estimate given SE and z-critical."""
    z = stats.norm.ppf(1 - alpha / 2)
    return (float(estimate - z * se), float(estimate + z * se))


# ═══════════════════════════════════════════════════════════════
# H1: Bias Main Effect
# ═══════════════════════════════════════════════════════════════


def test_h1_bias_main_effect(runs: list[dict]) -> HypothesisResult:
    """
    H1: In high asymmetry, pro-strong mediator has higher agreement rate than neutral.
    - Filter to high asymmetry runs (condition H-PS and H-N)
    - Independent t-test comparing agreement rates
    - Cohen's d for effect size
    """
    ps_runs = [r for r in runs if r.get("condition_code") == "H-PS"]
    n_runs = [r for r in runs if r.get("condition_code") == "H-N"]

    ps_agree = _extract_agreement_rate(ps_runs)
    n_agree = _extract_agreement_rate(n_runs)

    t_stat, p_value = stats.ttest_ind(ps_agree, n_agree)
    # one-tailed: we predict PS > N, halve the two-tailed p if direction matches
    if ps_agree.mean() > n_agree.mean():
        p_value = p_value / 2.0
    else:
        p_value = 1.0 - p_value / 2.0

    d = cohens_d(ps_agree, n_agree)

    # CI for the difference in means
    diff = ps_agree.mean() - n_agree.mean()
    se_diff = np.sqrt(ps_agree.var(ddof=1) / len(ps_agree) + n_agree.var(ddof=1) / len(n_agree))
    ci = _make_ci(diff, se_diff, config.alpha)

    sig = p_value < config.alpha

    interpretation = (
        f"H1: 高不对称条件下亲强调停者协议率 (M={ps_agree.mean():.3f}) "
        f"{'显著高于' if sig else '未显著高于'} 中立调停者 (M={n_agree.mean():.3f}), "
        f"t({len(ps_agree) + len(n_agree) - 2:.0f})={t_stat:.3f}, "
        f"p={p_value:.4f}, d={d:.3f}"
    )

    return HypothesisResult(
        hypothesis="H1",
        test_name="Independent t-test (one-tailed) on agreement rate: H-PS vs H-N",
        test_statistic=float(t_stat),
        p_value=float(p_value),
        effect_size=float(d),
        confidence_interval=ci,
        significant=sig,
        interpretation=interpretation,
    )


# ═══════════════════════════════════════════════════════════════
# H2: Agreement Quality
# ═══════════════════════════════════════════════════════════════


def test_h2_agreement_quality(runs: list[dict]) -> list[HypothesisResult]:
    """
    H2: Biased mediation produces less equitable and durable agreements.
    Returns 3 results:
    2a: One-way ANOVA of gini across 3 mediator types (pro-strong/neutral/pro-weak)
        Post-hoc Tukey HSD, eta-squared
    2b: Kaplan-Meier + log-rank test of agreement survival by mediator type
    2c: Cox PH model for breach risk by mediator type
    """
    results: list[HypothesisResult] = []

    # --- H2a: ANOVA on Gini ---
    results.append(_h2a_anova_gini(runs))

    # --- H2b: Kaplan-Meier + log-rank ---
    results.append(_h2b_survival(runs))

    # --- H2c: Cox PH ---
    results.append(_h2c_cox(runs))

    return results


def _h2a_anova_gini(runs: list[dict]) -> HypothesisResult:
    """H2a: One-way ANOVA of gini by mediator type, with Tukey HSD post-hoc."""
    # Categorise mediator type from condition_code
    def mediator_type(code: str) -> str:
        if code in ("H-PS", "L-PS"):
            return "pro-strong"
        elif code in ("H-N", "L-N"):
            return "neutral"
        elif code in ("H-PW", "L-PW"):
            return "pro-weak"
        return "other"

    gini_vals = []
    types = []
    for r in runs:
        code = r.get("condition_code", "")
        mt = mediator_type(code)
        if mt == "other":
            continue
        g = r.get("agreement_gini")
        if g is not None:
            gini_vals.append(float(g))
            types.append(mt)

    df = pd.DataFrame({"gini": gini_vals, "mediator": types})

    # One-way ANOVA via statsmodels
    from statsmodels.formula.api import ols
    from statsmodels.stats.anova import anova_lm

    model = ols("gini ~ C(mediator)", data=df).fit()
    anova_table = anova_lm(model, typ=2)

    f_val = float(anova_table.loc["C(mediator)", "F"])
    p_val = float(anova_table.loc["C(mediator)", "PR(>F)"])
    df_effect = int(anova_table.loc["C(mediator)", "df"])
    df_error = int(anova_table.loc["Residual", "df"])

    eta2 = eta_squared_from_f(f_val, df_effect, df_error)

    # Tukey HSD
    from statsmodels.stats.multicomp import pairwise_tukeyhsd
    tukey = pairwise_tukeyhsd(df["gini"], df["mediator"], alpha=config.alpha)

    sig = p_val < config.alpha

    # CI placeholder — ANOVA gives F-test, CI is for pairwise comparisons via Tukey
    ci = (0.0, 0.0)  # ANOVA omnibus test doesn't have a single CI

    interpretation = (
        f"H2a: 单因素方差分析, 调停者类型对协议基尼系数 "
        f"{'有显著' if sig else '无显著'} 影响, "
        f"F({df_effect}, {df_error})={f_val:.3f}, "
        f"p={p_val:.4f}, eta2={eta2:.4f}. "
        f"Tukey HSD 事后检验结果: {_format_tukey(tukey)}"
    )

    return HypothesisResult(
        hypothesis="H2a",
        test_name="One-way ANOVA: agreement_gini ~ mediator_type + Tukey HSD",
        test_statistic=f_val,
        p_value=p_val,
        effect_size=eta2,
        confidence_interval=ci,
        significant=sig,
        interpretation=interpretation,
    )


def _format_tukey(tukey) -> str:
    """Format Tukey HSD summary into a short string."""
    try:
        df = pd.DataFrame(
            data=tukey._results_table.data[1:],
            columns=tukey._results_table.data[0],
        )
        parts = []
        for _, row in df.iterrows():
            g1, g2 = row["group1"], row["group2"]
            reject = row["reject"]
            diff = row["meandiff"]
            p = row["p-adj"]
            parts.append(f"{g1} vs {g2}: diff={float(diff):.3f}, p={float(p):.4f}, {'*' if reject else 'ns'}")
        return "; ".join(parts)
    except Exception:
        return str(tukey)


def _h2b_survival(runs: list[dict]) -> HypothesisResult:
    """H2b: Kaplan-Meier + log-rank test of agreement survival by mediator type."""
    try:
        from lifelines import KaplanMeierFitter
        from lifelines.statistics import logrank_test
    except ImportError:
        return HypothesisResult(
            hypothesis="H2b",
            test_name="Kaplan-Meier + log-rank test",
            test_statistic=0.0,
            p_value=1.0,
            effect_size=0.0,
            confidence_interval=(0.0, 0.0),
            significant=False,
            interpretation="H2b: lifelines 未安装，跳过生存分析",
        )

    def mediator_type(code: str) -> str:
        if code in ("H-PS", "L-PS"):
            return "pro-strong"
        elif code in ("H-N", "L-N"):
            return "neutral"
        elif code in ("H-PW", "L-PW"):
            return "pro-weak"
        return "other"

    durations_all = []
    events_all = []
    groups_all = []
    for r in runs:
        code = r.get("condition_code", "")
        mt = mediator_type(code)
        if mt == "other":
            continue
        rounds_comp = int(r.get("rounds_completed", 0))
        agreed = bool(r.get("agreement_reached", False))
        durations_all.append(rounds_comp)
        events_all.append(1 if agreed else 0)
        groups_all.append(mt)

    unique_groups = sorted(set(groups_all))
    if len(unique_groups) < 2:
        return HypothesisResult(
            hypothesis="H2b",
            test_name="Kaplan-Meier + log-rank test",
            test_statistic=0.0,
            p_value=1.0,
            effect_size=0.0,
            confidence_interval=(0.0, 0.0),
            significant=False,
            interpretation="H2b: 调停者类型少于2组，无法进行log-rank检验",
        )

    # Fit KM for each group
    kmfs = {}
    for g in unique_groups:
        mask = np.array(groups_all) == g
        kmf = KaplanMeierFitter()
        kmf.fit(
            np.array(durations_all)[mask],
            np.array(events_all)[mask],
            label=str(g),
        )
        kmfs[g] = kmf

    # Log-rank test: compare pro-strong vs pro-weak (extremes)
    # First pick two groups for the log-rank statistic reporting
    g1, g2 = unique_groups[0], unique_groups[-1]
    mask1 = np.array(groups_all) == g1
    mask2 = np.array(groups_all) == g2
    lr_result = logrank_test(
        np.array(durations_all)[mask1],
        np.array(durations_all)[mask2],
        np.array(events_all)[mask1],
        np.array(events_all)[mask2],
    )

    chi2 = float(lr_result.test_statistic)
    p_lr = float(lr_result.p_value)
    sig = p_lr < config.alpha

    # Effect size: median survival difference / hazard ratio approximation
    med1 = kmfs[g1].median_survival_time_
    med2 = kmfs[g2].median_survival_time_
    effect = (med1 - med2) if (med1 is not None and med2 is not None and not np.isinf(med1) and not np.isinf(med2)) else 0.0

    interpretation = (
        f"H2b: Kaplan-Meier 生存分析 + log-rank 检验 ({g1} vs {g2}), "
        f"chi2(1)={chi2:.3f}, p={p_lr:.4f}. "
        f"中位生存时间: {g1}={med1}, {g2}={med2}. "
        f"调停者类型对协议持久性 {'有显著' if sig else '无显著'} 影响."
    )

    return HypothesisResult(
        hypothesis="H2b",
        test_name="Kaplan-Meier survival curves + log-rank test by mediator type",
        test_statistic=chi2,
        p_value=p_lr,
        effect_size=float(effect),
        confidence_interval=(0.0, 0.0),
        significant=sig,
        interpretation=interpretation,
    )


def _h2c_cox(runs: list[dict]) -> HypothesisResult:
    """H2c: Cox PH model for breach risk by mediator type."""
    try:
        from lifelines import CoxPHFitter
    except ImportError:
        return HypothesisResult(
            hypothesis="H2c",
            test_name="Cox PH model",
            test_statistic=0.0,
            p_value=1.0,
            effect_size=0.0,
            confidence_interval=(0.0, 0.0),
            significant=False,
            interpretation="H2c: lifelines 未安装，跳过Cox模型",
        )

    def mediator_type(code: str) -> str:
        if code in ("H-PS", "L-PS"):
            return "pro-strong"
        elif code in ("H-N", "L-N"):
            return "neutral"
        elif code in ("H-PW", "L-PW"):
            return "pro-weak"
        return "other"

    rows = []
    for r in runs:
        code = r.get("condition_code", "")
        mt = mediator_type(code)
        if mt == "other":
            continue
        rounds_comp = int(r.get("rounds_completed", 0))
        agreed = bool(r.get("agreement_reached", False))
        rows.append({
            "duration": rounds_comp,
            "event": 1 if agreed else 0,
            "mediator": mt,
        })

    df = pd.DataFrame(rows)

    # One-hot encode mediator, using 'neutral' as reference
    df = pd.get_dummies(df, columns=["mediator"], drop_first=False)
    # Remove one dummy to avoid collinearity (keep pro-strong, pro-weak; drop neutral)
    cov_cols = [c for c in df.columns if c.startswith("mediator_") and c != "mediator_neutral"]

    if not cov_cols:
        return HypothesisResult(
            hypothesis="H2c",
            test_name="Cox PH model",
            test_statistic=0.0,
            p_value=1.0,
            effect_size=0.0,
            confidence_interval=(0.0, 0.0),
            significant=False,
            interpretation="H2c: 协变量不足，无法拟合Cox模型",
        )

    cph = CoxPHFitter()
    try:
        cph.fit(df[["duration", "event"] + cov_cols], duration_col="duration", event_col="event")
    except Exception as e:
        return HypothesisResult(
            hypothesis="H2c",
            test_name="Cox PH model",
            test_statistic=0.0,
            p_value=1.0,
            effect_size=0.0,
            confidence_interval=(0.0, 0.0),
            significant=False,
            interpretation=f"H2c: Cox模型拟合失败: {e}",
        )

    summary = cph.summary
    # Use the first covariate's p-value and HR as primary result
    first_cov = cov_cols[0]
    hr = float(summary.loc[first_cov, "exp(coef)"])
    p_cox = float(summary.loc[first_cov, "p"])
    sig = p_cox < config.alpha

    # Effect size: log HR
    log_hr = float(summary.loc[first_cov, "coef"])
    ci_lower = float(summary.loc[first_cov, "exp(coef) lower 95%"])
    ci_upper = float(summary.loc[first_cov, "exp(coef) upper 95%"])

    interpretation = (
        f"H2c: Cox PH 模型, 参照组=neutral. "
        f"{first_cov}: HR={hr:.3f}, 95% CI=({ci_lower:.3f}, {ci_upper:.3f}), "
        f"p={p_cox:.4f}. "
        f"{'显著' if sig else '不显著'} 影响协议持久性."
    )

    return HypothesisResult(
        hypothesis="H2c",
        test_name="Cox Proportional Hazards model",
        test_statistic=float(hr),
        p_value=p_cox,
        effect_size=log_hr,
        confidence_interval=(ci_lower, ci_upper),
        significant=sig,
        interpretation=interpretation,
    )


# ═══════════════════════════════════════════════════════════════
# H3: Mediation Effect
# ═══════════════════════════════════════════════════════════════


def test_h3_mediation_effect(
    runs_with_payment: list[dict], runs_without_payment: list[dict]
) -> HypothesisResult:
    """
    H3: Bootstrap mediation test (5000 resamples, bias-corrected percentile CI).
    X = mediator_bias, M = side_payment_usage, Y = agreement
    Path a: X->M, Path b: M->Y|X, Path c': X->Y|M
    Indirect effect = a*b. Test if 95% CI excludes 0.
    Also compare agreement rates with vs without payment.
    """
    from backend.analysis.mediation import bootstrap_mediation

    # Build X (bias), M (side payment used), Y (agreement) from payment-enabled runs
    x_vals = []
    m_vals = []
    y_vals = []

    for r in runs_with_payment:
        code = r.get("condition_code", "")
        # Map condition to bias: H-PS/L-PS=0.7, H-N/L-N=0.0, H-PW/L-PW=-0.7
        if "PS" in code:
            bias = 0.7
        elif "PW" in code:
            bias = -0.7
        elif "N" in code:
            bias = 0.0
        else:
            bias = 0.0
        x_vals.append(bias)
        m_vals.append(float(r.get("side_payment_used_total", 0.0)))
        y_vals.append(1.0 if r.get("agreement_reached", False) else 0.0)

    x_arr = np.array(x_vals, dtype=float)
    m_arr = np.array(m_vals, dtype=float)
    y_arr = np.array(y_vals, dtype=float)

    boot_result = bootstrap_mediation(x_arr, m_arr, y_arr, n_bootstrap=5000, random_seed=42)

    # Compare agreement rates with vs without payment
    agree_with = _extract_agreement_rate(runs_with_payment).mean()
    agree_without = _extract_agreement_rate(runs_without_payment).mean()

    indirect = boot_result["indirect_effect"]
    ci_lower = boot_result["ci_lower"]
    ci_upper = boot_result["ci_upper"]
    sig = boot_result["significant"]

    interpretation = (
        f"H3: Bootstrap 中介分析 (5000次重抽样, 偏差校正百分位法). "
        f"路径a (X->M)={boot_result['path_a']:.3f}, "
        f"路径b (M->Y|X)={boot_result['path_b']:.3f}, "
        f"间接效应 a*b={indirect:.4f}, "
        f"95% BC CI=({ci_lower:.4f}, {ci_upper:.4f}). "
        f"中介效应{'显著' if sig else '不显著'} (CI {'不' if sig else ''}包含0). "
        f"边支付启用组协议率={agree_with:.3f}, 禁用组={agree_without:.3f}. "
        f"中介比例={boot_result['proportion_mediated']:.3f}."
    )

    return HypothesisResult(
        hypothesis="H3",
        test_name="Bootstrap mediation (5000 resamples, bias-corrected percentile CI)",
        test_statistic=float(boot_result["boot_mean"]),
        p_value=0.0,  # Bootstrap uses CI-based inference, not p-value
        effect_size=float(indirect),
        confidence_interval=(ci_lower, ci_upper),
        significant=sig,
        interpretation=interpretation,
    )


# ═══════════════════════════════════════════════════════════════
# H4: Moderation Effect
# ═══════════════════════════════════════════════════════════════


def test_h4_moderation_effect(runs: list[dict]) -> HypothesisResult:
    """
    H4: Two-way ANOVA: agreement ~ mediator_type * asymmetry_level.
    Interaction significance is key. Simple effects at each asymmetry level.
    Partial eta-squared.
    """
    def mediator_type(code: str) -> str:
        if "PS" in code:
            return "pro-strong"
        elif "N" in code:
            return "neutral"
        elif "PW" in code:
            return "pro-weak"
        return "other"

    def asymmetry_level(code: str) -> str:
        if code.startswith("H-"):
            return "high"
        elif code.startswith("L-"):
            return "low"
        return "other"

    rows = []
    for r in runs:
        code = r.get("condition_code", "")
        mt = mediator_type(code)
        al = asymmetry_level(code)
        if mt == "other" or al == "other":
            continue
        rows.append({
            "agreement": 1.0 if r.get("agreement_reached", False) else 0.0,
            "mediator": mt,
            "asymmetry": al,
        })

    df = pd.DataFrame(rows)

    from statsmodels.formula.api import ols
    from statsmodels.stats.anova import anova_lm

    model = ols("agreement ~ C(mediator) * C(asymmetry)", data=df).fit()
    try:
        anova_table = anova_lm(model, typ=2)
    except ValueError:
        # Fallback: typ=1 or return non-significant on sparse data
        try:
            anova_table = anova_lm(model, typ=1)
        except Exception:
            return HypothesisResult(
                hypothesis="H4",
                test_name="Two-way ANOVA (insufficient data)",
                test_statistic=0.0,
                p_value=1.0,
                effect_size=0.0,
                confidence_interval=(0.0, 0.0),
                significant=False,
                interpretation="H4: 样本量不足以进行双因素方差分析",
            )

    # Extract interaction row
    interaction_key = "C(mediator):C(asymmetry)"
    if interaction_key not in anova_table.index:
        return HypothesisResult(
            hypothesis="H4",
            test_name="Two-way ANOVA: agreement ~ mediator_type * asymmetry_level",
            test_statistic=0.0,
            p_value=1.0,
            effect_size=0.0,
            confidence_interval=(0.0, 0.0),
            significant=False,
            interpretation="H4: 交互项缺失，无法完成检验",
        )

    f_int = float(anova_table.loc[interaction_key, "F"])
    p_int = float(anova_table.loc[interaction_key, "PR(>F)"])
    df_int = int(anova_table.loc[interaction_key, "df"])
    df_error = int(anova_table.loc["Residual", "df"])

    eta2_int = eta_squared_from_f(f_int, df_int, df_error)
    sig = p_int < config.alpha

    # Simple effects: agreement by mediator at each asymmetry level
    simple_effects_str = ""
    for level in ["high", "low"]:
        sub = df[df["asymmetry"] == level]
        if len(sub) < 6:
            continue
        means = sub.groupby("mediator")["agreement"].mean()
        simple_effects_str += f"{level}: PS={means.get('pro-strong', 0):.3f}, N={means.get('neutral', 0):.3f}, PW={means.get('pro-weak', 0):.3f}; "

    interpretation = (
        f"H4: 双因素方差分析 (调停者类型 x 不对称水平). "
        f"交互效应 F({df_int}, {df_error})={f_int:.3f}, p={p_int:.4f}, "
        f"偏eta2={eta2_int:.4f}. "
        f"交互作用{'显著' if sig else '不显著'}. "
        f"简单效应: {simple_effects_str}"
    )

    return HypothesisResult(
        hypothesis="H4",
        test_name="Two-way ANOVA: agreement ~ mediator_type * asymmetry_level",
        test_statistic=f_int,
        p_value=p_int,
        effect_size=eta2_int,
        confidence_interval=(0.0, 0.0),
        significant=sig,
        interpretation=interpretation,
    )


# ═══════════════════════════════════════════════════════════════
# Run All
# ═══════════════════════════════════════════════════════════════


def run_all_tests(runs: list[dict], disable_payment_runs: list[dict] | None = None) -> list[HypothesisResult]:
    """Run all 4 hypothesis tests."""
    results: list[HypothesisResult] = []
    results.append(test_h1_bias_main_effect(runs))
    results.extend(test_h2_agreement_quality(runs))
    if disable_payment_runs:
        results.append(test_h3_mediation_effect(runs, disable_payment_runs))
    results.append(test_h4_moderation_effect(runs))
    return results

from __future__ import annotations
import numpy as np
from scipy import stats


def bootstrap_mediation(x, m, y, n_bootstrap=5000, random_seed=42) -> dict:
    """
    Bootstrap mediation per Preacher & Hayes (2008).
    X -> M -> Y, with direct X -> Y.

    Steps:
    1. Path a: regress M ~ X  ->  a = cov(X,M)/var(X)
    2. Path b and c': regress Y ~ X + M  ->  b, c_prime
    3. Indirect = a * b, Total = c_prime + a*b
    4. Bootstrap: resample n rows with replacement n_bootstrap times
    5. For each bootstrap sample, compute a*b
    6. Bias-corrected percentile CI (95%)
    7. Significant if CI does not include 0

    Returns dict with path_a, path_b, path_c_prime, indirect_effect, total_effect,
    ci_lower, ci_upper, significant, proportion_mediated.
    """
    rng = np.random.RandomState(random_seed)
    x = np.asarray(x, dtype=float)
    m = np.asarray(m, dtype=float)
    y = np.asarray(y, dtype=float)
    n = len(x)

    # ── 1. Original path estimates using OLS closed form ──
    # Path a: M ~ X
    a, _, se_a, _ = ols_coef(x, m)

    # Path b and c': Y ~ X + M
    # Closed-form multiple regression: Y = b0 + c'*X + b*M
    X_mat = np.column_stack([np.ones(n), x, m])
    try:
        beta = np.linalg.lstsq(X_mat, y, rcond=None)[0]
        c_prime = beta[1]
        b = beta[2]
        y_pred = X_mat @ beta
        residuals = y - y_pred
        ss_res = (residuals ** 2).sum()
        ss_tot = ((y - y.mean()) ** 2).sum()
        r2_y = 1 - ss_res / ss_tot if ss_tot != 0 else 0.0
        # SE for b: sqrt(MSE * diag(X'X)^-1)
        mse = ss_res / (n - 3) if n > 3 else ss_res / n
        XtX_inv = np.linalg.inv(X_mat.T @ X_mat)
        se_b = np.sqrt(mse * XtX_inv[2, 2])
    except np.linalg.LinAlgError:
        c_prime = 0.0
        b = 0.0
        se_b = 0.0

    # Path c (total effect): Y ~ X
    c_total, _, _, _ = ols_coef(x, y)

    indirect_effect = a * b
    total_effect = c_total

    # ── 2. Bootstrap ──
    boot_indirect = np.zeros(n_bootstrap)
    data = np.column_stack([x, m, y])

    for i in range(n_bootstrap):
        idx = rng.randint(0, n, size=n)
        xb = data[idx, 0]
        mb = data[idx, 1]
        yb = data[idx, 2]

        # Path a in bootstrap
        ab, _, _, _ = ols_coef(xb, mb)

        # Path b in bootstrap (multiple regression)
        Xb_mat = np.column_stack([np.ones(n), xb, mb])
        try:
            betab = np.linalg.lstsq(Xb_mat, yb, rcond=None)[0]
            bb = betab[2]
        except np.linalg.LinAlgError:
            bb = 0.0

        boot_indirect[i] = ab * bb

    # ── 3. Bias-corrected percentile CI ──
    # Bias correction: z0 = Phi^-1(proportion of bootstrap estimates < original)
    prop_less = (boot_indirect < indirect_effect).mean()
    prop_less = np.clip(prop_less, 0.0001, 0.9999)  # avoid -inf/inf
    z0 = stats.norm.ppf(prop_less)

    # Desired percentiles
    alpha_lo = 0.025
    alpha_hi = 0.975

    z_lo = stats.norm.ppf(alpha_lo)
    z_hi = stats.norm.ppf(alpha_hi)

    p_lo = stats.norm.cdf(2 * z0 + z_lo)
    p_hi = stats.norm.cdf(2 * z0 + z_hi)

    idx_lo = int(np.round(p_lo * n_bootstrap))
    idx_hi = int(np.round(p_hi * n_bootstrap))
    idx_lo = max(0, min(idx_lo, n_bootstrap - 1))
    idx_hi = max(0, min(idx_hi, n_bootstrap - 1))

    boot_sorted = np.sort(boot_indirect)
    ci_lower = float(boot_sorted[idx_lo])
    ci_upper = float(boot_sorted[idx_hi])

    significant = not (ci_lower <= 0 <= ci_upper)

    # ── 4. Proportion mediated ──
    proportion_mediated = indirect_effect / total_effect if total_effect != 0 else 0.0

    return {
        "path_a": float(a),
        "path_b": float(b),
        "path_c_prime": float(c_prime),
        "path_c_total": float(c_total),
        "indirect_effect": float(indirect_effect),
        "total_effect": float(total_effect),
        "ci_lower": ci_lower,
        "ci_upper": ci_upper,
        "significant": significant,
        "proportion_mediated": float(proportion_mediated),
        "boot_mean": float(boot_indirect.mean()),
        "boot_se": float(boot_indirect.std(ddof=1)),
        "bootstrap_samples": boot_indirect.tolist(),
    }


def sobel_test(a, b, se_a, se_b) -> dict:
    """Sobel test for mediation (supplementary)."""
    denominator = np.sqrt(b**2 * se_a**2 + a**2 * se_b**2)
    if denominator == 0:
        z = 0.0
    else:
        z = a * b / denominator
    p_value = 2 * (1 - stats.norm.cdf(abs(z)))
    return {"z": float(z), "p_value": float(p_value), "indirect_effect": float(a * b)}


def ols_coef(x, y):
    """Simple OLS slope and intercept. Returns (slope, intercept, se_slope, r_squared)."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    n = len(x)
    mx, my = x.mean(), y.mean()
    num = ((x - mx) * (y - my)).sum()
    den = ((x - mx) ** 2).sum()
    if den == 0:
        slope = 0.0
    else:
        slope = num / den
    intercept = my - slope * mx
    y_pred = slope * x + intercept
    residuals = y - y_pred
    ss_res = (residuals ** 2).sum()
    ss_tot = ((y - my) ** 2).sum()
    r_squared = 1 - ss_res / ss_tot if ss_tot != 0 else 0.0
    if den != 0 and n > 2:
        se_slope = np.sqrt(ss_res / (n - 2) / den)
    else:
        se_slope = 0.0
    return slope, intercept, se_slope, r_squared

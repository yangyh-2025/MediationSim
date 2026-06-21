from __future__ import annotations
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def fit_kaplan_meier(durations, event_observed, groups) -> dict:
    """Fit KM for each group. Returns {group: kmf} dict."""
    from lifelines import KaplanMeierFitter

    unique_groups = sorted(set(groups))
    kmfs = {}
    for g in unique_groups:
        mask = np.array(groups) == g
        kmf = KaplanMeierFitter()
        kmf.fit(
            np.array(durations, dtype=float)[mask],
            np.array(event_observed, dtype=int)[mask],
            label=str(g),
        )
        kmfs[g] = kmf
    return kmfs


def run_logrank_test(durations1, events1, durations2, events2) -> dict:
    """Log-rank test between two groups."""
    from lifelines.statistics import logrank_test

    result = logrank_test(
        np.asarray(durations1, dtype=float),
        np.asarray(durations2, dtype=float),
        np.asarray(events1, dtype=int),
        np.asarray(events2, dtype=int),
    )
    return {"statistic": float(result.test_statistic), "p_value": float(result.p_value)}


def fit_cox_model(df, duration_col, event_col, covariates) -> dict:
    """Fit Cox PH model, return summary dict."""
    from lifelines import CoxPHFitter

    cols = [duration_col, event_col] + covariates
    cph = CoxPHFitter()
    cph.fit(df[cols], duration_col=duration_col, event_col=event_col)
    return cph.summary.to_dict()


def plot_survival_curves(kmf_dict: dict, output_path: str, title: str = "Survival Curves"):
    """Plot Kaplan-Meier curves, save to file."""
    fig, ax = plt.subplots(figsize=(10, 6))
    for label, kmf in kmf_dict.items():
        kmf.plot_survival_function(ax=ax)
    ax.set_title(title)
    ax.set_xlabel("Time (rounds)")
    ax.set_ylabel("Survival Probability")
    plt.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)

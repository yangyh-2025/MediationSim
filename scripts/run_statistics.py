#!/usr/bin/env python3
"""Complete statistical analysis for the paper."""
import sqlite3, json, numpy as np
from scipy import stats
import pandas as pd

conn = sqlite3.connect('data/mediation_sim.db')
conn.row_factory = sqlite3.Row
c = conn.cursor()

exp_id = 'd19b51d4-85f1-48d1-9dd4-0a4d32fbcb98'
c.execute('SELECT * FROM runs WHERE experiment_id=?', (exp_id,))
runs = [dict(r) for r in c.fetchall()]

exp_id2 = 'bdfa04d3-b13d-48c0-a01e-83e741be1c43'
c.execute('SELECT * FROM runs WHERE experiment_id=?', (exp_id2,))
runs_no_sp = [dict(r) for r in c.fetchall()]

print('=' * 70)
print('COMPLETE STATISTICAL ANALYSIS')
print('=' * 70)

def mediator_type(code):
    if 'PS' in code: return 'pro-strong'
    elif 'N' in code: return 'neutral'
    elif 'PW' in code: return 'pro-weak'
    return 'other'

def asymmetry_level(code):
    if code.startswith('H-'): return 'high'
    elif code.startswith('L-'): return 'low'
    return 'other'

def get_territory(r):
    rj = r.get('result_json')
    if not rj: return None
    rj = json.loads(rj) if isinstance(rj, str) else rj
    fp = rj.get('final_proposal') or {}
    return fp.get('territory_split')

def cohens_d(g1, g2):
    g1, g2 = np.asarray(g1, float), np.asarray(g2, float)
    n1, n2 = len(g1), len(g2)
    if n1 < 2 or n2 < 2: return 0.0
    pooled = np.sqrt(((n1-1)*g1.var(ddof=1) + (n2-1)*g2.var(ddof=1)) / (n1+n2-2))
    return float((g1.mean() - g2.mean()) / pooled) if pooled != 0 else 0.0

# ==========================================
# H1: BIAS MAIN EFFECT
# ==========================================
print('\n' + '='*70)
print('H1: BIAS MAIN EFFECT')
print('='*70)

for cond in ['H-PS','H-N','H-PW','L-PS','L-N','L-PW','CD']:
    cr = [r for r in runs if r['condition_code']==cond]
    agree = sum(1 for r in cr if r['agreement_reached'])
    print(f'{cond}: {agree}/{len(cr)} ({agree/len(cr):.1%})')

# High AR: H-PS vs H-N
hps = np.array([r['agreement_reached'] for r in runs if r['condition_code']=='H-PS'])
hn = np.array([r['agreement_reached'] for r in runs if r['condition_code']=='H-N'])
t_h1, p_h1 = stats.ttest_ind(hps, hn)
p_h1_one = p_h1/2 if hps.mean() > hn.mean() else 1-p_h1/2
d_h1 = cohens_d(hps, hn)
print(f'\nHigh AR: H-PS(M={hps.mean():.3f}) vs H-N(M={hn.mean():.3f})')
print(f't({len(hps)+len(hn)-2})={t_h1:.3f}, p(one-tailed)={p_h1_one:.4f}, d={d_h1:.3f}')

# High AR: All pairwise
for pair in [('H-PS','H-PW'),('H-N','H-PW')]:
    g1 = np.array([r['agreement_reached'] for r in runs if r['condition_code']==pair[0]])
    g2 = np.array([r['agreement_reached'] for r in runs if r['condition_code']==pair[1]])
    t, p = stats.ttest_ind(g1, g2)
    d = cohens_d(g1, g2)
    print(f'{pair[0]} vs {pair[1]}: t={t:.3f}, p={p:.4f}, d={d:.3f}')

# ==========================================
# H2: AGREEMENT QUALITY
# ==========================================
print('\n' + '='*70)
print('H2: AGREEMENT QUALITY')
print('='*70)

# H2a: Gini ANOVA
gini_vals, med_types_g = [], []
for r in runs:
    mt = mediator_type(r['condition_code'])
    if mt == 'other': continue
    g = r['agreement_gini']
    if g is not None:
        gini_vals.append(g)
        med_types_g.append(mt)

for mt in ['pro-strong','neutral','pro-weak']:
    gs = [g for g,m in zip(gini_vals, med_types_g) if m==mt]
    print(f'{mt}: M={np.mean(gs):.4f}, SD={np.std(gs):.4f}, n={len(gs)}')

df_g = pd.DataFrame({'gini':gini_vals, 'mediator':med_types_g})
from statsmodels.formula.api import ols
from statsmodels.stats.anova import anova_lm
model_g = ols('gini ~ C(mediator)', data=df_g).fit()
aov_g = anova_lm(model_g, typ=2)
f_h2a = aov_g.loc['C(mediator)','F']
p_h2a = aov_g.loc['C(mediator)','PR(>F)']
df_e = int(aov_g.loc['Residual','df'])
eta2_h2a = (f_h2a * 2) / (f_h2a * 2 + df_e)
print(f'\nANOVA: F(2,{df_e})={f_h2a:.3f}, p={p_h2a:.6f}, eta2={eta2_h2a:.4f}')

from statsmodels.stats.multicomp import pairwise_tukeyhsd
tukey = pairwise_tukeyhsd(df_g['gini'], df_g['mediator'], alpha=0.05)
print('\nTukey HSD:')
print(tukey)

# Territory comparison
for mt in ['pro-strong','neutral','pro-weak']:
    ts = [get_territory(r) for r in runs if mediator_type(r['condition_code'])==mt and get_territory(r)]
    print(f'{mt} territory: M={np.mean(ts):.1f}%, SD={np.std(ts):.1f}, n={len(ts)}')

# H2b: Cox PH
print('\n-- Cox PH Model --')
try:
    from lifelines import CoxPHFitter
    rows_cox = []
    for r in runs:
        mt = mediator_type(r['condition_code'])
        if mt == 'other': continue
        rows_cox.append({'duration':r['rounds_completed'], 'event':r['agreement_reached'], 'mediator':mt})
    df_cox = pd.DataFrame(rows_cox)
    df_cox = pd.get_dummies(df_cox, columns=['mediator'], drop_first=False)
    covs = [c for c in df_cox.columns if c.startswith('mediator_') and c != 'mediator_neutral']
    cph = CoxPHFitter()
    cph.fit(df_cox[['duration','event']+covs], duration_col='duration', event_col='event')
    print(cph.summary)
except Exception as e:
    print(f'Cox PH error: {e}')

# ==========================================
# H3: MEDIATION EFFECT
# ==========================================
print('\n' + '='*70)
print('H3: MEDIATION EFFECT')
print('='*70)

for cond in ['H-PS','L-PS','CD']:
    w = [r['agreement_reached'] for r in runs if r['condition_code']==cond]
    wo = [r['agreement_reached'] for r in runs_no_sp if r['condition_code']==cond]
    print(f'{cond}: With SP={np.mean(w):.3f} ({sum(w)}/{len(w)}), Without SP={np.mean(wo):.3f} ({sum(wo)}/{len(wo)})')
    t, p = stats.ttest_ind(w, wo)
    print(f'  t={t:.3f}, p={p:.4f}')

ps_w = [r['agreement_reached'] for r in runs if r['condition_code'] in ('H-PS','L-PS')]
ps_wo = [r['agreement_reached'] for r in runs_no_sp if r['condition_code'] in ('H-PS','L-PS')]
t_all, p_all = stats.ttest_ind(ps_w, ps_wo)
d_all = cohens_d(ps_w, ps_wo)
print(f'\nOverall PS: With SP={np.mean(ps_w):.3f}, Without SP={np.mean(ps_wo):.3f}')
print(f't={t_all:.3f}, p={p_all:.4f}, d={d_all:.3f}')

# Bootstrap mediation
print('\n-- Bootstrap Mediation (Preacher & Hayes 2008) --')
sys.path.insert(0, '.')
from backend.analysis.mediation import bootstrap_mediation

runs_ps = [r for r in runs if r['condition_code'] in ('H-PS','L-PS','CD')]
x_vals, m_vals, y_vals = [], [], []
for r in runs_ps:
    code = r['condition_code']
    if 'PS' in code: bias = 0.7
    elif 'CD' in code: bias = 0.7
    elif 'PW' in code: bias = -0.7
    else: bias = 0.0
    x_vals.append(bias)
    m_vals.append(float(r.get('side_payment_used', 0) or 0))
    y_vals.append(float(r['agreement_reached']))
result = bootstrap_mediation(np.array(x_vals), np.array(m_vals), np.array(y_vals), n_bootstrap=5000)
for k,v in result.items():
    if k != 'bootstrap_samples':
        print(f'  {k}: {v}')

# ==========================================
# H4: MODERATION EFFECT
# ==========================================
print('\n' + '='*70)
print('H4: MODERATION EFFECT')
print('='*70)

df_mod = pd.DataFrame([{
    'agreement': r['agreement_reached'],
    'mediator': mediator_type(r['condition_code']),
    'asymmetry': asymmetry_level(r['condition_code'])
} for r in runs if mediator_type(r['condition_code'])!='other' and asymmetry_level(r['condition_code'])!='other'])

model_mod = ols('agreement ~ C(mediator) * C(asymmetry)', data=df_mod).fit()
aov_mod = anova_lm(model_mod, typ=2)
print(aov_mod)

for level in ['high','low']:
    sub = df_mod[df_mod['asymmetry']==level]
    means = sub.groupby('mediator')['agreement'].agg(['mean','count'])
    print(f'\n{level} AR:')
    print(means)

# ==========================================
# TERRITORY ANALYSIS
# ==========================================
print('\n' + '='*70)
print('TERRITORY SPLIT ANALYSIS')
print('='*70)

for cond in ['H-PS','H-N','H-PW','L-PS','L-N','L-PW','CD']:
    ts = [get_territory(r) for r in runs if r['condition_code']==cond and get_territory(r)]
    if ts:
        print(f'{cond}: M={np.mean(ts):.1f}%, SD={np.std(ts):.1f}, n={len(ts)}')

for pair in [('H-PS','H-N'),('H-PW','H-N'),('L-PS','L-N'),('L-PW','L-N')]:
    t1 = [get_territory(r) for r in runs if r['condition_code']==pair[0] and get_territory(r)]
    t2 = [get_territory(r) for r in runs if r['condition_code']==pair[1] and get_territory(r)]
    tv, pv = stats.ttest_ind(t1, t2)
    d = cohens_d(np.array(t1), np.array(t2))
    print(f'{pair[0]} vs {pair[1]}: t={tv:.3f}, p={pv:.6f}, d={d:.2f}')

# ==========================================
# SUMMARY
# ==========================================
print('\n' + '='*70)
print('SUMMARY FOR PAPER')
print('='*70)

def fmt_rate(vals):
    return f'{np.mean(vals):.1%}'

# Overall by mediator type
for mt in ['pro-strong','neutral','pro-weak']:
    ag = [r['agreement_reached'] for r in runs if mediator_type(r['condition_code'])==mt]
    gs = [r['agreement_gini'] for r in runs if mediator_type(r['condition_code'])==mt and r['agreement_gini'] is not None]
    ts = [get_territory(r) for r in runs if mediator_type(r['condition_code'])==mt and get_territory(r)]
    print(f'{mt}: agree_rate={fmt_rate(ag)}, gini={np.mean(gs):.3f}, territory={np.mean(ts):.1f}%')

# Key finding summary
print(f'\nKey Finding 1 (H1): H-PS vs H-N, d={d_h1:.3f}, p(one-tailed)={p_h1_one:.4f}')
print(f'Key Finding 2 (H2): Gini ANOVA F={f_h2a:.1f}, p={p_h2a:.4f}, eta2={eta2_h2a:.3f}')
print(f'Key Finding 3 (H3): Payment ON vs OFF, t={t_all:.3f}, p={p_all:.4f}, d={d_all:.3f}')
print(f'Key Finding 4 (H4): Interaction F={aov_mod.loc["C(mediator):C(asymmetry)","F"]:.3f}, p={aov_mod.loc["C(mediator):C(asymmetry)","PR(>F)"]:.4f}')

conn.close()

#!/usr/bin/env python3
"""Generate all academic charts for the IR paper."""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import sqlite3, json, os
from scipy import stats

plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

output_dir = 'docs/figures'
os.makedirs(output_dir, exist_ok=True)

conn = sqlite3.connect('data/mediation_sim.db')
conn.row_factory = sqlite3.Row
c = conn.cursor()

exp_id = 'd19b51d4-85f1-48d1-9dd4-0a4d32fbcb98'
c.execute('SELECT * FROM runs WHERE experiment_id=?', (exp_id,))
runs = [dict(r) for r in c.fetchall()]

exp_id2 = 'bdfa04d3-b13d-48c0-a01e-83e741be1c43'
c.execute('SELECT * FROM runs WHERE experiment_id=?', (exp_id2,))
runs_no_sp = [dict(r) for r in c.fetchall()]

conditions = ['H-PS','H-N','H-PW','L-PS','L-N','L-PW','CD']
short_labels = {'H-PS':'H-PS','H-N':'H-N','H-PW':'H-PW','L-PS':'L-PS','L-N':'L-N','L-PW':'L-PW','CD':'CD'}
box_colors = ['#2E86AB','#A23B72','#F18F01','#2E86AB','#A23B72','#F18F01','#C73E1D']

def get_territory(r):
    rj = r.get('result_json')
    if not rj:
        return None
    rj = json.loads(rj) if isinstance(rj, str) else rj
    fp = rj.get('final_proposal') or {}
    return fp.get('territory_split')

# ============================================================
# Figure 1: Agreement Rate by Condition (bar chart)
# ============================================================
fig, ax = plt.subplots(figsize=(12, 6))
agree_rates = []
agree_ns = []
for cond in conditions:
    cr = [r for r in runs if r['condition_code'] == cond]
    rate = sum(1 for r in cr if r['agreement_reached']) / len(cr)
    agree_rates.append(rate)
    agree_ns.append(len(cr))

colors_bar = ['#2E86AB','#A23B72','#F18F01','#2E86AB','#A23B72','#F18F01','#C73E1D']
x = np.arange(len(conditions))
bars = ax.bar(x, [r * 100 for r in agree_rates], color=colors_bar,
              edgecolor='white', linewidth=0.8, width=0.65)

for i, (bar, rate, n) in enumerate(zip(bars, agree_rates, agree_ns)):
    ax.text(bar.get_x() + bar.get_width() / 2., bar.get_height() + 1.5,
            f'{rate:.0%}\n(n={n})', ha='center', va='bottom',
            fontsize=10, fontweight='bold')

ax.set_xticks(x)
ax.set_xticklabels([short_labels[c] for c in conditions], fontsize=10)
ax.set_ylabel('Agreement Rate (%)', fontsize=12, fontweight='bold')
ax.set_title('Agreement Rate by Experimental Condition', fontsize=14, fontweight='bold', pad=15)
ax.set_ylim(0, 85)
ax.grid(axis='y', alpha=0.3, linestyle='--')
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)
ax.axhline(y=50, color='gray', linestyle=':', alpha=0.5, linewidth=1)
plt.tight_layout()
fig.savefig(f'{output_dir}/fig1_agreement_rates.png', dpi=200, bbox_inches='tight')
plt.close()
print('Figure 1 saved')

# ============================================================
# Figure 2: Territory Split Distribution by Condition (box plot)
# ============================================================
fig, ax = plt.subplots(figsize=(12, 6))
territory_data = []
positions = []
labels = []
for i, cond in enumerate(conditions):
    cr = [r for r in runs if r['condition_code'] == cond]
    ts = [get_territory(r) for r in cr if get_territory(r) is not None]
    territory_data.append(ts)
    positions.append(i + 1)
    labels.append(short_labels[cond])

bp = ax.boxplot(territory_data, positions=positions, patch_artist=True,
                widths=0.5, showmeans=True,
                meanprops=dict(marker='D', markerfacecolor='white', markersize=6))
ax.set_xticklabels(labels, fontsize=10)

for patch, color in zip(bp['boxes'], box_colors):
    patch.set_facecolor(color)
    patch.set_alpha(0.7)

for i, (data, pos) in enumerate(zip(territory_data, positions)):
    jitter = np.random.normal(0, 0.08, len(data))
    ax.scatter([pos] * len(data) + jitter, data, alpha=0.5, s=30,
               color=box_colors[i], edgecolors='white', linewidth=0.3)

ax.axhline(y=50, color='gray', linestyle='--', alpha=0.5, linewidth=1, label='Equal Split (50%)')
ax.set_ylabel('Territory Split (% to Strong Party)', fontsize=12, fontweight='bold')
ax.set_title('Distribution of Territory Split by Condition', fontsize=14, fontweight='bold', pad=15)
ax.legend(loc='upper right', fontsize=9)
ax.grid(axis='y', alpha=0.3, linestyle='--')
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)
plt.tight_layout()
fig.savefig(f'{output_dir}/fig2_territory_splits.png', dpi=200, bbox_inches='tight')
plt.close()
print('Figure 2 saved')

# ============================================================
# Figure 3: Gini Coefficient by Condition
# ============================================================
fig, ax = plt.subplots(figsize=(12, 6))
gini_data = []
for i, cond in enumerate(conditions):
    cr = [r for r in runs if r['condition_code'] == cond]
    gs = [r['agreement_gini'] for r in cr if r['agreement_gini'] is not None]
    gini_data.append(gs)

bp2 = ax.boxplot(gini_data, positions=positions, patch_artist=True,
                 widths=0.5, showmeans=True,
                 meanprops=dict(marker='D', markerfacecolor='white', markersize=6))
ax.set_xticklabels(labels, fontsize=10)

for patch, color in zip(bp2['boxes'], box_colors):
    patch.set_facecolor(color)
    patch.set_alpha(0.7)

for i, (data, pos) in enumerate(zip(gini_data, positions)):
    jitter = np.random.normal(0, 0.08, len(data))
    ax.scatter([pos] * len(data) + jitter, data, alpha=0.5, s=30,
               color=box_colors[i], edgecolors='white', linewidth=0.3)

ax.set_ylabel('Gini Coefficient of Agreement', fontsize=12, fontweight='bold')
ax.set_title('Agreement Equity by Condition (Higher Gini = Less Equitable)',
             fontsize=14, fontweight='bold', pad=15)
ax.grid(axis='y', alpha=0.3, linestyle='--')
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)
plt.tight_layout()
fig.savefig(f'{output_dir}/fig3_gini_coefficients.png', dpi=200, bbox_inches='tight')
plt.close()
print('Figure 3 saved')

# ============================================================
# Figure 4: DA Scores — PA and Pressure by Condition
# ============================================================
c.execute('''
SELECT r.condition_code, rnd.domestic_scores_json
FROM rounds rnd JOIN runs r ON rnd.run_id=r.id
WHERE r.experiment_id=? AND rnd.domestic_scores_json != '{}'
ORDER BY r.condition_code, rnd.run_id, rnd.round_number
''', (exp_id,))
da_all = c.fetchall()

da_by_cond = {}
for row in da_all:
    cond = row['condition_code']
    if cond not in da_by_cond:
        da_by_cond[cond] = {'strong_pa': [], 'weak_pa': [],
                            'strong_pr': [], 'weak_pr': []}
    ds = json.loads(row['domestic_scores_json'])
    if 'strong' in ds:
        da_by_cond[cond]['strong_pa'].append(ds['strong']['political_acceptability'])
        da_by_cond[cond]['strong_pr'].append(ds['strong']['pressure_level'])
    if 'weak' in ds:
        da_by_cond[cond]['weak_pa'].append(ds['weak']['political_acceptability'])
        da_by_cond[cond]['weak_pr'].append(ds['weak']['pressure_level'])

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
x_pa = np.arange(len(conditions))
width = 0.35

# PA chart
s_pa_means = [np.mean(da_by_cond[c]['strong_pa']) for c in conditions]
w_pa_means = [np.mean(da_by_cond[c]['weak_pa']) for c in conditions]
s_pa_err = [np.std(da_by_cond[c]['strong_pa']) / np.sqrt(len(da_by_cond[c]['strong_pa']))
            for c in conditions]
w_pa_err = [np.std(da_by_cond[c]['weak_pa']) / np.sqrt(len(da_by_cond[c]['weak_pa']))
            for c in conditions]

ax1.bar(x_pa - width/2, s_pa_means, width, yerr=s_pa_err,
        label='Strong Party', color='#2E86AB', edgecolor='white', capsize=3)
ax1.bar(x_pa + width/2, w_pa_means, width, yerr=w_pa_err,
        label='Weak Party', color='#F18F01', edgecolor='white', capsize=3)
ax1.set_xticks(x_pa)
ax1.set_xticklabels([short_labels[c] for c in conditions], fontsize=8)
ax1.set_ylabel('Political Acceptability', fontsize=11, fontweight='bold')
ax1.set_title('Political Acceptability by Condition', fontsize=13, fontweight='bold')
ax1.legend(fontsize=10)
ax1.grid(axis='y', alpha=0.3, linestyle='--')
ax1.spines['top'].set_visible(False)
ax1.spines['right'].set_visible(False)

# Pressure chart
s_pr_means = [np.mean(da_by_cond[c]['strong_pr']) for c in conditions]
w_pr_means = [np.mean(da_by_cond[c]['weak_pr']) for c in conditions]
s_pr_err = [np.std(da_by_cond[c]['strong_pr']) / np.sqrt(len(da_by_cond[c]['strong_pr']))
            for c in conditions]
w_pr_err = [np.std(da_by_cond[c]['weak_pr']) / np.sqrt(len(da_by_cond[c]['weak_pr']))
            for c in conditions]

ax2.bar(x_pa - width/2, s_pr_means, width, yerr=s_pr_err,
        label='Strong Party', color='#2E86AB', edgecolor='white', capsize=3)
ax2.bar(x_pa + width/2, w_pr_means, width, yerr=w_pr_err,
        label='Weak Party', color='#F18F01', edgecolor='white', capsize=3)
ax2.set_xticks(x_pa)
ax2.set_xticklabels([short_labels[c] for c in conditions], fontsize=8)
ax2.set_ylabel('Domestic Pressure Level', fontsize=11, fontweight='bold')
ax2.set_title('Domestic Pressure by Condition', fontsize=13, fontweight='bold')
ax2.legend(fontsize=10)
ax2.grid(axis='y', alpha=0.3, linestyle='--')
ax2.spines['top'].set_visible(False)
ax2.spines['right'].set_visible(False)
plt.tight_layout()
fig.savefig(f'{output_dir}/fig4_da_scores.png', dpi=200, bbox_inches='tight')
plt.close()
print('Figure 4 saved')

# ============================================================
# Figure 5: Side Payment Escalation Pattern
# ============================================================
fig, ax = plt.subplots(figsize=(10, 6))
sp_conditions = ['CD', 'H-PS', 'L-PS']
sp_colors = {'CD': '#C73E1D', 'H-PS': '#2E86AB', 'L-PS': '#20A39E'}
sp_styles = {'CD': '-', 'H-PS': '--', 'L-PS': '--'}

for cond in sp_conditions:
    mean_sp = []
    for rn in range(1, 9):
        c.execute('''
        SELECT rnd.proposal_json FROM rounds rnd JOIN runs r ON rnd.run_id=r.id
        WHERE r.experiment_id=? AND r.condition_code=? AND rnd.round_number=?
        ''', (exp_id, cond, rn))
        vals = [json.loads(row['proposal_json']).get('side_payment_amount', 0) or 0
                for row in c.fetchall()]
        mean_sp.append(np.mean(vals) if vals else 0)
    ax.plot(range(1, 9), mean_sp, sp_styles[cond], color=sp_colors[cond],
            marker='o', markersize=8, linewidth=2.5, label=cond, alpha=0.85)

ax.axvspan(0.5, 4.5, alpha=0.05, color='green')
ax.axvspan(4.5, 6.5, alpha=0.05, color='orange')
ax.axvspan(6.5, 8.5, alpha=0.05, color='red')
ax.text(2.5, 1.75, 'Phase 1\n(<=8% budget)', ha='center', fontsize=8, color='green', style='italic')
ax.text(5.5, 1.75, 'Phase 2\n(<=12%)', ha='center', fontsize=8, color='orange', style='italic')
ax.text(7.5, 1.75, 'Phase 3\n(No cap)', ha='center', fontsize=8, color='red', style='italic')

ax.set_xlabel('Negotiation Round', fontsize=12, fontweight='bold')
ax.set_ylabel('Mean Side Payment Amount', fontsize=12, fontweight='bold')
ax.set_title('Side Payment Escalation by Round (Pro-Strong Conditions)',
             fontsize=14, fontweight='bold', pad=15)
ax.legend(fontsize=10, loc='upper left')
ax.grid(alpha=0.3, linestyle='--')
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)
ax.set_xticks(range(1, 9))
plt.tight_layout()
fig.savefig(f'{output_dir}/fig5_side_payment_pattern.png', dpi=200, bbox_inches='tight')
plt.close()
print('Figure 5 saved')

# ============================================================
# Figure 6: Payment ON vs OFF Comparison
# ============================================================
fig, ax = plt.subplots(figsize=(8, 6))
ps_conds = ['H-PS', 'L-PS', 'CD']
x_pos = np.arange(len(ps_conds))
width2 = 0.35

with_sp = []
without_sp = []
for cond in ps_conds:
    w = [r['agreement_reached'] for r in runs if r['condition_code'] == cond]
    wo = [r['agreement_reached'] for r in runs_no_sp if r['condition_code'] == cond]
    with_sp.append(np.mean(w))
    without_sp.append(np.mean(wo))

bars_on = ax.bar(x_pos - width2/2, [r * 100 for r in with_sp], width2,
                 label='Side Payment Enabled', color='#2E86AB', edgecolor='white')
bars_off = ax.bar(x_pos + width2/2, [r * 100 for r in without_sp], width2,
                  label='Side Payment Disabled', color='#C73E1D', edgecolor='white')

for bar, val in zip(bars_on, with_sp):
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1,
            f'{val:.0%}', ha='center', fontsize=11, fontweight='bold')
for bar, val in zip(bars_off, without_sp):
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1,
            f'{val:.0%}', ha='center', fontsize=11, fontweight='bold')

ax.set_xticks(x_pos)
ax.set_xticklabels(ps_conds, fontsize=11)
ax.set_ylabel('Agreement Rate (%)', fontsize=12, fontweight='bold')
ax.set_title('Effect of Side Payment on Agreement Rate', fontsize=14, fontweight='bold', pad=15)
ax.legend(fontsize=10, loc='upper right')
ax.set_ylim(0, 85)
ax.grid(axis='y', alpha=0.3, linestyle='--')
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)
plt.tight_layout()
fig.savefig(f'{output_dir}/fig6_payment_on_off.png', dpi=200, bbox_inches='tight')
plt.close()
print('Figure 6 saved')

# ============================================================
# Figure 7: Interaction Plot (H4 - Moderation Effect)
# ============================================================
fig, ax = plt.subplots(figsize=(10, 6))
mediator_types = ['Pro-Strong', 'Neutral', 'Pro-Weak']

def get_agreement_rate(cond_list):
    cr = [r for r in runs if r['condition_code'] in cond_list]
    if not cr:
        return 0
    return sum(1 for r in cr if r['agreement_reached']) / len(cr)

high_rates = [get_agreement_rate(['H-PS']), get_agreement_rate(['H-N']), get_agreement_rate(['H-PW'])]
low_rates = [get_agreement_rate(['L-PS']), get_agreement_rate(['L-N']), get_agreement_rate(['L-PW'])]

x_int = np.arange(len(mediator_types))
ax.plot(x_int, [r * 100 for r in high_rates], 'o-', color='#2E86AB', linewidth=2.5,
        markersize=10, label='High Asymmetry (AR=3.0)')
ax.plot(x_int, [r * 100 for r in low_rates], 's--', color='#F18F01', linewidth=2.5,
        markersize=10, label='Low Asymmetry (AR=1.5)')

for i, (hr, lr) in enumerate(zip(high_rates, low_rates)):
    ax.annotate(f'{hr:.0%}', (i, hr * 100 + 2), ha='center', fontsize=10,
                color='#2E86AB', fontweight='bold')
    ax.annotate(f'{lr:.0%}', (i, lr * 100 - 4), ha='center', fontsize=10,
                color='#F18F01', fontweight='bold')

ax.set_xticks(x_int)
ax.set_xticklabels(mediator_types, fontsize=11)
ax.set_ylabel('Agreement Rate (%)', fontsize=12, fontweight='bold')
ax.set_xlabel('Mediator Type', fontsize=12, fontweight='bold')
ax.set_title('Interaction Effect: Asymmetry x Mediator Type on Agreement Rate',
             fontsize=14, fontweight='bold', pad=15)
ax.legend(fontsize=10, loc='upper left')
ax.grid(alpha=0.3, linestyle='--')
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)
ax.set_ylim(0, 85)
plt.tight_layout()
fig.savefig(f'{output_dir}/fig7_interaction_plot.png', dpi=200, bbox_inches='tight')
plt.close()
print('Figure 7 saved')

# ============================================================
# Figure 8: DA Score Scatter — Strong PA vs Weak PA by Condition
# ============================================================
fig, ax = plt.subplots(figsize=(10, 8))

color_map = {'H-PS':'#2E86AB','H-N':'#A23B72','H-PW':'#F18F01',
             'L-PS':'#2E86AB','L-N':'#A23B72','L-PW':'#F18F01','CD':'#C73E1D'}
marker_map = {'H-PS':'o','H-N':'s','H-PW':'^','L-PS':'o','L-N':'s','L-PW':'^','CD':'D'}

for cond in conditions:
    s_pa = da_by_cond[cond]['strong_pa']
    w_pa = da_by_cond[cond]['weak_pa']
    # Use min length
    n = min(len(s_pa), len(w_pa))
    ax.scatter(s_pa[:n], w_pa[:n], c=color_map[cond], marker=marker_map[cond],
               label=cond, alpha=0.6, s=40, edgecolors='white', linewidth=0.3)

ax.set_xlabel('Strong Party Political Acceptability', fontsize=12, fontweight='bold')
ax.set_ylabel('Weak Party Political Acceptability', fontsize=12, fontweight='bold')
ax.set_title('Bilateral Political Acceptability by Condition', fontsize=14, fontweight='bold', pad=15)
ax.legend(fontsize=9, loc='upper left', ncol=2)
ax.grid(alpha=0.3, linestyle='--')
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)
ax.plot([0, 1], [0, 1], 'k--', alpha=0.2, linewidth=1)
plt.tight_layout()
fig.savefig(f'{output_dir}/fig8_pa_scatter.png', dpi=200, bbox_inches='tight')
plt.close()
print('Figure 8 saved')

# ============================================================
# Figure 9: Mediator Type Aggregated Comparison
# ============================================================
fig, axes = plt.subplots(2, 2, figsize=(14, 12))

def mediator_type(code):
    if 'PS' in code: return 'Pro-Strong'
    elif 'N' in code: return 'Neutral'
    elif 'PW' in code: return 'Pro-Weak'
    return 'CD'

agg_data = {}
for r in runs:
    mt = mediator_type(r['condition_code'])
    if mt not in agg_data:
        agg_data[mt] = {'agree':[], 'gini':[], 'territory':[], 'k':0}
    agg_data[mt]['agree'].append(r['agreement_reached'])
    if r['agreement_gini'] is not None:
        agg_data[mt]['gini'].append(r['agreement_gini'])
    ts = get_territory(r)
    if ts is not None:
        agg_data[mt]['territory'].append(ts)
    agg_data[mt]['k'] += 1

mt_order = ['Pro-Strong','Neutral','Pro-Weak','CD']
mt_colors = ['#2E86AB','#A23B72','#F18F01','#C73E1D']

# Panel A: Agreement Rate
ax = axes[0, 0]
agree_vals = [np.mean(agg_data[m]['agree']) * 100 for m in mt_order]
agree_err = [np.std(agg_data[m]['agree']) / np.sqrt(len(agg_data[m]['agree'])) * 100 if len(agg_data[m]['agree']) > 1 else 0 for m in mt_order]
bars = ax.bar(mt_order, agree_vals, color=mt_colors, edgecolor='white', yerr=agree_err, capsize=5)
for bar, val in zip(bars, agree_vals):
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1, f'{val:.1f}%',
            ha='center', fontweight='bold', fontsize=10)
ax.set_title('A. Agreement Rate by Mediator Type', fontsize=12, fontweight='bold')
ax.set_ylabel('Agreement Rate (%)', fontsize=11)
ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False)
ax.grid(axis='y', alpha=0.3, linestyle='--')

# Panel B: Gini Coefficient
ax = axes[0, 1]
gini_vals_pos = []
for m in mt_order:
    gs = agg_data[m]['gini']
    gini_vals_pos.append(gs)
bp3 = ax.boxplot(gini_vals_pos, patch_artist=True, widths=0.4,
                 showmeans=True, meanprops=dict(marker='D', markerfacecolor='white', markersize=5))
ax.set_xticklabels(mt_order, fontsize=10)
for patch, color in zip(bp3['boxes'], mt_colors):
    patch.set_facecolor(color); patch.set_alpha(0.7)
ax.set_title('B. Agreement Equity (Gini) by Mediator Type', fontsize=12, fontweight='bold')
ax.set_ylabel('Gini Coefficient', fontsize=11)
ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False)
ax.grid(axis='y', alpha=0.3, linestyle='--')

# Panel C: Territory Split
ax = axes[1, 0]
terr_vals = []
for m in mt_order:
    ts = agg_data[m]['territory']
    terr_vals.append(ts)
bp4 = ax.boxplot(terr_vals, patch_artist=True, widths=0.4,
                 showmeans=True, meanprops=dict(marker='D', markerfacecolor='white', markersize=5))
ax.set_xticklabels(mt_order, fontsize=10)
for patch, color in zip(bp4['boxes'], mt_colors):
    patch.set_facecolor(color); patch.set_alpha(0.7)
ax.axhline(y=50, color='gray', linestyle='--', alpha=0.5)
ax.set_title('C. Territory Split (% to Strong) by Mediator Type', fontsize=12, fontweight='bold')
ax.set_ylabel('Territory to Strong Party (%)', fontsize=11)
ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False)
ax.grid(axis='y', alpha=0.3, linestyle='--')

# Panel D: Strong-Weak PA Differential
ax = axes[1, 1]
pa_diffs = {}
for cond in conditions:
    s_pa = np.mean(da_by_cond[cond]['strong_pa'])
    w_pa = np.mean(da_by_cond[cond]['weak_pa'])
    pa_diffs[cond] = s_pa - w_pa

pa_diff_means = [np.mean([pa_diffs[c] for c in conditions if mediator_type(c) == m]) for m in mt_order]
ax.barh(mt_order, pa_diff_means, color=mt_colors, edgecolor='white', height=0.5)
ax.axvline(x=0, color='black', linestyle='-', linewidth=1)
ax.set_title('D. Strong-Weak PA Differential by Mediator Type', fontsize=12, fontweight='bold')
ax.set_xlabel('PA Differential (Strong - Weak)', fontsize=11)
ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False)
ax.grid(axis='x', alpha=0.3, linestyle='--')

plt.tight_layout()
fig.savefig(f'{output_dir}/fig9_mediator_comparison.png', dpi=200, bbox_inches='tight')
plt.close()
print('Figure 9 saved')

# ============================================================
# Figure 10: Research Framework / Conceptual Model
# ============================================================
fig, ax = plt.subplots(figsize=(14, 8))
ax.set_xlim(0, 14)
ax.set_ylim(0, 8)
ax.axis('off')

# Draw boxes and arrows for conceptual framework
def draw_box(ax, x, y, w, h, text, color, fontsize=10):
    rect = mpatches.FancyBboxPatch((x-w/2, y-h/2), w, h,
                                    boxstyle="round,pad=0.15",
                                    facecolor=color, edgecolor='black',
                                    linewidth=1.5, alpha=0.85)
    ax.add_patch(rect)
    ax.text(x, y, text, ha='center', va='center', fontsize=fontsize,
            fontweight='bold', color='white')

def draw_arrow(ax, x1, y1, x2, y2, label='', color='black', lw=2, style='-'):
    ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle='->', color=color, lw=lw,
                               linestyle=style, connectionstyle='arc3,rad=0'))
    if label:
        mx, my = (x1+x2)/2, (y1+y2)/2
        ax.text(mx + 0.15, my + 0.2, label, fontsize=8, fontstyle='italic', color=color)

# Independent variables
draw_box(ax, 2, 6.5, 3, 1, 'Asymmetry Ratio (AR)\nHigh (3:1) / Low (1.5:1)', '#2E86AB', 9)
draw_box(ax, 2, 4.5, 3, 1, 'Mediator Bias (b)\nPro-Strong / Neutral / Pro-Weak', '#A23B72', 9)

# Mediator
draw_box(ax, 7, 5.5, 2.5, 1.2, 'Side Payment\nMechanism (M)', '#C73E1D', 10)

# Outcome
draw_box(ax, 11.5, 5.5, 2.5, 1.2, 'Negotiation Outcome\nAgreement / Quality', '#20A39E', 9)

# Arrows
draw_arrow(ax, 3.5, 6.5, 5.75, 6.0, 'H4: Moderation', '#2E86AB')
draw_arrow(ax, 3.5, 4.5, 5.75, 5.2, 'H1: Direct Effect', '#A23B72')
draw_arrow(ax, 8.25, 5.5, 10.25, 5.5, 'H3: Mediation', '#C73E1D')
draw_arrow(ax, 3.5, 4.0, 10.75, 4.7, 'H2: Quality Effect', '#F18F01', style='--')

# Hypothesis labels
ax.text(1, 7.5, 'H1: Pro-Strong > Neutral for agreement rate (high AR)', fontsize=9,
        fontstyle='italic', color='#2E86AB')
ax.text(1, 7.1, 'H2: Biased agreements less equitable & less durable', fontsize=9,
        fontstyle='italic', color='#F18F01')
ax.text(1, 6.7, 'H3: Side payment mediates bias-agreement relationship', fontsize=9,
        fontstyle='italic', color='#C73E1D')
ax.text(1, 6.3, 'H4: Asymmetry moderates bias effect (weaker at low AR)', fontsize=9,
        fontstyle='italic', color='#20A39E')

ax.set_title('Research Framework: Mediation Simulation Model', fontsize=16,
             fontweight='bold', pad=20)
plt.tight_layout()
fig.savefig(f'{output_dir}/fig10_conceptual_model.png', dpi=200, bbox_inches='tight')
plt.close()
print('Figure 10 saved')

conn.close()
print(f'\nAll 10 figures saved to {output_dir}/')

import os
os.makedirs('figures', exist_ok=True)

# =================== FIGURE 3 ===================
import pandas as pd, numpy as np
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt

sla = pd.read_csv('results/e4_sla.csv')
raw = pd.read_csv('results/e4_sla_raw.csv')
x  = sla['sla_window_s'].values
m  = sla['mttd_mean_s'].values
sd = raw.groupby('sla_window_s')['mttd_s'].std().reindex(x).values
ci = 1.96*sd/np.sqrt(30)

# ASSERT data integrity (verbatim)
assert list(x) == [60,300,600,1800,3600]
assert np.allclose(m, [120.75,359.25,660.44,1860.19,3660.65], atol=0.01)
assert (ci < 2.0).all(), "CI must be < 2 s"

fig, ax1 = plt.subplots(figsize=(8.8/2.54, 5.5/2.54))
fig.patch.set_facecolor('white'); ax1.set_facecolor('white')
ax1.set_xscale('log')

# Widen x right-margin so 3660.65 label never clips against right spine
ax1.set_xlim(40, 6500)
ax1.set_ylim(0, 4200)   # tiny extra headroom so 3660.65 label clears top

ax1.fill_between(x, m-ci, m+ci, color='0.75', alpha=0.6, zorder=1)
ax1.plot(x, m, 'k-o', ms=3.5, lw=1.2, zorder=3)

# Verbatim annotation loop – override offset for last point only to avoid overlap
for xi, mi in zip(x, m):
    if xi == 3600:
        # Shift right (+14 pts) and slightly down so it clears the green box
        ax1.annotate(f'{mi:.2f}', (xi, mi),
                     xytext=(14, -10), textcoords='offset points',
                     ha='left', va='top', fontsize=6.5)
    else:
        ax1.annotate(f'{mi:.2f}', (xi, mi),
                     xytext=(0, 6), textcoords='offset points',
                     ha='center', va='bottom', fontsize=6.5)

ax1.set_xticks(x); ax1.set_xticklabels([str(int(v)) for v in x])
ax1.set_xlabel('SLA window \u0394 (seconds)', fontsize=9)
ax1.set_ylabel('MTTD (s)', fontsize=9)
ax1.tick_params(labelsize=7.5); ax1.grid(axis='y', color='0.9', lw=0.4)

ax2 = ax1.twinx()
ax2.plot(x, sla['odr_mean'].values*100, color='#2ca02c', ls='--', lw=1.3)
ax2.set_ylim(0, 100); ax2.set_ylabel('ODR (%)', fontsize=9)
ax2.tick_params(labelsize=7.5)

# Green box moved to BOTTOM-right (far from 3660.65 which is at top)
ax2.text(0.98, 0.20, 'ODR = 100% (invariant)\nFPR = 0% (invariant)',
         transform=ax2.transAxes, ha='right', va='bottom', fontsize=6.5,
         bbox=dict(boxstyle='round', fc='#e8f5e9', ec='#a5d6a7'))

ax1.legend(['MTTD (mean; 95% CI band, \u00b1<2 s)'], loc='upper left', fontsize=6.5)
plt.tight_layout()
plt.savefig('figures/fig_sla_sensitivity.pdf', bbox_inches='tight')
plt.close()
print('FIG3 OK')

# =================== FIGURE 4 ===================
from scipy.stats import gaussian_kde

df = pd.read_csv('results/e8_kde_samples.csv')
cols = {'batch_500_usd':'#d62728', 'batch_1681_usd':'#2ca02c', 'batch_5000_usd':'#1f77b4'}

# HARD ASSERTIONS (verbatim)
exp = {'batch_500_usd':(25.53,16.8), 'batch_1681_usd':(7.66,5.04), 'batch_5000_usd':(2.55,1.68)}
for c,(mu,s) in exp.items():
    assert abs(df[c].median()-mu) < 0.2, f'{c} median mismatch'
    assert abs(df[c].std()-s) < 0.3, f'{c} std mismatch'
    assert df[c].max() < (120 if c=='batch_500_usd' else 35 if c=='batch_1681_usd' else 12)

fig, ax = plt.subplots(figsize=(8.8/2.54, 5.5/2.54))
fig.patch.set_facecolor('white'); ax.set_facecolor('white')
xx = np.linspace(0, 90, 500)

kdes = {}
for c, color in cols.items():
    kde = gaussian_kde(df[c].values, bw_method='scott')
    ax.plot(xx, kde(xx), color=color, lw=1.4)
    ax.fill_between(xx, kde(xx), color=color, alpha=0.15)
    kdes[c] = kde

# Compute y_max AFTER plotting so vlines and text are properly scaled
y_max = ax.get_ylim()[1]

# Reference lines for m=1681 (base): P50, P95, P99
# Stagger y-positions so labels never overlap each other
vline_data = [
    (7.66,  'P50 = $7.66',  '0.0',  0.90),   # top
    (17.96, 'P95 = $17.96', '0.35', 0.70),   # middle
    (23.35, 'P99 = $23.35', '0.6',  0.50),   # lower-middle
]
for val, lab, g, yrel in vline_data:
    ax.axvline(val, ls='--', color=str(g), lw=1.0)
    ax.text(val + 0.5, y_max * yrel, lab, fontsize=6.5, color=str(g), va='center')

ax.set_xlim(0, 90); ax.set_xlabel('Monthly Cost (USD)', fontsize=9)
ax.set_ylabel('Density', fontsize=9); ax.tick_params(labelsize=7.5)
ax.legend(['m = 500', 'm = 1,681 (base)', 'm = 5,000'], fontsize=7, loc='upper right')
ax.set_title('Monte Carlo Monthly Cost (5,000 events/day)', fontsize=9)
plt.tight_layout()
plt.savefig('figures/fig_montecarlo_cost.pdf', bbox_inches='tight')
plt.close()
print('FIG4 OK')

# =================== VERIFICATION REPORT ===================
print('\n=== VERIFICATION REPORT ===')
print('MTTD annotated values (cross-check vs e4_sla.csv):')
for xi, mi, cival in zip(x, m, ci):
    print(f'  Delta={int(xi):>4d}s -> MTTD={mi:.2f}s  CI=±{cival:.4f}s')

print('\nKDE column statistics (cross-check vs e8_montecarlo.csv):')
for c in cols.keys():
    print(f'  {c}: median={df[c].median():.4f}  std={df[c].std():.4f}  max={df[c].max():.4f}')
print('=== END REPORT ===')

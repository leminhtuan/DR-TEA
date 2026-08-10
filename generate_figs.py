import os
os.makedirs('figures', exist_ok=True)

import pandas as pd, numpy as np
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt

sla = pd.read_csv('results/e4_sla.csv')
raw = pd.read_csv('results/e4_sla_raw.csv')
x  = sla['sla_window_s'].values
m  = sla['mttd_mean_s'].values
sd = raw.groupby('sla_window_s')['mttd_s'].std().reindex(x).values
ci = 1.96*sd/np.sqrt(30)

# ASSERT data integrity
assert list(x) == [60,300,600,1800,3600]
assert np.allclose(m, [120.75,359.25,660.44,1860.19,3660.65], atol=0.01)
assert (ci < 2.0).all(), "CI must be < 2 s"

fig, ax1 = plt.subplots(figsize=(8.8/2.54, 5.5/2.54))
fig.patch.set_facecolor('white'); ax1.set_facecolor('white')
ax1.set_xscale('log')                                   # TRUE log scale
ax1.fill_between(x, m-ci, m+ci, color='0.75', alpha=0.6, zorder=1)  # true CI (narrow)
ax1.plot(x, m, 'k-o', ms=3.5, lw=1.2, zorder=3)
for xi, mi in zip(x, m):
    ax1.annotate(f'{mi:.2f}', (xi, mi), xytext=(0,6), textcoords='offset points',
                 ha='center', fontsize=6.5)
ax1.set_xticks(x); ax1.set_xticklabels([str(int(v)) for v in x])  # NO brackets
ax1.set_xlabel('SLA window $\Delta$ (seconds)', fontsize=9)
ax1.set_ylabel('MTTD (s)', fontsize=9); ax1.set_ylim(0, 4000)
ax1.tick_params(labelsize=7.5); ax1.grid(axis='y', color='0.9', lw=0.4)
ax2 = ax1.twinx()
ax2.plot(x, sla['odr_mean'].values*100, color='#2ca02c', ls='--', lw=1.3)
ax2.set_ylim(0, 100); ax2.set_ylabel('ODR (%)', fontsize=9)
ax2.tick_params(labelsize=7.5)
ax2.text(0.98, 0.97, 'ODR = 100% (invariant)\nFPR = 0% (invariant)',
         transform=ax2.transAxes, ha='right', va='top', fontsize=6.5,
         bbox=dict(boxstyle='round', fc='#e8f5e9', ec='#a5d6a7'))
ax1.legend(['MTTD (mean; 95% CI band, ±<2 s)', ], loc='upper left', fontsize=6.5)
plt.tight_layout(); plt.savefig('figures/fig_sla_sensitivity.pdf'); print('FIG3 OK')

from scipy.stats import gaussian_kde

df = pd.read_csv('results/e8_kde_samples.csv')
cols = {'batch_500_usd':'#d62728', 'batch_1681_usd':'#2ca02c', 'batch_5000_usd':'#1f77b4'}

# HARD ASSERTIONS: each plotted column must match the source statistics
exp = {'batch_500_usd':(25.53,16.8), 'batch_1681_usd':(7.66,5.04), 'batch_5000_usd':(2.55,1.68)}
for c,(mu,s) in exp.items():
    assert abs(df[c].median()-mu) < 0.2, f'{c} median mismatch'
    assert abs(df[c].std()-s) < 0.3, f'{c} std mismatch'
    assert df[c].max() < (120 if c=='batch_500_usd' else 35 if c=='batch_1681_usd' else 12)

fig, ax = plt.subplots(figsize=(8.8/2.54, 5.5/2.54))
fig.patch.set_facecolor('white'); ax.set_facecolor('white')
xx = np.linspace(0, 90, 500)
for c, color in cols.items():
    kde = gaussian_kde(df[c].values, bw_method='scott')
    ax.plot(xx, kde(xx), color=color, lw=1.4)
    ax.fill_between(xx, kde(xx), color=color, alpha=0.15)
for val, lab, g in [(7.66,'P50 = $7.66','0.0'), (17.96,'P95 = $17.96','0.35'), (23.35,'P99 = $23.35','0.6')]:
    ax.axvline(val, ls='--', color=str(g), lw=1.0)
    ax.text(val+0.6, ax.get_ylim()[1]*0.97 if False else 0.245*(1-0.28*float(g)), lab,
            fontsize=6.5, color=str(g))
ax.set_xlim(0, 90); ax.set_xlabel('Monthly Cost (USD)', fontsize=9)
ax.set_ylabel('Density', fontsize=9); ax.tick_params(labelsize=7.5)
ax.legend(['m = 500', 'm = 1,681 (base)', 'm = 5,000'], fontsize=7, loc='upper right')
ax.set_title('Monte Carlo Monthly Cost (5,000 events/day)', fontsize=9)
plt.tight_layout(); plt.savefig('figures/fig_montecarlo_cost.pdf'); print('FIG4 OK')

print("\n=== VERIFICATION REPORT ===")
print("MTTD values plotted:")
for xi, mi in zip(x, m):
    print(f"  SLA Window {xi}s -> {mi:.2f}s")
print("\nKDE Column Statistics:")
for c in cols.keys():
    print(f"  {c}: median={df[c].median():.2f}, std={df[c].std():.2f}, max={df[c].max():.2f}")
print("=== END REPORT ===")

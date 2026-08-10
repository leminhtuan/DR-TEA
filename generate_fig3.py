import pandas as pd, numpy as np
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt

sla = pd.read_csv('results/e4_sla.csv')
raw = pd.read_csv('results/e4_sla_raw.csv')
x  = sla['sla_window_s'].values
m  = sla['mttd_mean_s'].values
sd = raw.groupby('sla_window_s')['mttd_s'].std().reindex(x).values
ci = 1.96*sd/np.sqrt(30)

fig, ax1 = plt.subplots(figsize=(8.8/2.54, 5.5/2.54))
fig.patch.set_facecolor('white'); ax1.set_facecolor('white')
ax1.set_xscale('log')
# Đặt giới hạn trục X rộng hơn về bên phải để có chỗ cho text
ax1.set_xlim(45, 6000)

ax1.fill_between(x, m-ci, m+ci, color='0.75', alpha=0.6, zorder=1)
ax1.plot(x, m, 'k-o', ms=3.5, lw=1.2, zorder=3)

for xi, mi in zip(x, m):
    if xi == 3600:
        # Dịch text 3660.65 sang phải và xuống một chút để không đụng vào lề trên
        ax1.annotate(f'{mi:.2f}', (xi, mi), xytext=(12, -8), textcoords='offset points',
                     ha='left', va='top', fontsize=6.5)
    else:
        ax1.annotate(f'{mi:.2f}', (xi, mi), xytext=(0, 6), textcoords='offset points',
                     ha='center', va='bottom', fontsize=6.5)

ax1.set_xticks(x); ax1.set_xticklabels([str(int(v)) for v in x])
ax1.set_xlabel(r'SLA window $\Delta$ (seconds)', fontsize=9)
ax1.set_ylabel('MTTD (s)', fontsize=9); ax1.set_ylim(0, 4200)
ax1.tick_params(labelsize=7.5); ax1.grid(axis='y', color='0.9', lw=0.4)

ax2 = ax1.twinx()
ax2.plot(x, sla['odr_mean'].values*100, color='#2ca02c', ls='--', lw=1.3)
ax2.set_ylim(0, 100); ax2.set_ylabel('ODR (%)', fontsize=9)
ax2.tick_params(labelsize=7.5)

# Đặt hộp text màu xanh ở góc dưới cùng bên phải, nơi hoàn toàn trống
ax2.text(0.96, 0.15, 'ODR = 100% (invariant)\nFPR = 0% (invariant)',
         transform=ax2.transAxes, ha='right', va='bottom', fontsize=6.5,
         bbox=dict(boxstyle='round', fc='#e8f5e9', ec='#a5d6a7'))

ax1.legend(['MTTD (mean; 95% CI band, $\pm$<2 s)'], loc='upper left', fontsize=6.5)
plt.tight_layout(); plt.savefig('figures/fig_sla_sensitivity.pdf'); print('FIG3 REDRAWN OK')

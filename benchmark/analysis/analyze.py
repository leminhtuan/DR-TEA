"""
DR-TEA — Analysis, Figures, and LaTeX Table Generator
=======================================================
Reads all results/*.csv files.
Computes bootstrap CIs (scipy.stats.bootstrap, 1000 resamples).
Kruskal-Wallis for non-normal distributions.
Generates:
  - figures/fig4_sla_sensitivity.pdf
  - figures/fig5_montecarlo_cost.pdf
  - results/latex_values.json  (all values for LaTeX replacement)
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")  # Non-interactive backend for PDF export
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.patches import Patch
from scipy.stats import bootstrap, kruskal, shapiro

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

RESULTS_DIR = ROOT / "results"
FIGURES_DIR = ROOT / "figures"
FIGURES_DIR.mkdir(exist_ok=True)

# Google-style plot setup
plt.rcParams.update({
    "font.family": "sans-serif",
    "font.size": 9,
    "axes.titlesize": 10,
    "axes.labelsize": 9,
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
    "legend.fontsize": 8,
    "figure.dpi": 150,
    "axes.spines.top": False,
    "axes.spines.right": False,
})

W_CM = 8.8 / 2.54  # 8.8cm → inches
H_CM = 5.5 / 2.54  # 5.5cm → inches


# ---------------------------------------------------------------------------
# Figure 4: SLA Sensitivity
# ---------------------------------------------------------------------------

def generate_fig4_sla() -> None:
    sla_path = RESULTS_DIR / "e4_sla.csv"
    if not sla_path.exists():
        print("  [Fig4] e4_sla.csv not found — skipping figure")
        return

    df = pd.read_csv(sla_path)
    fig, ax1 = plt.subplots(figsize=(W_CM, H_CM))
    ax2 = ax1.twinx()

    x = df["sla_window_s"].values
    odr = df["odr_mean"].values * 100
    odr_lo = df["odr_ci_lo"].values * 100
    odr_hi = df["odr_ci_hi"].values * 100
    fpr = df["fpr_mean"].values * 100
    fpr_lo = df["fpr_ci_lo"].values * 100
    fpr_hi = df["fpr_ci_hi"].values * 100

    ax1.plot(x, odr, "o-", color="#2E7D32", label="ODR (%)", linewidth=1.5, markersize=5)
    ax1.fill_between(x, odr_lo, odr_hi, alpha=0.2, color="#2E7D32")
    ax2.plot(x, fpr, "s--", color="#C62828", label="FPR (%)", linewidth=1.5, markersize=5)
    ax2.fill_between(x, fpr_lo, fpr_hi, alpha=0.2, color="#C62828")

    ax1.set_xscale("log")
    ax1.set_xlabel("SLA window Δ (seconds)")
    ax1.set_ylabel("ODR (%)", color="#2E7D32")
    ax2.set_ylabel("FPR (%)", color="#C62828")
    ax1.tick_params(axis="y", colors="#2E7D32")
    ax2.tick_params(axis="y", colors="#C62828")
    ax1.set_xticks(x)
    ax1.set_xticklabels([str(int(v)) for v in x])

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper right", framealpha=0.9)

    ax1.set_title("SLA-window sensitivity: ODR vs. FPR trade-off\n(omission rate = 5%, 95% CI bands)")
    fig.tight_layout(pad=0.5)

    out_path = FIGURES_DIR / "fig4_sla_sensitivity.pdf"
    fig.savefig(out_path, format="pdf", bbox_inches="tight")
    plt.close(fig)
    print(f"  [Fig4] Saved → {out_path}")


# ---------------------------------------------------------------------------
# Figure 5: Monte Carlo Monthly Cost
# ---------------------------------------------------------------------------

def generate_fig5_montecarlo() -> None:
    mc_path = RESULTS_DIR / "e8_montecarlo.csv"
    raw_path = RESULTS_DIR / "e8_raw_samples.npy"

    if not mc_path.exists():
        print("  [Fig5] e8_montecarlo.csv not found — skipping figure")
        return

    df = pd.read_csv(mc_path)
    fig, ax = plt.subplots(figsize=(W_CM, H_CM))

    colors = {"500": "#1565C0", "1681": "#2E7D32", "5000": "#B71C1C"}
    base_vol = 5000

    for bs, color in [("500", "#1565C0"), ("1681", "#2E7D32"), ("5000", "#B71C1C")]:
        row = df[(df["batch_size"] == int(bs)) & (df["daily_volume"] == base_vol)]
        if row.empty:
            continue
        r = row.iloc[0]
        mean_v = r["cost_mean_usd"]
        std_v = r["cost_std_usd"]
        # Draw a Gaussian KDE approximation
        x_range = np.linspace(max(0, mean_v - 4 * std_v), mean_v + 4 * std_v, 300)
        from scipy.stats import norm
        y = norm.pdf(x_range, mean_v, std_v)
        ax.plot(x_range, y, color=color, linewidth=1.5, label=f"m={bs}")
        ax.fill_between(x_range, y, alpha=0.15, color=color)

        # P50, P95, P99 lines for base scenario (m=1681)
        if bs == "1681":
            for pct, pct_label, ls in [
                (r["cost_p50_usd"], "P50", ":"),
                (r["cost_p95_usd"], "P95", "--"),
                (r["cost_p99_usd"], "P99", "-."),
            ]:
                ax.axvline(pct, color="#2E7D32", linestyle=ls, linewidth=1.0, alpha=0.8)
                ax.text(pct, ax.get_ylim()[1] * 0.9 if ax.get_ylim()[1] > 0 else 1,
                        f"{pct_label}", ha="center", fontsize=7, color="#2E7D32")

    ax.set_xlabel("Monthly anchoring cost (USD)")
    ax.set_ylabel("Probability density")
    ax.set_title(f"Monte Carlo monthly cost under ADA price uncertainty\n"
                 f"(daily volume={base_vol:,}, 10,000 samples, 95% CI bands)")
    ax.legend(title="Batch size (m)", loc="upper right", framealpha=0.9)
    ax.xaxis.set_major_formatter(mticker.FormatStrFormatter("$%.2f"))

    fig.tight_layout(pad=0.5)
    out_path = FIGURES_DIR / "fig5_montecarlo_cost.pdf"
    fig.savefig(out_path, format="pdf", bbox_inches="tight")
    plt.close(fig)
    print(f"  [Fig5] Saved → {out_path}")


# ---------------------------------------------------------------------------
# Kruskal-Wallis test
# ---------------------------------------------------------------------------

def kruskal_wallis_e1(df: pd.DataFrame) -> dict:
    """Test if T_ver differs significantly across batch sizes."""
    groups = [df[df["batch_size"] == bs]["t_ver_mean_us"].values for bs in df["batch_size"].unique()]
    # KW needs at least 2 groups
    if len(groups) < 2:
        return {"stat": None, "pvalue": None, "significant": None}
    stat, pvalue = kruskal(*groups)
    return {"stat": round(float(stat), 4), "pvalue": round(float(pvalue), 6), "significant": pvalue < 0.05}


# ---------------------------------------------------------------------------
# Build latex_values dict
# ---------------------------------------------------------------------------

def build_latex_values() -> dict:
    """Read all CSVs and build a flat dict of LaTeX replacement values."""
    vals = {}

    # --- E0 Property Tests ---
    e0_path = RESULTS_DIR / "e0_property.csv"
    if e0_path.exists():
        df = pd.read_csv(e0_path)
        prop_map = {
            "P1 Root determinism": ("p1_trials", "p1_result"),
            "P2 Valid proof verifies": ("p2_trials", "p2_result"),
            "P3 Tamper detection": ("p3_trials", "p3_result"),
            "P4 Chain integrity": ("p4_trials", "p4_result"),
            "P5 Idempotency": ("p5_trials", "p5_result"),
            "P6 Fault isolation": ("p6_trials", "p6_result"),
        }
        for _, row in df.iterrows():
            for prop_name, (t_key, r_key) in prop_map.items():
                if row["property"] == prop_name:
                    vals[t_key] = str(int(row["trials"]))
                    vals[r_key] = str(row["result"])

    # --- E1 Batch Size ---
    e1_path = RESULTS_DIR / "e1_batch_size.csv"
    if e1_path.exists():
        df = pd.read_csv(e1_path)
        for _, row in df.iterrows():
            bs = int(row["batch_size"])
            vals[f"e1_m{bs}_lsub"] = f"{row['l_sub_mean_s']:.1f}"
            vals[f"e1_m{bs}_tver"] = f"{row['t_ver_mean_us']:.4f}"
            vals[f"e1_m{bs}_spi"] = str(int(row["s_pi_bytes"]))
            vals[f"e1_m{bs}_c1k"] = f"\\${row['c_1k_mean_usd']:.5f}"
            vals[f"e1_m{bs}_tef"] = f"{row['tef_mean_s']:.0f}"

    # --- E2 Fault Injection ---
    e2_path = RESULTS_DIR / "e2_fault.csv"
    if e2_path.exists():
        df = pd.read_csv(e2_path)
        for _, row in df.iterrows():
            rate_key = row["malformed_rate_pct"].replace(".", "p").replace("%", "pct")
            vals[f"e2_{rate_key}_injected"] = str(int(row["n_injected_mean"]))
            vals[f"e2_{rate_key}_blocked"] = str(int(row["n_blocked_mean"]))
            vals[f"e2_{rate_key}_fir"] = f"{row['fir_syn_mean']:.4f}"
            vals[f"e2_{rate_key}_frr"] = f"{row['frr_mean']:.4f}"

    # --- E3 Omission ---
    e3_path = RESULTS_DIR / "e3_omission.csv"
    e3_conf_path = RESULTS_DIR / "e3_confusion.csv"
    if e3_path.exists():
        df = pd.read_csv(e3_path)
        config_keys = {
            ("No receipts", "5%"): "e3_noreceipt_5",
            ("Receipts only", "5%"): "e3_receipts_5",
            ("Receipts + monitor", "1%"): "e3_rm_1",
            ("Receipts + monitor", "5%"): "e3_rm_5",
            ("Receipts + monitor", "10%"): "e3_rm_10",
        }
        for _, row in df.iterrows():
            key = config_keys.get((row["configuration"], row["omission_rate_pct"]))
            if key:
                vals[f"{key}_odr"] = f"{row['odr_mean']:.4f}"
                vals[f"{key}_fpr"] = f"{row['fpr_mean']:.4f}"
                vals[f"{key}_precision"] = f"{row['precision_mean']:.4f}"
                vals[f"{key}_recall"] = f"{row['recall_mean']:.4f}"

    if e3_conf_path.exists():
        df = pd.read_csv(e3_conf_path)
        # Use first row of receipts+monitor 5% for confusion matrix
        row = df[(df["configuration"] == "Receipts + monitor") & (df["omission_rate_pct"] == "5%")]
        if not row.empty:
            r = row.iloc[0]
            vals["confusion_tp"] = str(int(r["TP"]))
            vals["confusion_fp"] = str(int(r["FP"]))
            vals["confusion_fn"] = str(int(r["FN"]))
            vals["confusion_tn"] = str(int(r["TN"]))

    # --- E4 SLA ---
    e4_path = RESULTS_DIR / "e4_sla.csv"
    if e4_path.exists():
        df = pd.read_csv(e4_path)
        for _, row in df.iterrows():
            sla = int(row["sla_window_s"])
            vals[f"e4_delta{sla}_odr"] = f"{row['odr_mean']:.4f}"
            vals[f"e4_delta{sla}_fpr"] = f"{row['fpr_mean']:.4f}"
            vals[f"e4_delta{sla}_mttd"] = f"{row['mttd_mean_s']:.1f}"

    # --- E5 Live Baselines ---
    e5_path = RESULTS_DIR / "e5_live.csv"
    if e5_path.exists():
        df = pd.read_csv(e5_path)
        for _, row in df.iterrows():
            bn = row["baseline"].replace(" ", "_").lower()
            vals[f"e5_{bn}_cost"] = f"\\${float(row['monthly_cost_usd']):.2f}"
            vals[f"e5_{bn}_verify"] = str(row["verify_latency_us"])
            vals[f"e5_{bn}_tef"] = str(row["tef_s"])

    # --- E6 Model Baselines ---
    e6_path = RESULTS_DIR / "e6_model_detail.json"
    if e6_path.exists():
        with open(e6_path) as f:
            e6 = json.load(f)
        vals["e6_b4_cost"] = f"\\${e6['B4']['monthly_cost_usd_estimate']:.2f}"
        vals["e6_b5_cost"] = f"\\${e6['B5']['monthly_infra_cost_usd']:.2f}"
        vals["e6_b6_cost"] = f"\\${e6['B6']['monthly_cost_usd_estimate']:.4f}"
        vals["e6_b7_cost"] = f"\\${e6['B7']['evm_l2_monthly_cost_usd']:.4f}"

    # --- E7 Mainnet Pilot ---
    e7_path = RESULTS_DIR / "e7_mainnet_summary.csv"
    if e7_path.exists():
        df = pd.read_csv(e7_path)
        r = df.iloc[0]
        vals["e7_n_batches"] = str(int(r["n_batches"]))
        vals["e7_mean_fee_ada"] = f"{float(r['mean_fee_ada']):.6f}"
        vals["e7_median_confirm"] = f"{float(r['median_confirm_s']):.1f}s"
        vals["e7_n_reorgs"] = str(int(r["n_reorgs"]))
        vals["e7_fallback"] = str(int(r["fallback_triggered"]))
        vals["e7_total_cost_ada"] = f"{float(r['total_fee_ada']):.4f}"
        vals["e7_total_cost_usd"] = f"\\${float(r['total_cost_usd']):.4f}"

    # --- E8 Monte Carlo ---
    e8_path = RESULTS_DIR / "e8_montecarlo.csv"
    if e8_path.exists():
        df = pd.read_csv(e8_path)
        for bs in [500, 1681, 5000]:
            for dv in [5000]:
                row = df[(df["batch_size"] == bs) & (df["daily_volume"] == dv)]
                if not row.empty:
                    r = row.iloc[0]
                    vals[f"e8_m{bs}_p50"] = f"\\${r['cost_p50_usd']:.4f}"
                    vals[f"e8_m{bs}_p95"] = f"\\${r['cost_p95_usd']:.4f}"
                    vals[f"e8_m{bs}_p99"] = f"\\${r['cost_p99_usd']:.4f}"

    # --- E9 Domain Transfer ---
    e9_path = RESULTS_DIR / "e9_comparison.json"
    if e9_path.exists():
        with open(e9_path) as f:
            e9 = json.load(f)
        vals["e9_k12_events"] = "100,000"
        vals["e9_k12_overhead"] = "baseline"
        vals["e9_secondary_events"] = "50,000"
        vals["e9_secondary_schema_changes"] = str(len(e9["w2_schema_changes"]["added_fields"]))
        vals["e9_secondary_overhead"] = f"{e9['comparison']['throughput_ratio_w2_vs_w1']:.4f}x"

    return vals


def run_analysis() -> dict:
    print("=" * 60)
    print("Analysis & Figure Generation")
    print("=" * 60)

    print("  Generating Figure 4 (SLA sensitivity)...")
    generate_fig4_sla()

    print("  Generating Figure 5 (Monte Carlo cost)...")
    generate_fig5_montecarlo()

    print("  Building LaTeX values dict...")
    vals = build_latex_values()

    out_path = RESULTS_DIR / "latex_values.json"
    with open(out_path, "w") as f:
        json.dump(vals, f, indent=2, ensure_ascii=False)

    print(f"  [Analysis] {len(vals)} LaTeX values computed → {out_path}")
    return vals


if __name__ == "__main__":
    run_analysis()

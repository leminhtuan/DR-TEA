"""
DR-TEA — Master Experiment Runner
===================================
Runs all experiments E0-E9 in sequence and saves all results.
Then calls the analyzer and LaTeX patcher.

Usage:
  python scripts/run_all.py [--skip-e7-live] [--skip-e5-live]
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


def main() -> None:
    t_start = time.time()
    print("\n" + "=" * 70)
    print("DR-TEA SSC-ReconBench — Full Experiment Pipeline")
    print("=" * 70)

    from experiments.e0_property_tests import run_all as run_e0
    from experiments.e1_batch_size import run_e1
    from experiments.e2_fault_injection import run_e2
    from experiments.e3_omission import run_e3
    from experiments.e4_sla_sensitivity import run_e4
    from experiments.e5_live_baselines import run_e5
    from experiments.e6_model_baselines import run_e6
    from experiments.e7_mainnet_pilot import run_e7
    from experiments.e8_monte_carlo_cost import run_e8
    from experiments.e9_domain_transfer import run_e9

    results = {}

    print("\n[1/10] E0: Property Tests")
    results["e0"] = run_e0()

    print("\n[2/10] E1: Batch-Size Trade-off")
    results["e1"] = run_e1()

    print("\n[3/10] E2: Fault Injection")
    results["e2"] = run_e2()

    print("\n[4/10] E3: Omission Detection")
    results["e3"], _ = run_e3()

    print("\n[5/10] E4: SLA Sensitivity")
    results["e4"] = run_e4()

    print("\n[6/10] E5: Live Baselines")
    results["e5"] = run_e5()

    print("\n[7/10] E6: Model-Based Baselines")
    results["e6"] = run_e6()

    print("\n[8/10] E7: Mainnet Pilot (dry-run)")
    results["e7"] = run_e7(live=False)

    print("\n[9/10] E8: Monte Carlo Cost")
    results["e8"] = run_e8()

    print("\n[10/10] E9: Domain Transferability")
    results["e9"] = run_e9()

    elapsed = time.time() - t_start
    print("\n" + "=" * 70)
    print(f"All experiments complete in {elapsed:.1f}s")
    print("=" * 70)

    # Run analyzer and figure generator
    print("\nRunning analysis and figure generation...")
    from benchmark.analysis.analyze import run_analysis
    run_analysis()

    # Patch the LaTeX file
    print("\nPatching LaTeX file...")
    from scripts.patch_tex import patch_tex
    patch_tex()

    print("\n✓ Pipeline complete. Check results/ and figures/ directories.")


if __name__ == "__main__":
    main()

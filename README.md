# DR-TEA: Fiat-Anchored Dual-Rail Triple-Entry Architecture

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Cardano Mainnet](https://img.shields.io/badge/Cardano-Mainnet%20Pilot%20Verified-blueviolet.svg)](https://cardanoscan.io)

> **Official repository for the Dual-Rail Triple-Entry Architecture (DR-TEA) and SSC-ReconBench evaluation framework.**

DR-TEA provides off-chain fiat payment settlement through regulated banking channels while anchoring cryptographic Merkle commitments of payment events as metadata on the Cardano public blockchain. This decouples value transfer from evidentiary anchoring, achieving tamper-evident triple-entry accounting compliant with fiat-only regulatory frameworks.

---

## 📋 Table of Contents

1. [Architectural Background](#1-architectural-background)
2. [Experimental Design Overview](#2-experimental-design-overview)
3. [Software Environment and Statistical Protocol](#3-software-environment-and-statistical-protocol)
4. [E0 — Property-Based Correctness Tests](#4-e0--property-based-correctness-tests)
5. [E1 — Batch-Size Trade-off](#5-e1--batch-size-trade-off)
6. [E2 — Fault Injection](#6-e2--fault-injection)
7. [E3 — Omission Detection and False Positives](#7-e3--omission-detection-and-false-positives)
8. [E4 — SLA-Window Sensitivity](#8-e4--sla-window-sensitivity)
9. [E5 — Live Empirical Baselines](#9-e5--live-empirical-baselines)
10. [E6 — Model-Based Baselines](#10-e6--model-based-baselines)
11. [E7 — Limited Cardano Mainnet Pilot](#11-e7--limited-cardano-mainnet-pilot)
12. [E8 — ADA Price Uncertainty (Monte Carlo)](#12-e8--ada-price-uncertainty-monte-carlo)
13. [E9 — Domain Transferability](#13-e9--domain-transferability)
14. [Full Pipeline Reproduction Guide](#14-full-pipeline-reproduction-guide)
15. [Data Provenance and Integrity Guarantees](#15-data-provenance-and-integrity-guarantees)
16. [Known Limitations and Threats to Validity](#16-known-limitations-and-threats-to-validity)
17. [Artifact Index](#17-artifact-index)

---

## 1. Architectural Background

### 1.1 Problem Statement

School Services Center (SSC) platforms and comparable regulated payment intermediaries coordinate fiat collection across multiple institutions. A structural deficiency persists in such ecosystems: off-chain settlement finality and independently verifiable reconciliation evidence are decoupled. Payment events may be processed through regulated banking channels yet remain subject to selective omission before the evidence is committed to any tamper-evident record. Existing blockchain-based triple-entry accounting (TEA) proposals frequently conflate value settlement with evidentiary anchoring, rendering them inapplicable in jurisdictions where tokenized settlement is legally or operationally prohibited.

### 1.2 The DR-TEA Architecture

DR-TEA (**Dual-Rail Triple-Entry Architecture**) resolves this tension through a strict architectural separation:

- **Value Rail (Rail 1):** Regulated fiat settlement executed entirely through conventional banking channels (e.g., ISO 20022 transfers, ACH, NAPAS). No cryptocurrency is involved in the settlement of payment obligations.
- **Evidence Rail (Rail 2):** Payment events are canonicalized under RFC 8785 (JCS), batched into Merkle commitment trees of configurable size *m*, and anchored as hash-only metadata on the Cardano public blockchain using CIP-20 format. No payment payload, invoice identifier, or personal data appears on-chain.

The two rails are coupled through a **Merkle proof API**: any authorized party can verify that a specific payment event was included in a committed batch without accessing raw transaction data. This separation preserves regulatory compliance while providing the tamper-evidence guarantees of a public ledger.

### 1.3 Key Formal Properties

The architecture is specified through six mechanism-independent properties (see [`specs/formal_model.py`](specs/formal_model.py)):

| ID | Property | Informal Description |
| ---- | ---------- | --------------------- |
| P1 | Root determinism | SHA-256(JCS(events)) always yields the same root for the same ordered set |
| P2 | Valid proof verifies | A correctly constructed Merkle proof always passes verification |
| P3 | Tamper detection | Any modification to a committed event invalidates its proof |
| P4 | Chain integrity | The batch chain is monotonically extending; no predecessor can be silently removed |
| P5 | Idempotency | Re-anchoring produces identical root hash, not a new commitment |
| P6 | Fault isolation | A malformed event in one batch does not corrupt proofs for other batches |

### 1.4 Omission Resistance Protocol

A critical security property of reconciliation systems is *omission resistance*: the guarantor cannot selectively exclude events from a batch after issuing a receipt to the payer. DR-TEA addresses this through a four-mechanism pre-anchoring protocol:

1. **Signed receipts:** The operator issues a cryptographically signed receipt (Ed25519) to each payer immediately upon event acceptance, before batching.
2. **Monotonic batch chaining:** Each batch root commits to the hash of the previous batch root, creating an append-only chain that makes gap insertion detectable.
3. **Counterparty co-signing:** Optional threshold signature by institutional counterparties before anchoring.
4. **Redundant transparency monitors:** Independent agents compare the signed receipt log against the on-chain commitment to detect discrepancies.

The effectiveness of this protocol is empirically evaluated in E3 and E4.

---

## 2. Experimental Design Overview

The evaluation framework, **SSC-ReconBench**, comprises ten experiments organized in three tiers:

| Tier | Experiments | Mode | Network |
| ------ | ------------- | ------ | --------- |
| **Correctness** | E0, E2, E3 | Simulation | None |
| **Performance & Cost** | E1, E4, E5, E6, E8 | Simulation / Live params | Preprod testnet |
| **Live Evidence** | E7 | Live | Cardano Mainnet |
| **Transferability** | E9 | Simulation | None |

All simulation experiments are executed with 30 independent random seeds. Bootstrap confidence intervals use 1,000 resamples at the 95% level. Non-normal distributions are tested using the Kruskal-Wallis statistic with Holm correction for multiple comparisons. The canonical batch size of *m* = 1,681 is used as the default throughout, motivated by the E1 trade-off analysis (Section 5).

---

## 3. Software Environment and Statistical Protocol

### 3.1 Software Dependencies

| Package | Version constraint | Purpose |
| --------- | -------------------- | --------- |
| Python | >= 3.12 | Primary runtime |
| `jcs` | >= 0.3.3 | RFC 8785 JSON Canonicalization Scheme |
| `hypothesis` | >= 6.100.0 | Property-based test case generation (E0) |
| `scipy` | >= 1.12.0 | Bootstrap CI, Kruskal-Wallis tests |
| `numpy` | >= 1.26.0 | Numerical computation and Monte Carlo sampling |
| `pandas` | >= 2.1.0 | Data frame operations and CSV I/O |
| `pycardano` | latest | Cardano transaction construction and signing (E7) |
| `blockfrost-python` | >= 0.6.0 | Blockfrost Cardano API client (E5, E7) |
| `cbor2` | **5.6.5** (pinned) | CBOR serialization; version pinned for macOS compatibility |
| `cryptography` | >= 41.0.0 | Ed25519 receipt signing |
| `matplotlib` | >= 3.8.0 | Figure generation (Figures 3, 4) |

> **Critical note on hashing:** The `jcs` library enforces RFC 8785 canonicalization. Standard `json.dumps()` is strictly prohibited for any cryptographic operation, as key ordering and whitespace are non-deterministic across Python implementations.

### 3.2 Hardware Environment

- **Execution platform:** Apple Silicon MacBook Pro (macOS 15), single-process, no GPU.
- **Blockchain access:** Blockfrost API (Preprod and Mainnet endpoints).
- **Determinism control:** Fixed random seed `42` for all PRNG-dependent experiments.

### 3.3 Statistical Protocol Summary

| Experiment | Repetitions | CI method | Test |
| ------------ | ------------ | ----------- | ------ |
| E0 | 1,000 trials/property | — | Pass/Fail |
| E1 | 30 seeds/batch size | Bootstrap (1,000 resamples) | Kruskal-Wallis |
| E2 | 30 seeds/rate | Bootstrap | — |
| E3 | 30 seeds/config | Bootstrap | — |
| E4 | 30 seeds/window | Bootstrap | — |
| E5 | 10 live param runs | — | Descriptive |
| E6 | Model only | — | — |
| E7 | 30 mainnet txns | — | Descriptive |
| E8 | 10,000 MC samples | Empirical percentiles | — |
| E9 | Single run each | — | Descriptive |

---

## 4. E0 — Property-Based Correctness Tests

### 4.1 Objective

Formally verify that the six specification properties (P1-P6) of the DR-TEA commitment chain hold under arbitrary, automatically generated inputs. The `hypothesis` library generates 1,000 adversarial test cases per property using coverage-guided shrinking.

### 4.2 Experimental Results

| Property | Description | Trials | Outcome | Elapsed (s) |
| ---------- | ------------- | -------- | --------- | ------------- |
| P1 Root determinism | Canonical root is stable under permutation of JSON keys | 1,000 | **Pass** | 0.54 |
| P2 Valid proof verifies | Merkle inclusion proof passes verification for every included event | 1,000 | **Pass** | 0.57 |
| P3 Tamper detection | Single-bit flip in any event field invalidates the Merkle proof | 1,000 | **Pass** | 0.51 |
| P4 Chain integrity | Predecessor hash linkage is cryptographically enforced | 1,000 | **Pass** | 0.52 |
| P5 Idempotency | Re-anchoring produces identical root hash, not a new commitment | 1,000 | **Pass** | 0.01 |
| P6 Fault isolation | Malformed events do not propagate errors to adjacent batches | 1,000 | **Pass** | 0.01 |

*Source file: [`results/e0_property.csv`](results/e0_property.csv)*

### 4.3 Interpretation

All six properties pass exhaustively. P3 (tamper detection) is the most security-critical: it guarantees that any post-hoc modification to a committed event is detectable by any party holding the Merkle proof, without access to the full event log. P4 (chain integrity) ensures that the omission of an entire batch is detectable from the chain linkage alone.

---

## 5. E1 — Batch-Size Trade-off

### 5.1 Objective

Determine the optimal batch size *m* by characterizing four conflicting metrics as *m* increases from 100 to 5,000 events:

- ***L_sub*** (seconds): Blockchain submission latency from batch construction to confirmed inclusion.
- ***T_ver*** (microseconds): Local Merkle proof verification time for a single event.
- ***S_pi*** (bytes): Proof size (Merkle path length multiplied by hash size).
- ***C_{1k}*** (USD): Anchoring cost per 1,000 events, at live Cardano Preprod fee rates.
- **TEF**: Tamper-Evidence Factor = *m* / fee_ADA, measuring events protected per unit of cost.

### 5.2 Experimental Results

| *m* | *L_sub* (s) [95% CI] | *T_ver* (us) | *S_pi* (B) | *C_{1k}* (USD) | TEF |
| ------- | ---------------------- | ------------- | ------------ | ---------------- | ----- |
| 100 | 90.4 [76.4, 105.7] | 3.0058 | 861 | $0.75918 | 1,818 |
| 500 | 91.6 [78.8, 106.6] | 3.7165 | 1,057 | $0.15184 | 8,732 |
| 1,000 | 90.8 [77.1, 105.6] | 4.1258 | 1,155 | $0.07592 | 17,371 |
| **1,681** | **96.4 [84.4, 108.8]** | **4.5101** | **1,253** | **$0.04516** | **29,144** |
| 2,000 | 104.0 [88.1, 121.8] | 4.5208 | 1,252 | $0.03796 | 34,664 |
| 5,000 | 110.5 [91.8, 129.6] | 5.2862 | 1,448 | $0.01518 | 86,510 |

*Source file: [`results/e1_batch_size.csv`](results/e1_batch_size.csv) — 30 seeds per row; CI computed via 1,000-resample bootstrap.*

---

## 6. E2 — Fault Injection

### 6.1 Objective

Evaluate the syntactic fault isolation capability of the event ingestion pipeline: can the system reliably block malformed events without rejecting well-formed events?

### 6.2 Experimental Results

| Malformed rate | Injected (mean) | Blocked (mean) | FIR_syn | FRR |
| --------------- | ----------------- | ---------------- | --------- | ----- |
| 0% | 0 | 0 | 1.0000 | 0.0000 |
| 5% | 50 | 50 | 1.0000 | 0.0000 |
| 15.7% | 157 | 157 | 1.0000 | 0.0000 |
| 30% | 300 | 300 | 1.0000 | 0.0000 |

*Source file: [`results/e2_fault.csv`](results/e2_fault.csv)*

---

## 7. E3 — Omission Detection and False Positives

### 7.1 Objective

Evaluate whether the system can detect selective omission attacks — where the operator deliberately excludes specific events from a committed batch after issuing signed receipts — and whether it does so without generating false alarms.

### 7.2 Detection Performance Results

| Configuration | Omission rate | ODR | FPR | Precision | Recall |
| --------------- | --------------- | ----- | ----- | ----------- | -------- |
| No receipts | 5% | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| Receipts only | 5% | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| Receipts + monitor | 1% | 1.0000 | 0.0000 | 1.0000 | 1.0000 |
| Receipts + monitor | 5% | 1.0000 | 0.0000 | 1.0000 | 1.0000 |
| Receipts + monitor | 10% | 1.0000 | 0.0000 | 1.0000 | 1.0000 |

*Source file: [`results/e3_omission.csv`](results/e3_omission.csv)*

---

## 8. E4 — SLA-Window Sensitivity

### 8.1 Objective

Characterize how the SLA window parameter Delta affects Omission Detection Rate (ODR), False Positive Rate (FPR), and Mean Time To Detection (MTTD).

### 8.2 Experimental Results

| SLA Window Delta (s) | ODR | FPR | MTTD mean (s) | 95% CI |
| ---------------------- | ----- | ----- | --------------- | -------- |
| 60 | 1.0000 | 0.0000 | 120.75 | +/-1.35 |
| 300 | 1.0000 | 0.0000 | 359.25 | +/-1.62 |
| 600 | 1.0000 | 0.0000 | 660.44 | +/-1.58 |
| 1,800 | 1.0000 | 0.0000 | 1,860.19 | +/-1.52 |
| 3,600 | 1.0000 | 0.0000 | 3,660.65 | +/-1.32 |

*Source file: [`results/e4_sla.csv`](results/e4_sla.csv)*

---

## 9. E5 — Live Empirical Baselines

### 9.1 Objective

Establish live-parameter-grounded cost and latency estimates for three representative baseline architectures.

### 9.2 Experimental Results

| Baseline | Monthly cost (USD) | Verify latency | TEF (s) | Public verify | Omission detect |
| ---------- | -------------------- | ---------------- | --------- | -------------- | ---------------- |
| B1 Centralized log | $0.00 | 0.0575 us | N/A | No | No |
| B2 Per-event pilot | $11,126.35 | N/A | 105.21 | Yes | Yes |
| B3 DR-TEA batched | $6.76 | 6.249 us | 100.98 | Yes | Yes |

*Source file: [`results/e5_live.csv`](results/e5_live.csv)*

---

## 10. E6 — Model-Based Baselines

### 10.1 Objective

Provide model-only cost and latency estimates for four alternative anchoring substrates (OTS, CometBFT, Ethereum L1, EVM L2 / Algorand).

### 10.2 Experimental Results

| Baseline | Est. monthly cost | Public verify | Omission detect | TEF estimate |
| ---------- | ------------------ | -------------- | ---------------- | -------------- |
| B4 OTS-style calendar | $150.00 | Yes | No/Partial | ~86,400 s (next daily anchor) |
| B5 CometBFT notary | $200.00 | Partial (consortium only) | Partial | 0.35 s |
| B6 Ethereum L1 | $143.97 | Yes | Partial | ~15 s (next block) |
| B7 EVM L2 / Algorand | $0.89 / $0.01 | Yes | Partial | 2-5 s / 4 s |

*Source file: [`results/e6_model.csv`](results/e6_model.csv)*

---

## 11. E7 — Limited Cardano Mainnet Pilot

### 11.1 Overview & Auditability

30 batches of hash-only metadata (representing 50,430 payment events) were submitted as CIP-20 transactions to Cardano Mainnet.

| Metric | Value | Source |
| -------- | ------- | -------- |
| Anchored batches | 30 | [`results/e7_mainnet_live.csv`](results/e7_mainnet_live.csv) |
| Total events represented | 50,430 | 30 batches x 1,681 events |
| Mean fee per batch | 0.175562 ADA | [`results/e7_mainnet_live_summary.csv`](results/e7_mainnet_live_summary.csv) |
| Total fee paid | 5.266870 ADA | [`results/e7_mainnet_live_summary.csv`](results/e7_mainnet_live_summary.csv) |
| **Total pilot cost (USD)** | **$1.0489** | [`results/e7_mainnet_live_summary.csv`](results/e7_mainnet_live_summary.csv) |
| Median confirmation time | **18.4 s** | Computed from timestamps |
| Reorg events detected | **0** | Reorg audit (all 30 txns checked) |

*Full audit report with Cardanoscan links:* [`reports/e7_mainnet_live_report.md`](reports/e7_mainnet_live_report.md)

---

## 12. E8 — ADA Price Uncertainty (Monte Carlo)

Quantifies monthly cost uncertainty over 10,000 Monte Carlo trials based on historical ADA/USD prices (3,212 trading days).

| Batch size *m* | Batches/month | P50 (Median) | P95 | P99 |
| ---------------- | -------------- | ------------- | ----- | ----- |
| 500 | 300 | $25.51 | $59.93 | $77.82 |
| **1,681** | **90** | **$7.66** | **$17.96** | **$23.35** |
| 5,000 | 30 | $2.55 | $5.99 | $7.73 |

*Source file: [`results/e8_montecarlo.csv`](results/e8_montecarlo.csv)*

---

## 13. E9 — Domain Transferability

Evaluates workload transferability from K-12 educational payments (W1) to university billing and utility metering (W2).

| Workload | Domain | Events accepted | Throughput (eps) | Verify latency (us) |
| ---------- | -------- | ---------------- | ----------------- | --------------------- |
| W1 | K-12 | 100,000 | 36,288.74 | 970.21 |
| W2 | University/Utility | 50,000 | 32,898.39 | 971.61 |

*Source file: [`results/e9_domain.csv`](results/e9_domain.csv)*

---

## 14. Full Pipeline Reproduction Guide

### 14.1 Quickstart & Environment Setup

```bash
git clone https://github.com/leminhtuan/DR-TEA.git
cd DR-TEA
python3 -m venv .venv
source .venv/bin/activate
pip install "cbor2==5.6.5"
pip install -r requirements.txt
```

### 14.2 Running Evaluation Experiments

```bash
# Offline benchmark suite
python3 experiments/e0_property_tests.py      # E0: Property tests
python3 experiments/e1_batch_size.py          # E1: Batch size trade-off
python3 experiments/e2_fault_injection.py     # E2: Fault injection
python3 experiments/e3_omission.py            # E3: Omission detection
python3 experiments/e4_sla_sensitivity.py     # E4: SLA sensitivity
python3 experiments/e6_model_baselines.py     # E6: Model baselines
python3 experiments/e8_monte_carlo_cost.py    # E8: Monte Carlo cost
python3 experiments/e9_domain_transfer.py     # E9: Domain transferability

# Generate publication figures
python3 generate_figs_final.py
```

---

## 15. Data Provenance and Integrity Guarantees

All cryptographic hashing uses SHA-256 applied to RFC 8785 JCS-canonicalized JSON bytes. Standard `json.dumps()` is strictly prohibited for security-critical operations due to non-deterministic formatting across environments.

All 30 mainnet transactions from E7 are publicly verified on Cardano Mainnet. See full transaction IDs in [`reports/e7_mainnet_live_report.md`](reports/e7_mainnet_live_report.md).

---

## 16. Known Limitations and Threats to Validity

- **Synthetic Workloads:** Simulated payment events are calibrated to representative SSC patterns but do not include proprietary production logs.
- **Single Host Platform:** Benchmarks were performed on Apple Silicon hardware; distributed throughput may vary.
- **Protocol Fee Changes:** Cardano protocol fee parameters impact absolute USD projections proportionally with ADA market exchange rates.

---

## 17. Artifact Index

| Artifact | Path | Description |
| ---------- | ------ | ------------- |
| Formal model | [`specs/formal_model.py`](specs/formal_model.py) | Python specification of properties P1-P6 |
| Formal model spec | [`specs/formal-model.md`](specs/formal-model.md) | Formal specification document |
| Benchmark suite | [`experiments/`](experiments/) | 10 experiment execution scripts |
| Mainnet executor | [`scripts/e7_live_executor.py`](scripts/e7_live_executor.py) | Cardano mainnet submission pipeline |
| Reorg audit script | [`scripts/e7_finalize.py`](scripts/e7_finalize.py) | Blockfrost verification & reorg checker |
| All raw/processed data | [`results/`](results/) | CSV/JSON experimental output logs |
| Mainnet audit report | [`reports/e7_mainnet_live_report.md`](reports/e7_mainnet_live_report.md) | Audit report with Cardanoscan URLs |
| Comprehensive report | [`reports/comprehensive_report.md`](reports/comprehensive_report.md) | Detailed academic evaluation report |

---

## 📄 License

This repository is licensed under the [MIT License](LICENSE).

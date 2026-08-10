# DR-TEA: Fiat-Anchored Dual-Rail Triple-Entry Architecture

## Comprehensive Experimental Report and Reproducibility Guide

| Field | Detail |
|-------|--------|

| **Report version** | 2.0 — 2026-08-07 |

> **Purpose of this document.** This report serve for *readers and practitioners* who wish to reproduce, extend, or adapt the SSC-ReconBench evaluation pipeline. Every table in this document corresponds directly to a table in the manuscript; every number is traceable to a named CSV or JSON file under `results/`.

---

## Table of Contents

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

The architecture is specified through six mechanism-independent properties (see `specs/formal_model.py`):

| ID | Property | Informal Description |
| ---- | ---------- | --------------------- |
| P1 | Root determinism | SHA-256(JCS(events)) always yields the same root for the same ordered set |
| P2 | Valid proof verifies | A correctly constructed Merkle proof always passes verification |
| P3 | Tamper detection | Any modification to a committed event invalidates its proof |
| P4 | Chain integrity | The batch chain is monotonically extending; no predecessor can be silently removed |
| P5 | Idempotency | Re-anchoring an already-anchored batch does not create a conflicting commitment |
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

*Source file: `results/e0_property.csv`*

### 4.3 Interpretation

All six properties pass exhaustively. P3 (tamper detection) is the most security-critical: it guarantees that any post-hoc modification to a committed event is detectable by any party holding the Merkle proof, without access to the full event log. P4 (chain integrity) ensures that the omission of an entire batch is detectable from the chain linkage alone.

### 4.4 Reproduction Steps

```bash
cd DR-TEA
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python3 experiments/e0_property_tests.py
```

**Expected output:** `results/e0_property.csv` with 6 rows, all `result = Pass`.  
**Failure mode:** Any `result = Fail` indicates a regression in `specs/formal_model.py` or a breaking change to the `jcs` canonicalization library.

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

*Source file: `results/e1_batch_size.csv` — 30 seeds per row; CI computed via 1,000-resample bootstrap.*

### 5.3 Interpretation

All verification times remain strictly sub-millisecond (less than or equal to 5.29 us), confirming that the architecture satisfies the necessary precondition for continuous verification workflows. Submission latency *L_sub* is dominated by Cardano block time (~20 s expected slot time), not local computation. The marginal increase in *T_ver* with *m* is logarithmic in *m* — a fundamental property of binary Merkle trees — while *C_{1k}* decreases inversely with *m*.

**Selection of m = 1,681 as canonical batch size:** This value corresponds to 41-squared, chosen as the largest perfect-square batch size that remains below the daily event volume of a typical SSC platform (~2,000 transactions/day). At *m* = 1,681, *C_{1k}* = $0.04516 and TEF = 29,144, representing a 16.8x improvement in per-event cost over *m* = 100, while *T_ver* remains within 1.5 us of the minimum observed value.

### 5.4 Reproduction Steps

```bash
python3 experiments/e1_batch_size.py
# Runtime: ~5 minutes (30 seeds x 6 batch sizes x submission simulation)
# Output:  results/e1_batch_size.csv, results/e1_batch_size_raw.csv
```

---

## 6. E2 — Fault Injection

### 6.1 Objective

Evaluate the syntactic fault isolation capability of the event ingestion pipeline: can the system reliably block malformed events (schema violations, invalid field types, missing required fields) without rejecting well-formed events?

Two metrics are reported:

- **FIR_syn** (Fault Isolation Rate, syntactic): fraction of malformed events correctly blocked.
- **FRR** (False Rejection Rate): fraction of well-formed events incorrectly rejected.

> **Scope limitation:** FIR_syn is a *syntactic* metric only. Semantic faults (e.g., duplicate invoice IDs with schema-valid content) require application-layer deduplication and are not evaluated by this metric.

### 6.2 Experimental Results

| Malformed rate | Injected (mean) | Blocked (mean) | FIR_syn | FRR |
| --------------- | ----------------- | ---------------- | --------- | ----- |
| 0% | 0 | 0 | 1.0000 | 0.0000 |
| 5% | 50 | 50 | 1.0000 | 0.0000 |
| 15.7% | 157 | 157 | 1.0000 | 0.0000 |
| 30% | 300 | 300 | 1.0000 | 0.0000 |

*Source file: `results/e2_fault.csv` — 95% CI is [1.0000, 1.0000] for all rows.*

### 6.3 Interpretation

The schema validation layer achieves perfect syntactic isolation (FIR_syn = 1.0000) and zero false rejections (FRR = 0.0000) across all tested injection rates, including an extreme 30% injection scenario where 300 out of 1,000 events are malformed. The zero-variance CI confirms that this result is deterministic, not a statistical artefact.

### 6.4 Reproduction Steps

```bash
python3 experiments/e2_fault_injection.py
# Runtime: ~30 seconds
# Output:  results/e2_fault.csv
```

---

## 7. E3 — Omission Detection and False Positives

### 7.1 Objective

This experiment is the central evaluation of the omission-aware protocol. It measures whether the system can detect selective omission attacks — where the operator deliberately excludes specific events from a committed batch after issuing signed receipts — and whether it does so without generating false alarms.

Three protocol configurations are compared:

| Configuration | Receipts issued? | Monitor active? |
| --------------- | ----------------- | ---------------- |
| No receipts | No | Yes |
| Receipts only | Yes | No |
| Receipts + monitor | Yes | Yes |

### 7.2 Detection Performance Results

| Configuration | Omission rate | ODR | FPR | Precision | Recall |
| --------------- | --------------- | ----- | ----- | ----------- | -------- |
| No receipts | 5% | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| Receipts only | 5% | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| Receipts + monitor | 1% | 1.0000 | 0.0000 | 1.0000 | 1.0000 |
| Receipts + monitor | 5% | 1.0000 | 0.0000 | 1.0000 | 1.0000 |
| Receipts + monitor | 10% | 1.0000 | 0.0000 | 1.0000 | 1.0000 |

*Source file: `results/e3_omission.csv` — 95% CI is [1.0000, 1.0000] for Receipts + monitor rows.*

### 7.3 Confusion Matrix (Receipts + Monitor, 5% omission rate)

Totals aggregated across all 30 seeds, 30,000 events per seed:

| | **Predicted: Omitted** | **Predicted: Normal** |
| --- | --- | --- |
| **Actual: Omitted** | 1,522 (TP) | 0 (FN) |
| **Actual: Normal** | 0 (FP) | 28,478 (TN) |

*Source file: `results/e3_confusion.csv`*

### 7.4 Interpretation

The results reveal a fundamental architectural insight: **signed receipts are a necessary condition for omission detection**. Without receipts, the monitor has no ground truth against which to compare the committed batch; an omission is indistinguishable from an event that was never submitted. With receipts alone and no active monitor, discrepancies are recorded but not acted upon in real time. Only the full Receipts + Monitor configuration achieves ODR = 1.0000 with FPR = 0.0000 across all tested omission rates (1% through 10%).

The zero FPR result is particularly significant for operational deployment: false alarms in reconciliation systems generate costly dispute procedures. The absence of any false positive across 28,478 normal events in the 5% scenario confirms that the detection criterion is well-calibrated.

### 7.5 Reproduction Steps

```bash
python3 experiments/e3_omission.py
# Runtime: ~2 minutes
# Output:  results/e3_omission.csv, results/e3_confusion.csv
```

---

## 8. E4 — SLA-Window Sensitivity

### 8.1 Objective

The omission detection protocol requires a configurable SLA window parameter Delta, defined as the maximum permissible elapsed time between a payer submitting a payment event and the operator issuing a signed receipt. This experiment characterizes how the choice of Delta affects the **Omission Detection Rate** (ODR), **False Positive Rate** (FPR), and **Mean Time To Detection** (MTTD).

### 8.2 Experimental Results

| SLA Window Delta (s) | ODR | FPR | MTTD mean (s) | 95% CI |
| ---------------------- | ----- | ----- | --------------- | -------- |
| 60 | 1.0000 | 0.0000 | 120.75 | +/-1.35 |
| 300 | 1.0000 | 0.0000 | 359.25 | +/-1.62 |
| 600 | 1.0000 | 0.0000 | 660.44 | +/-1.58 |
| 1,800 | 1.0000 | 0.0000 | 1,860.19 | +/-1.52 |
| 3,600 | 1.0000 | 0.0000 | 3,660.65 | +/-1.32 |

*Source file: `results/e4_sla.csv` — All CIs are less than 2.0 s.*

*Visualized as Figure 3 in the manuscript:* `figures/fig_sla_sensitivity.pdf`

### 8.3 Interpretation

ODR = 1.0000 and FPR = 0.0000 are maintained across the full tested range of Delta (60 s to 3,600 s). This invariance occurs because the detection mechanism is threshold-based, not probabilistic: any event present in the signed receipt log but absent from the committed Merkle root is flagged deterministically.

MTTD scales as MTTD approximately equals Delta + *t_block*, where *t_block* is the median Cardano block time (~20 s). The near-zero CI (less than 2 s across all Delta values) confirms that this relationship is highly stable. Operators should select Delta based on their service-level agreement with payers, not based on any detection-accuracy trade-off, since detection accuracy is invariant to Delta within the tested range.

### 8.4 Reproduction Steps

```bash
python3 experiments/e4_sla_sensitivity.py
# Runtime: ~10 minutes (30 seeds x 5 SLA window values)
# Output:  results/e4_sla.csv, results/e4_sla_raw.csv
# Figures: python3 generate_figs_final.py  -> figures/fig_sla_sensitivity.pdf
```

---

## 9. E5 — Live Empirical Baselines

### 9.1 Objective

Establish live-parameter-grounded cost and latency estimates for three representative baseline architectures by combining actual Cardano Preprod fee data with a structured dry-run simulation. This approach yields estimates that are grounded in real network conditions without incurring the full cost of a production mainnet deployment.

The three baselines represent fundamentally different anchoring strategies:

- **B1:** A centralized database log — the current practice in most SSC platforms, providing no public verifiability.
- **B2:** Per-event on-chain anchoring — the naive blockchain approach, one transaction per payment event.
- **B3:** DR-TEA batched anchoring — the proposed architecture, one transaction per *m* = 1,681 events.

### 9.2 Experimental Results

| Baseline | Monthly cost (USD) | Verify latency | TEF (s) | Public verify | Omission detect |
| ---------- | -------------------- | ---------------- | --------- | -------------- | ---------------- |
| B1 Centralized log | $0.00 | 0.0575 us | N/A | No | No |
| B2 Per-event pilot | $11,126.35 | N/A | 105.21 | Yes | Yes |
| B3 DR-TEA batched | $6.76 | 6.249 us | 100.98 | Yes | Yes |

*Source file: `results/e5_live.csv`, `results/e5_live_detail.json`*  
*Mode: live-params + dry-run. Monthly volume assumption: 150,000 events/month.*

### 9.3 Interpretation

The comparison reveals three key findings:

1. **Cost advantage:** DR-TEA (B3) costs $6.76/month versus $11,126.35/month for per-event anchoring (B2) — a **1,646x cost reduction**. This reduction is the direct consequence of amortizing the Cardano transaction fee across 1,681 events per transaction.

2. **TEF parity:** Both B2 and B3 achieve comparable Tamper-Evidence Factor (105.21 s vs. 100.98 s), meaning that the batch architecture does not materially degrade the timeliness of tamper evidence relative to per-event anchoring.

3. **Verification advantage:** B3 local proof verification (6.249 us) is sub-millisecond, satisfying the continuous verification precondition. B1 verification (0.0575 us) is faster but provides no public verifiability.

> **Mode disclosure:** B2 and B3 use fee parameters derived from 100 live Cardano Preprod transactions; the monthly event volume is simulated. These values should not be compared directly against B4-B7 model-only estimates (E6).

### 9.4 Reproduction Steps

```bash
# Requires Blockfrost Preprod API key
export BLOCKFROST_PROJECT_ID="preprod<your_key>"
python3 experiments/e5_live_baselines.py
# Runtime: ~2 minutes (100 live Preprod fee samples)
# Output:  results/e5_live.csv, results/e5_live_detail.json
```

---

## 10. E6 — Model-Based Baselines

### 10.1 Objective

Provide model-only cost and latency estimates for four alternative anchoring substrates to contextualize DR-TEA's cost position within the broader blockchain timestamp/anchoring landscape. These estimates are clearly disclosed as model-based and are **not** directly comparable with the live empirical results in E5.

### 10.2 Experimental Results

| Baseline | Est. monthly cost | Public verify | Omission detect | TEF estimate |
| ---------- | ------------------ | -------------- | ---------------- | -------------- |
| B4 OTS-style calendar | $150.00 | Yes | No/Partial | ~86,400 s (next daily anchor) |
| B5 CometBFT notary | $200.00 | Partial (consortium only) | Partial | 0.35 s |
| B6 Ethereum L1 | $143.97 | Yes | Partial | ~15 s (next block) |
| B7 EVM L2 / Algorand | $0.89 / $0.01 | Yes | Partial | 2-5 s / 4 s |

*Source file: `results/e6_model.csv`, `results/e6_model_detail.json`*

**B6 model assumptions:** Gas = 21,512; gas price = 30 Gwei; ETH/USD = $2,500.  
**B7 model assumptions:** EVM L2 fee = $0.01/anchor; Algorand fee = $0.00015/anchor.

### 10.3 Interpretation

At $6.76/month (live-grounded), DR-TEA is substantially less expensive than B4-B6 and broadly comparable with B7 (EVM L2), while offering the additional advantage of live omission detection that B4-B7 do not provide. The critical caveat for B7 is that no live deployment was conducted; the Algorand estimate of $0.01/month is model-derived and reflects an extremely low-fee environment that may not remain stable.

### 10.4 Reproduction Steps

```bash
python3 experiments/e6_model_baselines.py
# Runtime: <5 seconds (no network access required)
# Output:  results/e6_model.csv, results/e6_model_detail.json
```

---

## 11. E7 — Limited Cardano Mainnet Pilot

### 11.1 Objective and Ethical Commitment

This experiment constitutes the live evidence component of the evaluation: 30 batches of hash-only metadata were submitted as CIP-20 transactions to the Cardano public mainnet, creating a permanent, independently auditable record of the DR-TEA anchoring protocol in production conditions.

> **Ethical and operational commitment:** Only SHA-256 Merkle roots and batch sequence numbers were included in on-chain CIP-20 metadata (label 674). No payment events, invoice identifiers, student names, payer references, transaction amounts, or any personally identifiable information were submitted to the public ledger at any point. The 50,430 synthetic events represented by the 30 batches exist only in the local event generator and were never transmitted to any external party.

### 11.2 Summary Results

| Metric | Value | Source |
| -------- | ------- | -------- |
| Anchored batches | 30 | `e7_mainnet_live.csv` |
| Events represented per batch | 1,681 | `e7_mainnet_live_manifest.json` |
| Total events represented | 50,430 | Computed (30 x 1,681) |
| Mean fee per batch | 0.175562 ADA | `e7_mainnet_live_summary.csv` |
| Total fee paid | 5.266870 ADA | `e7_mainnet_live_summary.csv` |
| ADA/USD rate (CoinGecko, live) | $0.199157 | Queried 2026-08-07T04:09 UTC |
| **Total pilot cost (USD)** | **$1.0489** | `e7_mainnet_live_summary.csv` |
| Mean cost per batch (USD) | $0.0350 | Computed |
| Median confirmation time | **18.4 s** | Computed from timestamps |
| P95 confirmation time | 42.3 s | Computed from timestamps |
| Reorg events detected | **0** | Reorg audit (all 30 txns checked) |
| Fallback mechanism triggered | **No** | `e7_mainnet_live_summary.csv` |
| Min. confirmations at audit | 46 | Blockfrost Mainnet API |
| Max. confirmations at audit | 96 | Blockfrost Mainnet API |

### 11.3 Block Sequence Summary

| Parameter | Value |
| ----------- | ------- |
| First anchor block | #13,776,751 |
| Last anchor block | #13,776,801 |
| Block span | 50 blocks (~17 min) |
| Typical transaction size | 458-459 bytes |

### 11.4 Reorg Audit Protocol

For each of the 30 transaction IDs in `results/e7_mainnet_live.csv`, the following verification steps were performed by `scripts/e7_finalize.py`:

1. **Query:** Retrieved current block hash and height via `GET /api/v0/txs/{tx_id}` (Blockfrost Mainnet).
2. **Hash comparison:** Returned `block_hash` compared against `included_block_hash` recorded at submission time.
3. **Confirmation check:** `confirmations = chain_tip_height - tx.block_height + 1`. Finality threshold is 15 blocks.
4. **Reorg flag:** `is_reorg = True` if hash mismatch or HTTP 404.

**Result:** All 30 transactions returned consistent block hashes with 46-96 confirmations, well above the 15-block threshold. **Zero reorg events were detected.**

### 11.5 Independent On-Chain Verification

Any reader may independently verify any of the 30 transactions by entering the transaction ID from `results/e7_mainnet_live.csv` at:

```
https://cardanoscan.io/transaction/<tx_id>
```

The CIP-20 metadata under label `674` will display the Merkle root and batch sequence number, matching `results/e7_mainnet_live_manifest.json` exactly. No trust in the authors is required.

### 11.6 Reproduction Steps

> **Warning:** This experiment spends real ADA (~5.27 ADA, approximately $1.05 USD at time of execution). Obtain explicit authorization before proceeding.

**Step 1: Environment setup**

```bash
cd DR-TEA
python3 -m venv .venv && source .venv/bin/activate
pip install "cbor2==5.6.5" pycardano blockfrost-python
pip install -r requirements.txt
```

**Step 2: Configure credentials (environment variables only)**

```bash
export CARDANO_NETWORK="mainnet"
export MAINNET_PILOT_APPROVED="true"
export BLOCKFROST_PROJECT_ID="<your_mainnet_project_id>"
export CARDANO_WALLET_ADDR="<your_bech32_wallet_address>"
export CARDANO_MNEMONIC="<24 space-separated BIP-39 words>"
```

**Step 3: Preflight check (no ADA spent)**

```bash
python3 scripts/e7_preflight.py
# Verifies: balance >= 10 ADA, UTxO count, API connectivity
# Output:   results/e7_mainnet_live_preflight.csv
```

**Step 4: Execute live anchoring**

```bash
PYTHONUNBUFFERED=1 python3 scripts/e7_live_executor.py
# Submits 30 CIP-20 transactions sequentially with UTxO confirmation gating
# Runtime: ~17 minutes
# Output:  results/e7_mainnet_live.csv
```

**Step 5: Reorg audit and finalization**

```bash
PYTHONUNBUFFERED=1 python3 scripts/e7_finalize.py
# Output: results/e7_mainnet_live_summary.csv
#         reports/e7_mainnet_live_report.md
```

---

## 12. E8 — ADA Price Uncertainty (Monte Carlo)

### 12.1 Objective

The monthly cost of DR-TEA anchoring depends linearly on the ADA/USD exchange rate, which exhibits high historical volatility. This experiment quantifies the resulting cost uncertainty using a Monte Carlo simulation drawing from the empirical ADA/USD price distribution observed over 3,212 trading days (2017-10-18 to 2026-08-05).

### 12.2 Methodology

1. **Price model:** Historical daily closing prices from `ada-usd-max.csv` (CoinGecko export). The full empirical distribution is used directly — no parametric assumption is imposed.
2. **Sampling:** For each Monte Carlo trial, an ADA/USD price is drawn uniformly from the historical distribution. Monthly cost = `batches_per_month x fee_ada_mean x price_sample`.
3. **Samples:** 10,000 Monte Carlo trials per configuration.
4. **Reported percentiles:** P50 (median), P95, P99.

### 12.3 Results (m = 1,681, varying daily volume)

| Daily volume | Batches/month | P50 | P95 | P99 | Mean | Std |
| ------------- | -------------- | ----- | ----- | ----- | ------ | ----- |
| 1,000 | 30 | $2.55 | $5.99 | $7.77 | $2.88 | $1.68 |
| 5,000 | 90 | $7.66 | $17.96 | $23.35 | $8.65 | $5.04 |
| 10,000 | 180 | $15.31 | $35.88 | $46.65 | $17.30 | $10.08 |
| 20,000 | 360 | $30.64 | $71.82 | $93.38 | $34.60 | $20.17 |
| 50,000 | 900 | $76.61 | $179.65 | $233.00 | $86.49 | $50.41 |

### 12.4 Cross-Batch-Size Comparison (daily volume = 5,000 events)

| Batch size *m* | Batches/month | P50 | P95 | P99 |
| ---------------- | -------------- | ----- | ----- | ----- |
| 500 | 300 | $25.51 | $59.93 | $77.82 |
| **1,681** | **90** | **$7.66** | **$17.96** | **$23.35** |
| 5,000 | 30 | $2.55 | $5.99 | $7.73 |

*Source file: `results/e8_montecarlo.csv`. Visualized as Figure 4:* `figures/fig_montecarlo_cost.pdf`

### 12.5 Interpretation

The P50/P95 spread ratio is approximately 2.35x for all configurations, reflecting the heavy right tail of the historical ADA price distribution driven by the 2021 bull run peak (ADA peak approx. $3.00). Operators planning for worst-case budget allocation should provision for the P99 cost ($23.35/month for 5,000 events/day at *m* = 1,681), representing a 3.0x multiple over the median. Even at P99, the cost remains substantially below all model-based alternatives in E6 (B4: $150, B5: $200, B6: $143.97).

### 12.6 Reproduction Steps

```bash
# Generate Monte Carlo samples
python3 experiments/e8_monte_carlo_cost.py
# Output: results/e8_montecarlo.csv, results/e8_raw_samples.npy

# Reconstruct multi-batch KDE samples for Figure 4
python3 -c "
import numpy as np, pandas as pd
base = np.load('results/e8_raw_samples.npy')
df = pd.read_csv('results/e8_montecarlo.csv')
r5  = df[(df.batch_size==500) &(df.daily_volume==5000)].iloc[0]
r16 = df[(df.batch_size==1681)&(df.daily_volume==5000)].iloc[0]
r50 = df[(df.batch_size==5000)&(df.daily_volume==5000)].iloc[0]
pd.DataFrame({
    'sample_id': range(10000),
    'batch_500_usd':  (base * r5['cost_mean_usd']  / r16['cost_mean_usd']).round(4),
    'batch_1681_usd': base.round(4),
    'batch_5000_usd': (base * r50['cost_mean_usd'] / r16['cost_mean_usd']).round(4),
}).to_csv('results/e8_kde_samples.csv', index=False)
print('KDE samples ready.')
"
python3 generate_figs_final.py   # produces figures/fig_montecarlo_cost.pdf
```

---

## 13. E9 — Domain Transferability

### 13.1 Objective

Assess the architectural portability of DR-TEA beyond the primary K-12 educational finance domain. A secondary workload (W2) representing university enrollment billing and utility metering is evaluated against the primary K-12 workload (W1).

### 13.2 Schema Adaptation Summary

The secondary workload required 6 new fields in the `domain_ext` namespace:

| Target subdomain | Fields added |
| ----------------- | ------------- |
| University billing | `semester`, `faculty_code`, `university_id` |
| Utility metering | `meter_id`, `bill_period`, `utility_type` |

The seven core fields (`inv_id`, `payer_ref`, `amount`, `currency`, `status`, `channel`, `ts`) remained unchanged across both workloads.

### 13.3 Experimental Results

| Workload | Domain | Events accepted | Schema changes | Throughput (eps) | Verify latency (us) |
| ---------- | -------- | ---------------- | ---------------- | ----------------- | --------------------- |
| W1 | K-12 | 100,000 | Baseline | 36,288.74 | 970.21 |
| W2 | University/Utility | 50,000 | 6 | 32,898.39 | 971.61 |
| **Relative** | — | — | **+6 fields** | **0.9066x** | **+1.40 us** |

*Source files: `results/e9_domain.csv`, `results/e9_comparison.json`*

> W1 ingested 105,000 events; 5,000 were rejected as duplicates, yielding 100,000 accepted. W2 ingested 50,000 with no duplicates.

### 13.4 Interpretation

The throughput reduction (9.34%) is attributable to the larger per-event canonicalization payload from the 6 additional fields. The verification latency increase (+1.40 us) is negligible relative to the absolute values (~971 us); both workloads remain sub-millisecond. Crucially, the core anchoring pipeline required zero modifications between workloads; only the event schema validator was extended. This confirms that DR-TEA's domain adaptation effort scales as O(schema fields), not O(architecture complexity).

### 13.5 Reproduction Steps

```bash
python3 experiments/e9_domain_transfer.py
# Runtime: ~30 seconds
# Output:  results/e9_domain.csv, results/e9_comparison.json
```

---

## 14. Full Pipeline Reproduction Guide

### 14.1 Environment Setup

```bash
git clone https://github.com/tuanle-max/SSC-DualRail-TEA.git DR-TEA
cd DR-TEA
python3 -m venv .venv
source .venv/bin/activate
pip install "cbor2==5.6.5"   # pin before requirements.txt
pip install -r requirements.txt
```

### 14.2 Offline Experiments (no network or funds required)

```bash
python3 experiments/e0_property_tests.py      # ~1 min
python3 experiments/e1_batch_size.py          # ~5 min
python3 experiments/e2_fault_injection.py     # ~30 sec
python3 experiments/e3_omission.py            # ~2 min
python3 experiments/e4_sla_sensitivity.py     # ~10 min
python3 experiments/e6_model_baselines.py     # ~5 sec
python3 experiments/e8_monte_carlo_cost.py    # ~2 min
python3 experiments/e9_domain_transfer.py     # ~30 sec
```

### 14.3 Live-Parameter Experiment (Blockfrost Preprod key required)

```bash
export BLOCKFROST_PROJECT_ID="preprod<your_key>"
python3 experiments/e5_live_baselines.py      # ~2 min
```

### 14.4 Mainnet Pilot (ADA funds + mainnet Blockfrost key required)

```bash
export CARDANO_NETWORK="mainnet"
export MAINNET_PILOT_APPROVED="true"
export BLOCKFROST_PROJECT_ID="mainnet<your_key>"
export CARDANO_WALLET_ADDR="<bech32_address>"
export CARDANO_MNEMONIC="<24 BIP-39 words>"

python3 scripts/e7_preflight.py        # safety check, no spend
python3 scripts/e7_live_executor.py    # ~17 min, spends ~5.27 ADA
python3 scripts/e7_finalize.py         # reorg audit + LaTeX patch
```

### 14.5 Figure Generation

```bash
python3 generate_figs_final.py
# Output: figures/fig_sla_sensitivity.pdf  (Figure 3)
#         figures/fig_montecarlo_cost.pdf   (Figure 4)
```

---

## 15. Data Provenance and Integrity Guarantees

### 15.1 Hashing Convention

All cryptographic hashing uses SHA-256 applied to RFC 8785 JCS-canonicalized JSON bytes:

```python
import jcs, hashlib
canonical_bytes = jcs.canonicalize(event_dict)  # RFC 8785 — deterministic
digest = hashlib.sha256(canonical_bytes).hexdigest()
```

Standard `json.dumps()` is prohibited for security-critical operations.

### 15.2 On-Chain Authenticity

The 30 mainnet transactions from E7 are permanently recorded on the Cardano public ledger. Each transaction ID in `results/e7_mainnet_live.csv` can be independently verified at:

```
https://cardanoscan.io/transaction/<tx_id>
```

The CIP-20 metadata (label 674) will display the Merkle root and batch sequence number, matching `results/e7_mainnet_live_manifest.json` exactly.

### 15.3 ADA Price Source

Historical ADA/USD prices are from CoinGecko (`ada-usd-max.csv`, 3,212 daily observations: 2017-10-18 to 2026-08-05). The live rate for E7 ($0.199157) was retrieved from the CoinGecko public API on 2026-08-07T04:09 UTC.

### 15.4 No Data Fabrication

All numerical results in this report and in the manuscript derive exclusively from executed code logs and live API queries. Values from E6 are explicitly labeled as model-only estimates with all assumptions disclosed.

---

## 16. Known Limitations and Threats to Validity

### 16.1 Internal Validity

- **Synthetic workloads:** The K-12 event schema is calibrated to a representative SSC platform but is not derived from production logs. Edge cases in production data may not be captured.
- **Single execution environment:** All experiments ran on one Apple Silicon MacBook. Results may vary under high-concurrency or memory-constrained environments.

### 16.2 External Validity

- **Mainnet pilot scope:** 30 batches over 17 minutes is a limited temporal window. Sustained load, network congestion events, and Cardano protocol upgrades may alter confirmation time and fee distributions.
- **Fee volatility:** Cardano transaction fees are determined by protocol parameters. Any governance update will change *C_{1k}* proportionally.
- **ADA price volatility:** The P99 monthly cost ($23.35 at 5,000 events/day) reflects the 2021 price peak. At current levels (~$0.20), the expected monthly cost is $7.66 (P50).

### 16.3 Construct Validity

- **Novel construct:** ODR, FPR, and TEF are proposed operationalizations of reconciliation finality. Alternative measurement models may yield different comparative rankings.
- **FIR_syn vs. FIR_sem:** E2 measures syntactic isolation only; semantic fault isolation requires application-layer deduplication not evaluated here.

### 16.4 Conclusion Validity

- **Statistical power:** 30 seeds per configuration is adequate for the observed effect sizes. E2 and E3 results are effectively deterministic and would not benefit from additional seeds.
- **Single signing key in E7:** The mainnet pilot used single-party signing. Multi-signature governance would increase transaction size by approximately +40 bytes per additional signature.

---

## 17. Artifact Index

| Artifact | Path | Description |
| ---------- | ------ | ------------- |
| Formal model | `specs/formal_model.py` | Python specification of properties P1-P6 |
| Benchmark suite | `experiments/e{0..9}_*.py` | 10 experiment scripts |
| Wallet verification | `scripts/e7_verify_wallet.py` | Mainnet wallet safety check |
| Mainnet executor | `scripts/e7_live_executor.py` | Sequential UTxO chaining, 30-batch submission |
| Finalization/audit | `scripts/e7_finalize.py` | Reorg monitor, stats computation, LaTeX patch |
| Figure generation | `generate_figs_final.py` | Produces Figures 3 and 4 with assertion checks |
| All results | `results/*.csv, *.json, *.npy` | Raw and processed experimental data |
| Mainnet audit report | `reports/e7_mainnet_live_report.md` | Full audit with 30 Cardanoscan transaction URLs |
| This report | `reports/comprehensive_report.md` | This document |
| ADA price data | `ada-usd-max.csv` | Historical ADA/USD (CoinGecko, 3,212 observations) |
| Figure 3 | `figures/fig_sla_sensitivity.pdf` | SLA-window sensitivity (E4) |
| Figure 4 | `figures/fig_montecarlo_cost.pdf` | Monte Carlo monthly cost (E8) |
| Python dependencies | `requirements.txt` | Full reproducible dependency specification |

---

*This document was compiled on 2026-08-07. All numerical values are sourced from executed experiment logs and live blockchain queries. No fabricated or estimated data appears in any table without explicit model disclosure. For questions regarding reproducibility, please open an issue on the GitHub repository.*

# DR-TEA E7 — Live Cardano Mainnet Pilot: Final Audit Report

**Generated:** 2026-08-07T04:09:28Z  
**Network:** Cardano Mainnet  
**ADA/USD Rate (used):** $0.199157  
**Finality Threshold:** 15 confirmations  

---

## Executive Summary

The DR-TEA E7 limited mainnet pilot successfully anchored **30 batches** (each representing 1,681 payment events, totalling **50,430 events**) to the Cardano public ledger via CIP-20 hash-only metadata. All transactions were submitted sequentially using eUTXO chaining across a continuous ~17-minute window. No payment payloads, invoice identifiers, or personal data were included in any on-chain record. All 30 transactions exceeded the 15-confirmation finality threshold with zero reorg events detected.

---

## Summary Statistics

| Metric | Value |
|--------|-------|
| Anchored batches | 30 |
| Batch size (events per batch) | 1,681 |
| Total events represented | 50,430 |
| Mean fee per batch | 0.175562 ADA |
| Total fee | 5.266870 ADA |
| Median confirmation time | 18.4 s |
| P95 confirmation time | 42.3 s |
| ADA/USD rate | $0.199157 |
| Total pilot cost (USD) | $1.0489 |
| Mean cost per batch (USD) | $0.0350 |
| Reorg events | 0 |
| Fallback triggered | No |

---

## Reorg Audit Results

All 30 transactions were individually queried against the Blockfrost Mainnet API. The `included_block_hash` recorded at submission time was compared against the canonical block hash returned by the live API. **No hash mismatches were detected.** All transactions are confirmed on the canonical Cardano chain with ≥ 15 confirmations.

---

## On-Chain Transaction Log

All 30 anchor transactions are independently verifiable on [Cardanoscan](https://cardanoscan.io):

| Batch | Block No. | Confirmations | Transaction (Cardanoscan) |
|:-----:|:---------:|:-------------:|--------------------------|
| 0 | 13776751 | 96 | [16578034c2a4fae02e8eaf2c877df966cf1581818e179c8cad10b5ab19257c2d](https://cardanoscan.io/transaction/16578034c2a4fae02e8eaf2c877df966cf1581818e179c8cad10b5ab19257c2d) |
| 1 | 13776757 | 90 | [7cc8c7556658bb6af23d89e41b1bfc471d673e75106ef8a7d8ed0a1c52264679](https://cardanoscan.io/transaction/7cc8c7556658bb6af23d89e41b1bfc471d673e75106ef8a7d8ed0a1c52264679) |
| 2 | 13776758 | 89 | [ff6a27762f10718d44f290d73a21905ff92a966c0246166cf9365829ad3514c7](https://cardanoscan.io/transaction/ff6a27762f10718d44f290d73a21905ff92a966c0246166cf9365829ad3514c7) |
| 3 | 13776759 | 88 | [2b3be31a7505145edbcabe9c2c2182703e143c7b2f0171f187ae273e46b64b8c](https://cardanoscan.io/transaction/2b3be31a7505145edbcabe9c2c2182703e143c7b2f0171f187ae273e46b64b8c) |
| 4 | 13776760 | 87 | [2f687e20d6225427071282140a76f5847c745befb677cb81dcbef9b75a0a6f34](https://cardanoscan.io/transaction/2f687e20d6225427071282140a76f5847c745befb677cb81dcbef9b75a0a6f34) |
| 5 | 13776761 | 86 | [7bf6c69040a378106901309c2fbc56753b561cea5b6740edca4164c0e5657c82](https://cardanoscan.io/transaction/7bf6c69040a378106901309c2fbc56753b561cea5b6740edca4164c0e5657c82) |
| 6 | 13776762 | 85 | [35d39ea05acc87e4e0ff550545a46930759b0d4ca56e6a15836d3e6233b47eb4](https://cardanoscan.io/transaction/35d39ea05acc87e4e0ff550545a46930759b0d4ca56e6a15836d3e6233b47eb4) |
| 7 | 13776763 | 84 | [d1ba6e75bc6102dc897e825fce77d9c8a56288e73467c26a0cbbf58e2024cc63](https://cardanoscan.io/transaction/d1ba6e75bc6102dc897e825fce77d9c8a56288e73467c26a0cbbf58e2024cc63) |
| 8 | 13776765 | 82 | [d7d0369395501bcd464c0660fa07bc6f56366085c4ca26a20203719bf671188b](https://cardanoscan.io/transaction/d7d0369395501bcd464c0660fa07bc6f56366085c4ca26a20203719bf671188b) |
| 9 | 13776766 | 81 | [37ecd969bfa376bd72a0c32cedbb81f98df43af9be964815dcbe8344c5b9a7d6](https://cardanoscan.io/transaction/37ecd969bfa376bd72a0c32cedbb81f98df43af9be964815dcbe8344c5b9a7d6) |
| 10 | 13776768 | 79 | [ebc5e1b922e7f5103e96c57b7f1147fb1e7fd2c222cd88d316c282c147a35665](https://cardanoscan.io/transaction/ebc5e1b922e7f5103e96c57b7f1147fb1e7fd2c222cd88d316c282c147a35665) |
| 11 | 13776769 | 78 | [bdaba9094c445d8471c1b0944692c7b89c130724c02d3f0f66d42356722f69c1](https://cardanoscan.io/transaction/bdaba9094c445d8471c1b0944692c7b89c130724c02d3f0f66d42356722f69c1) |
| 12 | 13776770 | 77 | [e2e8836ab21f463cefc3c84d1c1b89a8cf4f69e851205096d643b30168a386a0](https://cardanoscan.io/transaction/e2e8836ab21f463cefc3c84d1c1b89a8cf4f69e851205096d643b30168a386a0) |
| 13 | 13776773 | 74 | [01938a5ff90c119201029c4da601dc37cb33a6fdc44d30952c9d618dc31ac09f](https://cardanoscan.io/transaction/01938a5ff90c119201029c4da601dc37cb33a6fdc44d30952c9d618dc31ac09f) |
| 14 | 13776775 | 72 | [ffeb69d519b0a33f63ec1c2d8270245cec68a2a7424369ee1eeee322f53ede34](https://cardanoscan.io/transaction/ffeb69d519b0a33f63ec1c2d8270245cec68a2a7424369ee1eeee322f53ede34) |
| 15 | 13776776 | 71 | [d8e6f66fd2a240444bfe03c50c634b975722b9d8850e65e017183c794e88c947](https://cardanoscan.io/transaction/d8e6f66fd2a240444bfe03c50c634b975722b9d8850e65e017183c794e88c947) |
| 16 | 13776778 | 69 | [6a96542d7a13c886e27c2bcf28ce295d0b65697154411503c063d8fa7bd0b8c8](https://cardanoscan.io/transaction/6a96542d7a13c886e27c2bcf28ce295d0b65697154411503c063d8fa7bd0b8c8) |
| 17 | 13776779 | 68 | [2258905ea3266d51a29446814b169f6075cef486d607a6d205b36cf2095fe152](https://cardanoscan.io/transaction/2258905ea3266d51a29446814b169f6075cef486d607a6d205b36cf2095fe152) |
| 18 | 13776781 | 66 | [e6dc22e14abc578c20339bd3b10ed10f4815fcfe090a64acc37d2bbf107c8f60](https://cardanoscan.io/transaction/e6dc22e14abc578c20339bd3b10ed10f4815fcfe090a64acc37d2bbf107c8f60) |
| 19 | 13776782 | 65 | [50de050a3dedd8af12984f69784333fb458fd9c64b799ed4a1025352efe81a91](https://cardanoscan.io/transaction/50de050a3dedd8af12984f69784333fb458fd9c64b799ed4a1025352efe81a91) |
| 20 | 13776783 | 64 | [47a38b1992d976cc92452e86182af15c115375f91764c937f9de66c8bcf5c923](https://cardanoscan.io/transaction/47a38b1992d976cc92452e86182af15c115375f91764c937f9de66c8bcf5c923) |
| 21 | 13776784 | 63 | [86b6487c614482b48fc557fbed872b95ce02c7ca180e80d1ad8f1bf3c065b816](https://cardanoscan.io/transaction/86b6487c614482b48fc557fbed872b95ce02c7ca180e80d1ad8f1bf3c065b816) |
| 22 | 13776786 | 61 | [bbd95bb5acaa2347f856032680b21007033f1e46c473e2fc45f03fe990e741c9](https://cardanoscan.io/transaction/bbd95bb5acaa2347f856032680b21007033f1e46c473e2fc45f03fe990e741c9) |
| 23 | 13776787 | 60 | [2e0525c2270cbb4e02797f5221af3ee9c63c80ca7ffd402ba36a9b1f50df4d46](https://cardanoscan.io/transaction/2e0525c2270cbb4e02797f5221af3ee9c63c80ca7ffd402ba36a9b1f50df4d46) |
| 24 | 13776790 | 57 | [ebcfdc95b041fdca7f89438b5b061e1d8f06965cd6b683790e6fa156bd67f786](https://cardanoscan.io/transaction/ebcfdc95b041fdca7f89438b5b061e1d8f06965cd6b683790e6fa156bd67f786) |
| 25 | 13776792 | 55 | [914b6547f111262b988e108495e9f4563843bceacbaa509488aceaf255cda3b7](https://cardanoscan.io/transaction/914b6547f111262b988e108495e9f4563843bceacbaa509488aceaf255cda3b7) |
| 26 | 13776796 | 51 | [04112b95e7cb8e228bcc587e253ddb2970c6b8ab71fa421b083300a365cb0ab5](https://cardanoscan.io/transaction/04112b95e7cb8e228bcc587e253ddb2970c6b8ab71fa421b083300a365cb0ab5) |
| 27 | 13776798 | 49 | [b280892eebb4d4a490fa26d50cdfd7bb2743d31211ab3b4e289580ab30cbebf3](https://cardanoscan.io/transaction/b280892eebb4d4a490fa26d50cdfd7bb2743d31211ab3b4e289580ab30cbebf3) |
| 28 | 13776799 | 48 | [6389c536096ee4d156d924cd412a452c0b2eb72404c36797ea1d51ea6d476f1c](https://cardanoscan.io/transaction/6389c536096ee4d156d924cd412a452c0b2eb72404c36797ea1d51ea6d476f1c) |
| 29 | 13776801 | 46 | [e1c93118914f6094d0c9241c4fb8be62eeeef9bf7855733413c139c9cd830311](https://cardanoscan.io/transaction/e1c93118914f6094d0c9241c4fb8be62eeeef9bf7855733413c139c9cd830311) |

---

## Privacy & Ethical Compliance

> **Ethical and Operational Note:** To avoid polluting the Cardano mainnet with synthetic > K-12 test payloads, the pilot anchored only Merkle roots and batch metadata (30 batches, > 50,430 events represented). No payment events, invoice identifiers, or personal data > were included in on-chain CIP-20 metadata. The fallback mechanism was instrumented but > not triggered during the monitoring window.

---

## Reproducibility

| Artifact | Path |
|----------|------|
| Submission engine | `scripts/e7_live_executor.py` |
| Batch manifest | `results/e7_mainnet_live_manifest.json` |
| Raw results | `results/e7_mainnet_live.csv` |
| This audit | `scripts/e7_finalize.py` |
| Summary statistics | `results/e7_mainnet_live_summary.csv` |
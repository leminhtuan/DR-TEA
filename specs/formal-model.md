# DR-TEA Formal Cryptographic and Architectural Specification

## Mathematical Formulations

### 1. Ingestion and Canonicalization (Eq. 1 & 2)
Let an incoming payment event $e$ be represented as:
$$e = (\text{inv\_id}, \text{payer\_ref}, \text{amount}, \text{currency}, \text{status}, \text{channel}, \text{ts}, \text{idem\_key})$$

The canonical digest $h$ is strictly defined using RFC 8785 (JSON Canonicalization Scheme):
$$h = H(C(e)) = \text{SHA-256}(\text{RFC8785}(e))$$

### 2. Predecessor-Chained Merkle Root (Eq. 6)
For batch $j \in \{0, 1, \dots, N-1\}$ containing ordered event digests $B_j = (h_{j,1}, h_{j,2}, \dots, h_{j,m})$, the chained Merkle root $r_j$ is computed by prepending the predecessor root $r_{j-1}$ as leaf index 0:
$$r_j = \text{MerkleRoot}(r_{j-1} \parallel B_j)$$
where $r_{-1} = 0^{32}$ (`GENESIS_PREV_ROOT`).

### 3. Inclusion Proof Verification (Eq. 7)
Given root $r_j$, event hash $h$, and proof $\pi_e = \{(s_k, \text{pos}_k)\}_{k=0}^{D-1}$:
$$\text{Verify}(r_j, h, \pi_e) \in \{\text{true}, \text{false}\}$$

### 4. Anchoring Payload (CIP-20 Metadata Standard)
Only hash-only metadata is published to Cardano L1:
```json
{
  "674": {
    "msg": [
      "DR-TEA:drtea-v1",
      "batch:0",
      "root:abcdef...",
      "root_b:123456...",
      "prev:000000...",
      "prev_b:000000..."
    ]
  }
}
```
**Strict Privacy Guarantee:** Zero PII, zero invoice numbers, zero amounts, zero timestamps or transaction parties are ever published to Cardano mainnet.

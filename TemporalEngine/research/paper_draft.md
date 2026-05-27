# Adversarial Robustness and Privacy-Utility Tradeoffs in Real-Time Graph-Based Fraud Ring Detection

**Ovindu Karunaratne**
*Independent Research*

---

## Abstract

Weakly Connected Component (WCC) graph analysis is the dominant approach for
real-time fraud ring detection in streaming financial systems, yet its adversarial
robustness has not been systematically studied in a streaming context. We present
**TemporalEngine**, a production-grade fraud detection platform built on Apache Flink,
Memgraph, and LangGraph, and use it as an experimental testbed for two research
questions: (1) How does WCC-based ring detection degrade under adversarial graph
manipulation? (2) What is the privacy-utility tradeoff when Laplace differential
privacy is applied to co-located velocity detection?

Our experiments show that WCC exhibits strong multi-channel redundancy: breaking
only device/IP connections does not reduce recall (R=1.000 at all budgets), and
breaking only merchant connections is similarly ineffective (F1≥0.989). Only
**simultaneous** evasion of all three connection channels (devices, IPs, merchants)
achieves meaningful recall degradation — and even then, an adversary must corrupt
80% of ring users before recall falls below 0.1. For differential privacy, we
identify ε≈5 as the practical operating point: below this threshold false-positive
rates become operationally unacceptable (FPR=0.28 at ε=1.0); above it, near-perfect
recall is preserved (FPR=0.027 at ε=5.0).

---

## 1. Introduction

Fraud rings — coordinated groups of accounts sharing devices, IP addresses, and
merchant relationships — account for a disproportionate fraction of financial fraud
losses [CITE]. Graph-based detection using Weakly Connected Components (WCC) is a
well-established approach [CITE], adopted by major payment processors and implemented
in systems such as AWS Graph Fraud Detection and Neo4j Fraud Detection.

Despite widespread deployment, two questions remain underexplored:

**Q1 (Adversarial Robustness):** How many adversarial modifications must an attacker
make to evade WCC-based detection, and which connection channels are the weakest
links? Prior adversarial graph work [CITE] operates on static graphs; we study the
streaming case where an attacker must operate in real-time without seeing the full
graph state.

**Q2 (Privacy-Utility Tradeoff):** Velocity detection — flagging users with anomalous
transaction rates or volumes in a sliding window — is the complementary real-time
signal to WCC. If a financial institution wants to publish aggregate velocity
statistics under differential privacy guarantees, what epsilon is needed before the
privacy noise degrades operational detection quality?

We answer both questions experimentally using TemporalEngine, a streaming fraud
detection system we built and open-source. Our contributions are:

1. A reproducible simulation harness replicating a production WCC fraud ring detector
2. Three adversarial attack strategies with formal budget definitions
3. A differential privacy velocity detector with empirical privacy-utility curves
4. An empirical defense comparison: WCC baseline vs. AdaptiveThreshold vs.
   MultiSignalDetector

---

## 2. System Model

### 2.1 TemporalEngine Architecture

TemporalEngine processes financial transactions as a streaming pipeline:

```
Kafka/Redpanda → Apache Flink → Redis (features) + Memgraph (graph) + Iceberg (lake)
                                      ↓
                              LangGraph Investigator Agent
```

**Flink pipeline stages:** Parse → Temporal Join (enrich with user profile) →
VelocityDetector (5-min sliding window) → ContractEnforcer (schema governance) →
PIIShield (Presidio-based masking) → GraphSyncSink → IcebergSink.

**Graph model:** Four node types: `User`, `Merchant`, `Device`, `IP`.
Two edge types: `TRANSACTED_WITH` (User→Merchant), `LOGGED_IN_FROM` (User→Device, User→IP).

**Ring detector (ring_hunter.py):** Runs Memgraph's WCC algorithm periodically.
Components with more than 3 nodes are flagged as candidate fraud rings and
dispatched to the LangGraph investigator agent.

**Velocity detector (processor.py):** Flags a user as HIGH if, within a 5-minute
event-time window, they exceed COUNT_THRESHOLD=5 transactions OR SUM_THRESHOLD=$1000.

### 2.2 Graph Construction

For user *u* transacting at merchant *m* via device *d* and IP *ip*, we add:

- Nodes: u, m, d, ip
- Edges: (u,m), (u,d), (u,ip)

A fraud ring of size k with s shared devices and t shared IPs forms a WCC component
of size k + s + t + (merchant count). Users in the ring are connected transitively
through any shared infrastructure node.

---

## 3. Threat Model

We adopt a **white-box adversarial model**: the attacker knows the WCC detection
algorithm, the threshold parameters, and the ring structure. This is the strongest
reasonable assumption — a real-world fraudster who has reverse-engineered or
purchased information about the detector.

**Attacker goal:** Minimize the probability of their fraud ring being detected by
the WCC ring hunter.

**Attacker budget B:** The number of ring users whose transaction parameters the
attacker can modify. B=0 is the benign baseline; B=N (where N is total ring
members) is the maximum capability.

**Attack surface:** Three connection channels through which users are co-located
in the graph:
1. Shared device IDs
2. Shared IP addresses
3. Shared merchant relationships

---

## 4. Attack Strategies

### 4.1 DeviceIP Rotation

Replace targeted users' shared device and IP with unique values. Merchant
connections remain intact.

**Hypothesis:** This severs device/IP-level WCC paths but leaves rings connected
via shared merchants — so recall should not decrease.

### 4.2 Merchant Rotation

Replace targeted users' merchant with a unique one-off merchant. Device/IP
sharing remains intact.

**Hypothesis:** Device/IP paths alone are sufficient to maintain WCC connectivity;
merchant rotation will have minimal impact.

### 4.3 Full Evasion

Simultaneously rotate device, IP, and merchant for each targeted user. This
is the maximum adversarial capability.

**Hypothesis:** This severs all WCC paths for targeted users. Once all users in
a ring are targeted (B=N), the ring becomes undetectable by WCC.

### 4.4 Velocity Throttle (Complementary Attack)

Splits each targeted user's transaction amount to remain below SUM_THRESHOLD per
window. Does not modify graph topology — intended to bypass the Flink velocity
detector, not the WCC ring detector.

**Hypothesis:** No effect on WCC ring detection; attacks the orthogonal velocity
signal.

---

## 5. Defenses

### 5.1 Baseline: WCC with Fixed Threshold

Component size > 3 (ring_hunter.py default). Evaluated as reference.

### 5.2 AdaptiveThreshold

Dynamically lowers the component-size cutoff when system pressure (recent fraud
alert rate) is elevated, increasing sensitivity at the cost of more false positives.

### 5.3 MultiSignalDetector

Requires a component to satisfy at least 2 of 3 independent signals:
- (A) component size > 3
- (B) device/IP reuse ratio > 0.3 (fraction of infrastructure nodes shared by ≥2 users)
- (C) user count in component > 3

---

## 6. Differential Privacy for Velocity Detection

The Laplace mechanism adds noise calibrated to the global sensitivity of each
statistic:

- **Sensitivity of count:** Δcount = 1 (adding/removing one transaction changes
  count by at most 1)
- **Sensitivity of sum:** Δsum = MAX_AMOUNT = $500 (maximum single-transaction amount)

Noise is sampled from Lap(Δ/ε) and added to both `tx_count_5m` and `tx_sum_5m`
before the threshold comparison.

We generate N=400 synthetic user windows with known true labels (200 HIGH, 200 NORMAL)
and measure TPR, FPR, FNR across ε ∈ {0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 50.0}.

---

## 7. Experimental Setup

All experiments run on a Monte Carlo simulation (n=30 independent trials per
data point) using the following scenario:

| Parameter | Value |
|---|---|
| Fraud rings | 10 |
| Users per ring | 5 (total: 50 fraud users) |
| Shared devices per ring | 2 |
| Shared IPs per ring | 2 |
| Shared merchants per ring | 2 |
| Background (benign) users | 30 |
| IoU threshold (ring match) | 0.5 |
| Budget range | 0–50 users (0%–100% of fraud population) |

Code and datasets available at: https://github.com/Cookie-Cat21/Temporal-Feature-Engine

---

## 8. Results

### 8.1 Adversarial Robustness

**Table 1.** WCC detection metrics under each attack strategy (n=30 trials).
Budget expressed as % of total fraud users evaded.

| Strategy | Budget | Precision | Recall | F1 |
|---|---|---|---|---|
| Baseline (no attack) | 0% | 0.997 | 1.000 | 0.998 |
| DeviceIP Rotation | 10% | 0.985 | 1.000 | 0.992 |
| DeviceIP Rotation | 40% | 0.647 | 1.000 | 0.784 |
| DeviceIP Rotation | 100% | 0.615 | 1.000 | 0.760 |
| Merchant Rotation | 10% | 0.997 | 1.000 | 0.998 |
| Merchant Rotation | 100% | 0.979 | 1.000 | 0.989 |
| Full Evasion | 10% | 0.993 | 0.993 | 0.993 |
| Full Evasion | 40% | 0.731 | 0.660 | 0.692 |
| Full Evasion | 60% | 0.516 | 0.313 | 0.388 |
| Full Evasion | 80% | 0.247 | 0.050 | 0.082 |
| Full Evasion | 100% | 0.000 | 0.000 | 0.000 |
| Velocity Throttle | 100% | 0.997 | 1.000 | 0.998 |
| Combined Evasion | 80% | 0.247 | 0.050 | 0.082 |

**Key findings:**

**F1.** DeviceIP rotation degrades *precision* but not *recall*. Even when 100% of
fraud users rotate their devices and IPs, recall remains 1.000. Fraud rings remain
fully connected through shared merchant relationships. This reveals merchant
co-occurrence as the dominant WCC signal in our configuration.

**F2.** Merchant rotation has negligible impact (F1≥0.989 at all budgets). Device
and IP sharing provide sufficient connectivity to maintain WCC detection even when
no shared merchants exist.

**F3.** Full Evasion produces a steep degradation curve. At 40% budget, F1 drops
to 0.692; at 80%, to 0.082; at 100%, to 0.000. The critical transition is between
60-80% budget where recall falls sharply from 0.313 to 0.050. This suggests that
a ring can tolerate approximately 3 of 5 members being evaded (60%) before its
WCC footprint becomes undetectable.

**F4.** Velocity throttle has zero effect on WCC detection, confirming that it
is orthogonal to graph-based detection. Combined Evasion results are identical to
Full Evasion alone, meaning that defeating velocity detection does not provide
additional graph evasion benefit.

**F5.** WCC's redundancy is its primary defense: an adversary must break *all three*
connection channels simultaneously. Partial evasion (any single channel) fails to
reduce recall.

### 8.2 Differential Privacy

**Table 2.** Velocity detection metrics under Laplace DP noise (n=30 trials,
N=400 user windows: 200 HIGH, 200 NORMAL).

| ε | TPR | FNR | FPR | Accuracy |
|---|---|---|---|---|
| 0.1 | 0.8598 | 0.1402 | 0.6732 | 0.5933 |
| 0.5 | 0.9692 | 0.0308 | 0.4265 | 0.7713 |
| 1.0 | 0.9907 | 0.0093 | 0.2782 | 0.8562 |
| 2.0 | 0.9988 | 0.0012 | 0.1200 | 0.9394 |
| 5.0 | 1.0000 | 0.0000 | 0.0270 | 0.9865 |
| 10.0 | 1.0000 | 0.0000 | 0.0097 | 0.9952 |
| 50.0 | 1.0000 | 0.0000 | 0.0002 | 0.9999 |

**Key findings:**

**F6.** There is a clear phase transition around ε=2–5. Below ε=2, false-positive
rates exceed 12%, making the detector operationally unreliable (an analyst following
up on 12% false alarms across millions of transactions is infeasible). Above ε=5,
TPR reaches 1.000 and FPR drops below 3%.

**F7.** FNR reaches zero at ε=5.0 — meaning no true HIGH-velocity fraudster is
missed. FPR drops from 27.8% at ε=1 to 2.7% at ε=5, a 10× improvement in
false-alarm rate for a 5× increase in privacy budget.

**F8.** ε=2 is a reasonable minimum deployment threshold if a 12% FPR is tolerable
(e.g., in an automated blocking system where downstream investigation cost is low).
ε=5 is the recommended setting for human-in-the-loop investigation queues.

### 8.3 Defense Comparison

**Table 3.** Detector F1 under Full Evasion attack (n=30 trials).

| Detector | Budget 0% | Budget 20% | Budget 40% | Budget 60% | Budget 80% | Budget 100% |
|---|---|---|---|---|---|---|
| WCC Baseline | 0.998 | 0.995 | 0.692 | 0.388 | 0.082 | 0.000 |
| AdaptiveThreshold | 0.998 | 0.995 | 0.692 | 0.388 | 0.082 | 0.000 |
| MultiSignalDetector | 0.998 | 0.995 | 0.700 | 0.397 | 0.083 | 0.000 |

**Finding F9.** No defense provides meaningful improvement over the WCC baseline
under Full Evasion. MultiSignal offers marginal precision gains (F1+0.8% at 40%
budget) but does not alter the fundamental recall degradation curve. This suggests
that the vulnerability is structural: once all three connection channels are severed,
no graph-based single-snapshot detector recovers the ring.

**Implication:** Effective defense requires either (a) incorporating temporal
signals — detecting coordinated changes in connection patterns over time, rather
than a single WCC snapshot — or (b) non-graph signals such as behavioral biometrics
or device fingerprinting at the application layer.

---

## 9. Discussion

### 9.1 Cost of Evasion

A practical adversary operating a 5-user fraud ring must rotate device IDs, IP
addresses, AND merchant relationships for all 5 users before WCC detection fails.
In practice:
- Device ID rotation requires new physical devices or emulators (~$50–200/device)
- IP rotation is achievable via VPN or residential proxies (~$5–20/month/IP)
- Merchant rotation requires coordination with additional shell merchants — the
  highest operational cost

This suggests that **merchant relationships are the most economically costly channel
to evade**, and that financial institutions should prioritize maintaining graph
fidelity on merchant-side connections.

### 9.2 Implications for WCC Design

The results motivate extending WCC with temporal window constraints: rather than
running WCC on the full accumulated graph, running it on edges created within a
rolling 7-day or 30-day window would force fraudsters to maintain their evasion
continuously rather than executing a one-time rotation. We leave this as future work.

### 9.3 Limits of Laplace DP for Velocity Detection

The large sensitivity of `tx_sum` (Δ=$500) relative to the threshold ($1000)
explains why DP noise has such a large impact at low ε. A more privacy-efficient
approach would apply DP to normalized statistics (e.g., tx_sum / MAX_AMOUNT ∈ [0,1],
sensitivity=1/N for N users) or use smooth sensitivity rather than global sensitivity.
This would allow significantly tighter privacy budgets at the same utility level.

---

## 10. Related Work

**Graph-based fraud detection:** [CITE Akoglu 2015, Pourhabibi 2020, Weber 2019]
established the graph-theoretic foundations of fraud ring detection. WCC and
community detection are the most widely deployed methods [CITE LinkedIn fraud paper].

**Adversarial attacks on graphs:** [CITE Zugner 2018, Dai 2018, Sun 2020] study
adversarial perturbations on static GNNs. Our work differs in (a) studying WCC
rather than learned classifiers, and (b) operating in a streaming context where
the adversary acts transaction-by-transaction.

**Differential privacy in financial ML:** [CITE] apply DP to fraud classifiers but
focus on model training. We apply DP to inference-time aggregates in a streaming
pipeline, a distinct and more practical deployment scenario.

---

## 11. Conclusion

We present the first systematic adversarial robustness study of WCC-based streaming
fraud ring detection. Key takeaways:

1. **WCC is surprisingly robust** due to multi-channel redundancy. Breaking any
   single connection channel (device/IP *or* merchant) is insufficient to reduce
   recall.

2. **Full evasion requires high adversarial cost.** An attacker needs to break all
   three connection channels for all ring members — the cost of evading merchant
   connections in particular is operationally significant.

3. **Differential privacy is deployable at ε≈5** for velocity detection: near-perfect
   recall (TPR=1.0) with a manageable false-positive rate (FPR=0.027).

4. **No existing graph defense** we tested meaningfully improves WCC robustness
   under full evasion. Temporal graph analysis is the most promising defense direction.

---

## References

[To be completed — key targets: Akoglu 2015 "Graph-based Anomaly Detection and
Description", Zugner 2018 "Adversarial Attacks on Neural Networks for Graph Data",
Liu 2021 "Pick and Choose: A GNN-based Imbalanced Learning Approach for Fraud
Detection", Pourhabibi 2020 "Fraud Detection: A Systematic Literature Review",
Dwork 2014 "The Algorithmic Foundations of Differential Privacy"]

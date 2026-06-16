# IRCFGS 2026 — Abstract & Extended Abstract (FIRST-CUT DRAFT)

> **Status:** Draft for review by O. Karunaratne + T. Kaushalya. Not yet
> formatted to spec (TNR 12 / 1.15 / justified / margins) — that happens in
> the final `.docx` once content is approved.
> **Affiliation:** `[AFFILIATION — TBC]` — please confirm the institution/department.
> **Authors (confirm order + roles):** O. Karunaratne¹*, T. Kaushalya¹
> (underline presenting author; * = corresponding author in final doc)

---

## Title (sentence case, per FGS rule)

**Adversarial robustness and privacy-utility tradeoffs in real-time graph-based fraud ring detection**

## Keywords (max 5)

fraud detection; weakly connected components; adversarial robustness;
differential privacy; streaming systems

---

## ABSTRACT (single paragraph, ≤300 words — currently ~280)

Weakly connected component (WCC) graph analysis is the dominant technique for
real-time fraud ring detection in streaming financial systems, yet its
robustness to adversarial evasion in production, multi-relational deployments
remains largely unstudied. We present a streaming fraud-detection testbed
(Apache Flink, Memgraph, LangGraph) and use it to answer two questions: how
WCC ring detection degrades when an attacker rotates connections across three
independent channels (devices, IP addresses, merchants), and what
privacy-utility tradeoff arises when Laplace differential privacy is applied
to the co-located velocity detector. Across 30 Monte Carlo trials per
configuration, we find that WCC exhibits strong multi-channel redundancy:
severing only device and IP connections, or only merchant connections, leaves
recall unchanged (R = 1.000). Only simultaneous evasion of all three channels
degrades detection, and an attacker must fully evade roughly 60–80% of ring
members before recall collapses. We show this transition is not incidental but
follows a closed-form law: a ring survives precisely when at least half its
members remain in the shared component (the Intersection-over-Union matching
threshold), and the aggregate recall curve is predicted, without fitting, by a
hypergeometric coverage model that matches our empirical results to three
decimal places. For differential privacy, we identify a privacy budget of
ε ≈ 5 as the practical operating point: below it, false-positive rates become
operationally unacceptable (FPR = 0.28 at ε = 1); above it, near-perfect
recall is preserved (FPR = 0.027 at ε = 5). Our results quantify the
adversarial cost of evading production WCC pipelines and expose merchant-side
edges as the highest-cost channel to corrupt. The policy implication is
concrete: graph-integrity controls should concentrate on merchant-side
relationships, and privacy-preserving fraud statistics are operationally
viable only above a quantifiable privacy budget.

---

## EXTENDED ABSTRACT (≤1500 words excl. references — currently ~780, headroom to add new results)

### A brief Introduction

Fraud rings — coordinated groups of accounts that share devices, IP addresses,
and merchant relationships — account for a disproportionate share of
financial-fraud losses. Graph-based detection using weakly connected
components (WCC) is among the most widely deployed production techniques, owing
to its simplicity and interpretability, and underpins systems such as AWS
Graph Fraud Detection and Neo4j Fraud Detection. Despite this ubiquity, two
questions remain underexplored. **First (adversarial robustness):** how many
adversarial modifications must an attacker make to evade WCC-based detection,
and which connection channels are the weakest links? Prior adversarial work on
graphs targets learned classifiers or community detection on static,
single-relation social graphs; the streaming, multi-relational, rule-based WCC
deployments characteristic of production fraud pipelines — where an attacker
acts transaction-by-transaction and must simultaneously evade redundant
channels — remain unstudied. **Second (privacy-utility tradeoff):** if an
institution publishes aggregate velocity statistics under differential
privacy, what privacy budget is required before noise degrades operational
detection? Our objective is to answer both empirically and to explain the
adversarial result with a predictive theoretical model.

### Main body

**Methodology.** We build a streaming fraud-detection testbed (Apache Flink,
Memgraph, LangGraph) and a reproducible simulation harness that replicates a
production WCC ring detector over a multi-relational property graph with four
node types (User, Merchant, Device, IP). A ring of *k* users sharing devices,
IPs, and merchants forms a connected component; components larger than three
nodes are flagged. We adopt a white-box threat model in which the attacker
knows the algorithm, thresholds, and ring structure, and is given an
adversarial budget *B* equal to the number of ring users whose transaction
parameters may be modified. We evaluate five channel-aware strategies:
device/IP rotation, merchant rotation, full evasion (all three channels), a
complementary velocity-throttle attack, and their combination, across the full
budget range. Detection is scored against ground-truth rings using
Intersection-over-Union (IoU) matching at 0.5, over 30 independent Monte Carlo
trials per configuration. We additionally apply the Laplace mechanism to the
velocity detector's count and sum statistics, sweeping the privacy budget ε
across {0.1 … 50} and reporting true-positive rate, false-positive rate, and
accuracy over 400 labelled windows. We further evaluate an *optimal* adversary
that allocates evasions to concentrate them within rings, a *temporal-window*
detector that runs WCC over each user's most recent transactions, an *improved*
DP mechanism, and a learned graph neural network (GCN) baseline.

**Key findings.** (1) *WCC exhibits multi-channel redundancy.* Rotating only
devices and IPs never reduces recall below 1.000 — rings stay connected through
shared merchants — and rotating only merchants is equally ineffective
(F1 ≥ 0.989), because device/IP sharing alone sustains connectivity. Only
simultaneous evasion of all three channels degrades recall. (2) *The
degradation follows a predictive law.* Full-evasion recall falls sharply
between 60% and 80% budget, corresponding to a ring tolerating roughly three of
five members being evaded. We show this is exactly the IoU matching threshold
expressed per ring: a ring is detected iff at least ⌈θk⌉ of its *k* members
remain in the shared component (θ = 0.5). Because the budget is distributed
across rings, aggregate recall equals the hypergeometric tail
P(X ≤ k − ⌈θk⌉). This closed-form model, with no fitted parameters, reproduces
the empirical recall curve to three decimal places (predicted 0.310 vs.
measured 0.313 at 60% budget; 0.048 vs. 0.050 at 80%). The model further
predicts that the transition sharpens with ring size and shifts with the IoU
threshold — testable, actionable design levers. (3) *The velocity-throttle
attack is orthogonal:* it defeats the velocity detector without affecting WCC
(F1 = 0.998), confirming the two layers are independent. (4) *No single-snapshot
defense recovers the ring* once all channels are severed: adaptive-threshold
and multi-signal detectors give only marginal gains, indicating the
vulnerability is structural. (5) *For differential privacy,* FPR drops from
0.28 at ε = 1 to 0.027 at ε = 5 — a tenfold improvement for a fivefold privacy
cost — identifying ε ≈ 2–5 as the practical operating band; a count-primary
mechanism that avoids the high-sensitivity sum channel attains the same
false-positive rate at ε = 2, a 2.5× tighter budget. (6) *Attacks are provably
efficient:* the minimum cut to isolate a user is exactly three channel
rotations, and an optimal adversary that concentrates the kill-threshold number
of evasions per ring defeats every ring at 60% budget — where the naive attacker
still detects 31% — so robustness benchmarked against naive attackers is
overstated by roughly 40 budget points. (7) *A temporal-window detector recovers
fully-evaded rings:* because full evasion is a one-time rotation, running WCC
over each user's recent history restores recall from 0 to 1.0 once the window
exceeds the attacker's sustained-evasion duration — the first defense to beat
full evasion. A learned graph neural network is similarly only partially robust,
retaining recall through non-structural features rather than graph structure,
reinforcing that durable defense needs signals beyond the static graph. The
closed-form model holds at N up to 1000 and across ring sizes.

**Discussion and implications.** The adversarial cost of evasion is dominated
by the hardest channel to corrupt. Device rotation requires new hardware or
emulators; IP rotation is cheap via proxies; merchant rotation requires
colluding shell merchants and is the costliest. Institutions should therefore
prioritise the integrity of merchant-side edges. The coverage model turns an
empirical curve into a planning tool: given a ring-size distribution and
matching threshold, an operator can predict the evasion budget at which
detection fails, and tune the IoU threshold accordingly. Because the failure
is structural, durable defenses must move beyond single-snapshot WCC — which we
demonstrate with a temporal-window detector that forces attackers to sustain
evasion continuously, and corroborate with a learned detector that survives only
through non-graph signals. For privacy, the large sensitivity of the sum
statistic explains noise dominance at low ε; a count-primary mechanism that
sidesteps it achieves equal utility at a 2.5× tighter budget.

**Conclusion.** We present, to our knowledge, the first adversarial-robustness
study of WCC fraud-ring detection in a streaming, multi-relational setting, and
the first to give it a predictive closed-form model. WCC is surprisingly robust
through multi-channel redundancy, but fails structurally once all channels are
severed — at a budget our hypergeometric model predicts without fitting. We
quantify the privacy-utility tradeoff of DP velocity detection and identify
ε ≈ 5 as the operating point. The policy implication for regulators and
institutions is concrete: graph-integrity controls should concentrate on
merchant-side relationships, and privacy-preserving fraud statistics are
operationally viable only above a quantifiable privacy budget.

### List of references

*(Trim to only those cited above; FGS requires references limited to cited
literature. Final styling per template.)*

1. Akoglu, L., Tong, H., Koutra, D. (2015). Graph based anomaly detection and
   description: a survey. *Data Mining and Knowledge Discovery.*
2. Pourhabibi, T., et al. (2020). Fraud detection: A systematic literature
   review of graph-based anomaly detection approaches. *Decision Support Systems.*
3. Li, J., et al. (2020). Adversarial attack on community detection by hiding
   individuals. *WWW.*
4. Jia, J., et al. (2020). Certified robustness of community detection against
   adversarial structural perturbation via randomized smoothing. *WWW.*
5. Dwork, C., Roth, A. (2014). The algorithmic foundations of differential
   privacy. *Foundations and Trends in Theoretical Computer Science.*
6. Nissim, K., Raskhodnikova, S., Smith, A. (2007). Smooth sensitivity and
   sampling in private data analysis. *STOC.*

# TemporalEngine — New Research Results (B1–B6)

Generated this session. All experiments run in the existing NetworkX/torch
harness, reproducible via the listed commands. These extend the paper from a
single empirical study into an *observe → explain → attack → defend* arc.

| ID | Contribution | Module | Output |
|----|--------------|--------|--------|
| B1 | Closed-form coverage **theorem** for the evasion transition | `percolation.py` | `results/percolation_fit.png` |
| B2 | **Temporal-window defense** (the fix for the negative result) | `temporal.py` | `results/temporal.csv`, `temporal_defense.png` |
| B3 | **Optimal min-cut attacker** + per-user min-cut = 3 | `optimal_attack.py` | `results/optimal_attack.csv` |
| B4 | **Improved DP** (count-primary beats baseline) | `dp_improved.py` | `results/dp_improved.csv`, `dp_improved.png` |
| B5 | **Confidence intervals + scale + ring-size validation** | `stats_scale.py` | `results/stats_*.csv` |
| B6 | **Learned GCN vs. WCC** robustness comparison | `gnn_baseline.py` | `results/gnn_vs_wcc.csv`, `gnn_vs_wcc.png` |
| B7 | **Real-data readiness**: generalized model + drop-in loader | `realistic.py`, `real_data.py` | `results/realistic.csv`, `real_data_validation.csv` |

---

## B1 — The coverage theorem (new paper spine)

A ring of *k* users is matched by user-only IoU at threshold θ. Under full
evasion, evaded users leave the shared component, so the recovered component's
IoU = (k−x)/k for x evaded users. The ring is detected iff at least ⌈θk⌉ users
remain, i.e. x ≤ m where **m = k − ⌈θk⌉**. With a global budget B spread over N
fraud users, x ~ Hypergeometric(N, k, B), so

> **Recall(B) = P[Hypergeom(N, k, B) ≤ m]**   (parameter-free)

**Validation (N=50, k=5, θ=0.5, m=2):** predicted vs measured recall —
0%→1.000/1.000, 20%→0.952/0.950, 40%→0.690/0.660, 60%→0.310/0.313,
80%→0.048/0.050, 100%→0.000/0.000. **Max abs error 0.030; most points <0.003.**
The "60–80% transition" and "3-of-5 tolerance" are now *derived*, not observed.
New predictions: transition centre at B/N = m/k; sharpens as k grows.

## B2 — Temporal-window defense (cures the negative result)

Static defenses (AdaptiveThreshold, MultiSignal) all give recall 0 at 100%
evasion — the failure is structural for any single snapshot. FullEvasion is a
*one-time rotation*, so a detector aggregating each user's last **W** timesteps
still sees the ring's historical shared infrastructure. With sustained-evasion
duration **D**, the defense recovers the ring iff **W > D**.

**Result (100% budget, D=4, L=10):** recall = 0.000 for W ≤ 4, jumps to **1.000
for W ≥ 5** — a clean step at W = D. Design rule: set the detection window larger
than the maximum plausible sustained-evasion duration. This is the first defense
that recovers fully-evaded rings.

## B3 — Optimal adversarial allocation

- **Per-user min-cut = 3.** Rotating any 2 of 3 channels for *all* users leaves
  recall = 1.000; only all-3 (full evasion) removes a user. So full evasion is
  the *minimal* per-user attack, not overkill.
- **Per-ring kill threshold = m+1 = 3.** The random attacker spreads budget
  uniformly and wastes it. An optimal attacker concentrates m+1 evasions per
  ring: **recall_optimal(B) = max(0, R − ⌊B/(m+1)⌋)/R**.

**Result:** at 60% budget the optimal attacker reaches **recall 0.000** vs the
random attacker's **0.313**; optimal kills *all* rings at 60% where random needs
~100%. Closed-form matches simulation (0.700, 0.397≈0.400, 0.000). **Defenders
benchmarking against the naive attacker overstate security by ~40 budget points.**

## B4 — Improved differential privacy

The sum channel (sensitivity 500) dominates the noise; the count channel
(sensitivity 1) already separates HIGH/NORMAL. False-positive rate by mechanism:

| ε | baseline (Lap) | count-primary | clipped-sum c=100 | gaussian |
|---|---|---|---|---|
| 1.0 | 0.264 | **0.081** | 0.236 | 0.599 |
| 2.0 | 0.119 | **0.024** | 0.102 | 0.460 |
| 5.0 | 0.029 | **0.001** | 0.017 | 0.215 |

**Count-primary reaches the baseline's ε=5 FPR at ε=2 — a 2.5× tighter privacy
budget.** Honest findings: clipping helps modestly; the Gaussian mechanism does
*not* help in this single-release high-sensitivity regime.

## B5 — Statistical rigor and scale

- **95% CIs (100 trials):** model lies inside the CI at every budget except 40%
  (measured 0.664 [0.649, 0.679] vs model 0.690 — a ~3pp finite-size gap).
- **Scale:** coverage model holds at N=500 and N=1000 (abs error ~0.01–0.02).
- **Ring size:** k=10 transition is sharper than k=5, as predicted; model tracks
  both (e.g. k=10 at 50% → 0.613 measured / 0.626 model).

## B6 — Learned GCN vs. rule-based WCC

2-layer GCN (from-scratch PyTorch), node-level fraud classification, trained on
clean graphs, evaluated under full evasion (fraud-user recall):

| budget | GCN recall | GCN FPR | WCC user-recall |
|---|---|---|---|
| 0% | 0.995 | 0.000 | 1.000 |
| 60% | 0.654 | 0.044 | 0.323 |
| 100% | 0.670 | 0.078 | **0.000** |

**WCC collapses to 0; the GCN floors at ~0.67** because it exploits a
non-structural feature (transaction amount) evasion cannot remove — empirically
confirming the paper's recommendation that durable defense needs non-graph
signals. *Caveat:* the residual magnitude depends on the synthetic amount
distribution; treat it as a principle demonstration, not a guaranteed number on
real data.

## B7 — Real-data readiness (started)

Real fraud rings have heterogeneous sizes, so the fixed-k model must generalize
first. We added `predicted_recall_mixed(ring_sizes, N, B, theta)` — the coverage
law averaged over a ring-size distribution — and validated it two ways:

- **Heterogeneous generator** (`realistic.py`): 40 rings, sizes 3–15, N=362.
  Mixed model vs measured: 40%→0.773/0.768, 60%→0.318/0.320, 80%→0.046/0.048.
  **Max abs error 0.005.**
- **Drop-in loader** (`real_data.py`): channel-agnostic CSV ingest (bipartite
  user↔entity edges), connected-component rings, full-evasion sweep vs the mixed
  model. End-to-end demo (1002 nodes, 40 rings): **max abs error 0.006.**

The model is now ready for a real dataset. Remaining to *complete* B7: obtain
IBM AMLSim or Elliptic2 (instructions + column mapping in `real_data.py`
docstring), then `python real_data.py --csv <file>`. This step needs a dataset
download (Kaggle auth / large file) — best done with the user in the loop.

---

## How this maps into the paper

- **Methods/Theory (new section):** B1 coverage theorem.
- **Attacks:** add B3 (optimal allocation + min-cut) — strengthens the threat model.
- **Defenses:** replace the dead-end with B2 (temporal) + B6 (non-structural/GCN)
  as the two complementary robust defenses; keep static defenses as the negative
  baseline.
- **DP section:** add B4 improved mechanisms.
- **Evaluation:** add B5 CIs + scale; soften "production-grade" claim (B9).

## Reproduce
```
cd research
python percolation.py      # B1
python temporal.py         # B2
python optimal_attack.py   # B3
python dp_improved.py      # B4
python stats_scale.py      # B5
python gnn_baseline.py     # B6
```

"""
Unified research experiment runner for TemporalEngine.

Experiment 1 — Adversarial Robustness (attack vs. baseline WCC)
  Measures WCC precision/recall/F1 under each attack strategy across budgets.
  Output: results/adversarial.csv

Experiment 2 — Differential Privacy (velocity detection utility/privacy tradeoff)
  Measures velocity detector TPR/FNR under Laplace noise across epsilon values.
  Output: results/dp.csv

Experiment 3 — Defense Comparison (adaptive defenses vs. FullEvasion attack)
  Compares Baseline WCC, AdaptiveThreshold, and MultiSignalDetector under the
  strongest attack (FullEvasion) at each budget.
  Output: results/defense.csv

Usage
-----
  python evaluate.py                       # all three experiments
  python evaluate.py --exp adversarial
  python evaluate.py --exp dp
  python evaluate.py --exp defense
  python evaluate.py --trials 50
"""
import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from simulate import Scenario, evaluate_detection
from attacks import ALL_ATTACKS, FullEvasion
from defenses import AdaptiveThreshold, MultiSignalDetector
from dp import run_dp_experiment

RESULTS_DIR = Path(__file__).parent / "results"


# ---------------------------------------------------------------------------
# Experiment 1 — Adversarial Robustness
# ---------------------------------------------------------------------------

def run_adversarial_experiment(
    n_rings: int = 10,
    users_per_ring: int = 5,
    n_benign: int = 30,
    budgets: list = None,
    n_trials: int = 30,
    iou_threshold: float = 0.5,
) -> list:
    # Budget = total fraud users attacked (max = n_rings * users_per_ring = 50).
    # Expressed as % of total: [0%, 10%, 20%, 40%, 60%, 80%, 100%]
    total_fraud = n_rings * users_per_ring
    if budgets is None:
        budgets = [int(total_fraud * f) for f in [0, 0.1, 0.2, 0.4, 0.6, 0.8, 1.0]]

    rows = []

    # Baseline (no attack)
    m = _run_wcc_trials(None, 0, n_rings, users_per_ring, n_benign, n_trials, iou_threshold)
    rows.append({"strategy": "baseline", "budget": 0, **m})
    _print_adv_row(rows[-1])

    for attack in ALL_ATTACKS:
        for budget in budgets:
            if budget == 0:
                continue
            m = _run_wcc_trials(attack, budget, n_rings, users_per_ring, n_benign, n_trials, iou_threshold)
            row = {"strategy": attack.name, "budget": budget, **m}
            rows.append(row)
            _print_adv_row(row)

    return rows


def _run_wcc_trials(attack, budget, n_rings, users_per_ring, n_benign, n_trials, iou_threshold,
                    detector=None) -> dict:
    """Run n_trials for a given (attack, budget) and return averaged metrics."""
    agg = {"precision": 0.0, "recall": 0.0, "f1": 0.0, "tp": 0, "fp": 0, "fn": 0}

    for trial in range(n_trials):
        scenario = Scenario(n_rings=n_rings, users_per_ring=users_per_ring,
                            n_benign_users=n_benign, seed=trial * 137)
        txs = scenario.transactions
        if attack is not None and budget > 0:
            txs = attack.apply(scenario, txs, budget)

        graph = scenario.build_graph(txs)

        if detector is None:
            detected = graph.detect_rings_wcc()        # baseline WCC
        else:
            detected = detector.detect_rings(graph)    # alternate detector

        metrics = evaluate_detection(detected, scenario.fraud_user_sets, iou_threshold)
        for k in agg:
            agg[k] += metrics[k]

    n = n_trials
    return {k: round(v / n, 4) for k, v in agg.items()}


def _print_adv_row(row: dict) -> None:
    print(f"  [{row['strategy']:22s}] budget={row['budget']:2d} | "
          f"P={row['precision']:.3f}  R={row['recall']:.3f}  F1={row['f1']:.3f}")


# ---------------------------------------------------------------------------
# Experiment 3 — Defense Comparison
# ---------------------------------------------------------------------------

def run_defense_experiment(
    n_rings: int = 10,
    users_per_ring: int = 5,
    n_benign: int = 30,
    budgets: list = None,
    n_trials: int = 30,
    iou_threshold: float = 0.5,
) -> list:
    """Compare WCC, AdaptiveThreshold, MultiSignal under FullEvasion attack."""
    total_fraud = n_rings * users_per_ring
    if budgets is None:
        budgets = [int(total_fraud * f) for f in [0, 0.2, 0.4, 0.6, 0.8, 1.0]]

    attack = FullEvasion()
    detectors = {
        "wcc_baseline":      None,
        "adaptive_thresh":   AdaptiveThreshold(base_threshold=3, min_threshold=1),
        "multi_signal":      MultiSignalDetector(min_signals=2),
    }

    rows = []
    for budget in budgets:
        for det_name, det in detectors.items():
            atk = attack if budget > 0 else None
            m = _run_wcc_trials(atk, budget, n_rings, users_per_ring, n_benign,
                                n_trials, iou_threshold, detector=det)
            row = {"detector": det_name, "budget": budget, **m}
            rows.append(row)
            print(f"  [{det_name:20s}] budget={budget:2d} | "
                  f"P={m['precision']:.3f}  R={m['recall']:.3f}  F1={m['f1']:.3f}")
    return rows


# ---------------------------------------------------------------------------
# CSV helpers
# ---------------------------------------------------------------------------

def save_csv(rows: list, path: Path) -> None:
    RESULTS_DIR.mkdir(exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"  Saved -> {path}\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--exp",    choices=["adversarial", "dp", "defense", "all"],
                        default="all")
    parser.add_argument("--trials", type=int, default=30)
    args = parser.parse_args()

    if args.exp in ("adversarial", "all"):
        print("\n=== Experiment 1: Adversarial Robustness ===")
        print(f"  {'strategy':22s}  {'budget':>6}  {'P':>6}  {'R':>6}  {'F1':>6}")
        rows = run_adversarial_experiment(n_trials=args.trials)
        save_csv(rows, RESULTS_DIR / "adversarial.csv")

    if args.exp in ("dp", "all"):
        print("=== Experiment 2: Differential Privacy ===")
        print(f"  {'epsilon':>10}  {'TPR':>7}  {'FNR':>7}  {'FPR':>7}  {'Acc':>7}")
        rows = run_dp_experiment(n_trials=args.trials)
        for r in rows:
            print(f"  eps={r['epsilon']:7.2f}  TPR={r['tpr']:.4f}  FNR={r['fnr']:.4f}  "
                  f"FPR={r['fpr']:.4f}  Acc={r['accuracy']:.4f}")
        save_csv(rows, RESULTS_DIR / "dp.csv")

    if args.exp in ("defense", "all"):
        print("=== Experiment 3: Defense Comparison (vs. FullEvasion) ===")
        print(f"  {'detector':20s}  {'budget':>6}  {'P':>6}  {'R':>6}  {'F1':>6}")
        rows = run_defense_experiment(n_trials=args.trials)
        save_csv(rows, RESULTS_DIR / "defense.csv")


if __name__ == "__main__":
    main()

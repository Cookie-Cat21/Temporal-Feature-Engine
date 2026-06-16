"""
Statistical rigor and scale validation (B5).

(1) CONFIDENCE INTERVALS. The paper reports point estimates over 30 Monte Carlo
    trials. Here we collect the per-trial recall distribution and report
    mean +/- 95% CI (normal approximation) so claims carry uncertainty.

(2) SCALE. The paper uses N=50 fraud users (10 rings x 5). We re-run at
    N=500 (100 rings x 5) and N=1000 (200 rings x 5) to show the findings and
    the closed-form coverage model hold at scale (the model is exact in
    expectation for any N).

(3) RING-SIZE PREDICTION. The coverage model predicts the transition SHARPENS
    as ring size k grows (the hypergeometric tail concentrates). We validate the
    k=10 prediction empirically and contrast with k=5.
"""

import math
from pathlib import Path
import csv

from simulate import Scenario, evaluate_detection
from attacks import FullEvasion
from percolation import predicted_recall

RESULTS_DIR = Path(__file__).parent / "results"


def _trial_recalls(attack, budget, n_rings, k, n_benign, n_trials, theta):
    vals = []
    for trial in range(n_trials):
        sc = Scenario(
            n_rings=n_rings, users_per_ring=k, n_benign_users=n_benign, seed=trial * 137
        )
        txs = (
            attack.apply(sc, sc.transactions, budget)
            if (attack and budget > 0)
            else sc.transactions
        )
        g = sc.build_graph(txs)
        vals.append(
            evaluate_detection(g.detect_rings_wcc(), sc.fraud_user_sets, theta)[
                "recall"
            ]
        )
    return vals


def ci95(vals):
    n = len(vals)
    mean = sum(vals) / n
    var = sum((v - mean) ** 2 for v in vals) / (n - 1) if n > 1 else 0.0
    half = 1.96 * math.sqrt(var / n)
    return mean, half


def run_ci(n_trials=100, k=5, n_rings=10, n_benign=30, theta=0.5):
    N = n_rings * k
    budgets = [int(N * f) for f in [0, 0.2, 0.4, 0.6, 0.8, 1.0]]
    print(f"(1) Recall with 95% CI under FullEvasion (n_trials={n_trials}, N={N}):")
    print(f"{'budget%':>8} {'recall':>8} {'95% CI':>16} {'model':>8}")
    rows = []
    atk = FullEvasion()
    for B in budgets:
        vals = _trial_recalls(
            atk if B > 0 else None, B, n_rings, k, n_benign, n_trials, theta
        )
        mean, half = ci95(vals)
        pred = predicted_recall(B, N, k, theta)
        print(
            f"{B / N:>7.0%} {mean:>8.3f} {f'[{mean - half:.3f},{mean + half:.3f}]':>16} {pred:>8.3f}"
        )
        rows.append(
            {
                "k": k,
                "N": N,
                "budget": B,
                "budget_pct": round(B / N, 3),
                "recall_mean": round(mean, 4),
                "ci95_half": round(half, 4),
                "model": round(pred, 4),
            }
        )
    return rows


def run_scale(n_trials=20, theta=0.5):
    print("\n(2) Scale validation (FullEvasion, recall vs model, budget=60%):")
    print(f"{'config':>22} {'measured':>10} {'model':>8} {'abs.err':>8}")
    rows = []
    for n_rings, k in [(10, 5), (100, 5), (200, 5)]:
        N = n_rings * k
        B = int(0.6 * N)
        vals = _trial_recalls(
            FullEvasion(), B, n_rings, k, n_rings * 3, n_trials, theta
        )
        mean = sum(vals) / len(vals)
        pred = predicted_recall(B, N, k, theta)
        print(
            f"{f'{n_rings} rings x {k} (N={N})':>22} {mean:>10.3f} {pred:>8.3f} {abs(mean - pred):>8.3f}"
        )
        rows.append(
            {
                "n_rings": n_rings,
                "k": k,
                "N": N,
                "budget_pct": 0.6,
                "recall_mean": round(mean, 4),
                "model": round(pred, 4),
            }
        )
    return rows


def run_ringsize(n_trials=40, theta=0.5):
    print("\n(3) Ring-size prediction: transition sharpens as k grows")
    print(f"{'k':>3} {'budget%':>8} {'measured':>10} {'model':>8}")
    rows = []
    for k in [5, 10]:
        n_rings = 20
        N = n_rings * k
        for f in [0.2, 0.4, 0.5, 0.6, 0.8]:
            B = int(f * N)
            vals = _trial_recalls(FullEvasion(), B, n_rings, k, 60, n_trials, theta)
            mean = sum(vals) / len(vals)
            pred = predicted_recall(B, N, k, theta)
            print(f"{k:>3} {f:>7.0%} {mean:>10.3f} {pred:>8.3f}")
            rows.append(
                {
                    "k": k,
                    "N": N,
                    "budget_pct": f,
                    "recall_mean": round(mean, 4),
                    "model": round(pred, 4),
                }
            )
        print()
    return rows


def save_csv(rows, path):
    RESULTS_DIR.mkdir(exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"  Saved -> {path}")


if __name__ == "__main__":
    print("=== B5: Statistical rigor and scale ===")
    r1 = run_ci()
    r2 = run_scale()
    r3 = run_ringsize()
    save_csv(r1, RESULTS_DIR / "stats_ci.csv")
    save_csv(r2, RESULTS_DIR / "stats_scale.csv")
    save_csv(r3, RESULTS_DIR / "stats_ringsize.csv")

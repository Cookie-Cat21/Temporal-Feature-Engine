"""
B7 (part 1): validate the coverage theorem on REALISTIC heterogeneous rings.

Real fraud rings vary in size and in how densely they share infrastructure;
the paper's experiments used a fixed k=5. Before applying the theory to a real
dataset we must show it survives heterogeneity. This module builds rings whose
sizes are drawn from a distribution and whose shared-infra counts scale with
size, then checks the GENERALIZED coverage model (percolation.predicted_recall_mixed)
against simulation.

If the generalized model tracks the heterogeneous simulation, the theory is
ready for real data (real_data.py), where ring sizes come from the dataset.
"""

import random
from pathlib import Path
import csv

import networkx as nx

from simulate import FraudGraph, Transaction, GroundTruthRing, evaluate_detection
from attacks import FullEvasion
from percolation import predicted_recall_mixed

RESULTS_DIR = Path(__file__).parent / "results"


class RealisticScenario:
    """Rings with sizes ~ Uniform[min_k, max_k] and infra counts scaling with size."""

    def __init__(self, n_rings=40, min_k=3, max_k=15, n_benign=80, seed=42):
        random.seed(seed)
        self.ground_truth = []
        self.transactions = []
        for ring_id in range(n_rings):
            k = random.randint(min_k, max_k)
            # shared infra grows ~sqrt(k): bigger rings share a bit more, but
            # users-per-infra stays high (realistic co-location).
            n_dev = max(1, k // 3)
            n_ip = max(1, k // 3)
            n_merch = max(1, k // 4)
            users = [f"fr_{ring_id}_u{i}" for i in range(k)]
            devices = [f"fr_{ring_id}_d{i}" for i in range(n_dev)]
            ips = [f"fr_{ring_id}_ip{i}" for i in range(n_ip)]
            merchants = [f"fr_{ring_id}_m{i}" for i in range(n_merch)]
            self.ground_truth.append(
                GroundTruthRing(ring_id, users, devices, ips, merchants)
            )
            for u in users:
                self.transactions.append(
                    Transaction(
                        user_id=u,
                        merchant_id=random.choice(merchants),
                        device_id=random.choice(devices),
                        ip_address=random.choice(ips),
                        amount=round(random.uniform(100, 500), 2),
                        is_fraud=True,
                        ring_id=ring_id,
                    )
                )
        for i in range(n_benign):
            self.transactions.append(
                Transaction(
                    user_id=f"benign_u{i}",
                    merchant_id=f"benign_m{i}",
                    device_id=f"benign_d{i}",
                    ip_address=f"benign_ip{i}",
                    amount=round(random.uniform(10, 200), 2),
                    is_fraud=False,
                )
            )

    def build_graph(self, transactions=None):
        g = FraudGraph()
        for tx in transactions if transactions is not None else self.transactions:
            g.add_transaction(tx)
        return g

    @property
    def fraud_user_sets(self):
        return [set(r.users) for r in self.ground_truth]

    @property
    def ring_sizes(self):
        return [len(r.users) for r in self.ground_truth]


def run(n_trials=30, theta=0.5):
    print("=== B7.1: coverage theorem on heterogeneous ring sizes ===")
    # Fixed structure across trials (same sizes), random attack allocation per trial.
    base = RealisticScenario(seed=0)
    sizes = base.ring_sizes
    N = sum(sizes)
    print(
        f"{len(sizes)} rings, sizes {min(sizes)}-{max(sizes)} (mean {N / len(sizes):.1f}), "
        f"N={N} fraud users, theta={theta}"
    )
    print(f"{'budget%':>8} {'measured':>10} {'mixed-model':>12} {'abs.err':>8}")
    rows = []
    for f in [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]:
        B = int(f * N)
        meas = 0.0
        for trial in range(n_trials):
            sc = RealisticScenario(seed=trial * 137)  # resampled sizes per trial
            Nt = sum(sc.ring_sizes)
            Bt = int(f * Nt)
            txs = (
                FullEvasion().apply(sc, sc.transactions, Bt)
                if Bt > 0
                else sc.transactions
            )
            g = sc.build_graph(txs)
            meas += evaluate_detection(g.detect_rings_wcc(), sc.fraud_user_sets, theta)[
                "recall"
            ]
        meas /= n_trials
        # model uses the expected size profile (base sizes / N)
        pred = predicted_recall_mixed(sizes, N, B, theta)
        print(f"{f:>7.0%} {meas:>10.3f} {pred:>12.3f} {abs(meas - pred):>8.3f}")
        rows.append(
            {"budget_pct": f, "measured": round(meas, 4), "mixed_model": round(pred, 4)}
        )
    return rows


def save_csv(rows, path):
    RESULTS_DIR.mkdir(exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"  Saved -> {path}")


if __name__ == "__main__":
    rows = run()
    save_csv(rows, RESULTS_DIR / "realistic.csv")

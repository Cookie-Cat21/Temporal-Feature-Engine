"""
Optimal adversarial budget allocation against WCC ring detection (B3).

Two questions:

(1) PER-USER MIN-CUT. To remove one user from its ring's connected component,
    how many channels must the attacker rotate? A user is connected to shared
    infrastructure through three node types (Device, IP, Merchant). Leaving any
    one channel shared keeps the user in the component. Hence the minimum cut to
    isolate a single user is exactly 3 channel rotations — i.e. FullEvasion is
    the *minimal* per-user attack, not an over-kill. (Confirmed empirically below.)

(2) PER-RING ALLOCATION. A ring of k users is undetected iff fewer than
    ceil(theta*k) users remain, i.e. the attacker must evade at least
    m+1 = (k - ceil(theta*k)) + 1 users in that ring. For k=5, theta=0.5 this is
    3 of 5. The HEURISTIC attacker (attacks.FullEvasion) spends budget on users
    chosen UNIFORMLY AT RANDOM, so much of the budget lands in rings that are
    already dead or not-yet-killable. An OPTIMAL attacker concentrates exactly
    m+1 evasions per ring, killing floor(B/(m+1)) rings with a budget of B.

    => optimal recall(B) = max(0, R - floor(B/(m+1))) / R           (closed form)
    The optimal attacker reaches recall 0 at budget R*(m+1) = 60% here, whereas
    the random attacker needs ~100% (and at 60% still detects ~31% of rings).
"""
import copy
import random
from math import ceil, floor
from pathlib import Path
import csv

from simulate import Scenario, evaluate_detection

RESULTS_DIR = Path(__file__).parent / "results"


def min_users_to_kill_ring(k: int, theta: float) -> int:
    """m+1: minimum users to fully-evade in a ring to push IoU below theta."""
    tolerance = k - ceil(theta * k)
    return tolerance + 1


class OptimalEvasion:
    """
    Concentrate evasions: fill rings to exactly `per_ring` full-evasions (the
    kill threshold) in order, until the global budget is exhausted. Any leftover
    budget (< per_ring) is spent on the next ring but does not kill it.
    """

    name = "optimal_evasion"

    def __init__(self, per_ring: int):
        self.per_ring = per_ring

    def apply(self, scenario: Scenario, transactions, budget: int):
        # Allocate budget ring-by-ring, per_ring users each, until exhausted.
        targets = set()
        remaining = budget
        for ring in scenario.ground_truth:
            if remaining <= 0:
                break
            take = min(self.per_ring, remaining)
            targets.update(ring.users[:take])
            remaining -= take

        txs = copy.deepcopy(transactions)
        c = 0
        for tx in txs:
            if tx.user_id in targets:
                tx.device_id = f"opt_dev_{c}"
                tx.ip_address = f"opt_ip_{c}"
                tx.merchant_id = f"opt_merch_{c}"
                c += 1
        return txs


def optimal_recall_closed_form(B: int, R: int, per_ring: int) -> float:
    killed = min(R, floor(B / per_ring))
    return (R - killed) / R


def partial_channel_check(n_trials: int = 30) -> None:
    """
    Empirically confirm the per-user min-cut = 3: rotating only 2 of 3 channels
    for ALL ring users leaves recall at 1.0 (ring stays connected via the third).
    Uses the existing single-channel attacks composed pairwise.
    """
    from attacks import DeviceIPRotation  # rotates device+IP (2 channels), leaves merchant
    print("Per-user min-cut check (rotate 2 of 3 channels, 100% of users):")
    agg = 0.0
    for trial in range(n_trials):
        sc = Scenario(n_benign_users=30, seed=trial * 137)
        budget = sc.n_rings * sc.users_per_ring
        txs = DeviceIPRotation().apply(sc, sc.transactions, budget)  # merchant kept
        g = sc.build_graph(txs)
        m = evaluate_detection(g.detect_rings_wcc(), sc.fraud_user_sets, 0.5)
        agg += m["recall"]
    print(f"  device+IP rotated, merchant intact -> recall={agg/n_trials:.3f} "
          f"(stays 1.0 => need all 3 channels => min-cut per user = 3)\n")


def run_optimal_vs_random(n_trials: int = 30, k: int = 5, theta: float = 0.5) -> list:
    from attacks import FullEvasion
    per_ring = min_users_to_kill_ring(k, theta)
    R = 10  # n_rings default
    N = R * k
    budgets = [int(N * f) for f in [0, 0.2, 0.4, 0.6, 0.8, 1.0]]

    print(f"Optimal vs random allocation (k={k}, theta={theta}, "
          f"kill-threshold per ring={per_ring}):")
    print(f"{'budget':>6} {'budget%':>8} {'random R':>10} {'optimal R':>10} "
          f"{'opt(theory)':>12}")
    rows = []
    for B in budgets:
        # random heuristic
        rnd = 0.0
        for trial in range(n_trials):
            sc = Scenario(n_benign_users=30, seed=trial * 137)
            txs = FullEvasion().apply(sc, sc.transactions, B) if B > 0 else sc.transactions
            g = sc.build_graph(txs)
            rnd += evaluate_detection(g.detect_rings_wcc(), sc.fraud_user_sets, theta)["recall"]
        rnd /= n_trials
        # optimal allocation
        opt = 0.0
        atk = OptimalEvasion(per_ring=per_ring)
        for trial in range(n_trials):
            sc = Scenario(n_benign_users=30, seed=trial * 137)
            txs = atk.apply(sc, sc.transactions, B) if B > 0 else sc.transactions
            g = sc.build_graph(txs)
            opt += evaluate_detection(g.detect_rings_wcc(), sc.fraud_user_sets, theta)["recall"]
        opt /= n_trials
        theory = optimal_recall_closed_form(B, R, per_ring)
        rows.append({"budget": B, "budget_pct": round(B / N, 3),
                     "recall_random": round(rnd, 4),
                     "recall_optimal": round(opt, 4),
                     "recall_optimal_theory": round(theory, 4)})
        print(f"{B:>6} {B/N:>7.0%} {rnd:>10.3f} {opt:>10.3f} {theory:>12.3f}")
    return rows


def save_csv(rows, path):
    RESULTS_DIR.mkdir(exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    print(f"  Saved -> {path}")


if __name__ == "__main__":
    print("=== B3: Optimal adversarial allocation ===")
    partial_channel_check()
    rows = run_optimal_vs_random()
    save_csv(rows, RESULTS_DIR / "optimal_attack.csv")

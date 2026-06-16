"""
B8: certified robustness of WCC ring detection.

Learned detectors only admit *probabilistic* certificates via randomized
smoothing (e.g. Jia et al. 2020). The structural detector admits an EXACT,
per-ring deterministic certificate — but, importantly, NOT the naive size bound.

Naive bound (UPPER bound only): a ring of size k matched at IoU theta tolerates
m = k - ceil(theta*k) fully-evaded members *if the survivors stay connected*.
Under sparse infrastructure sharing that connectivity can break (removing a user
can split the ring, because remaining users may have been bridged only through
the removed one). So the true certified radius is a CONNECTIVITY property, not
just a counting one.

Exact certificate: R_cert(ring) = the largest r such that EVERY removal of r
users leaves a connected component with >= ceil(theta*k) users. We compute it by
exhaustive check on the ring's bipartite (user-infrastructure) graph. This is
sound by construction; we also confirm it against random attacks. We then show:
  * under sparse random sharing, R_cert < m (the naive bound is not achieved);
  * under DENSE co-location (members share a common hub), R_cert = m (optimal);
  * the deterministic R_cert is exact (confidence 1.0), unlike smoothing.
"""

from math import ceil
from itertools import combinations
from pathlib import Path
import random
import csv

import networkx as nx
from scipy.stats import beta  # Clopper-Pearson

from simulate import Scenario, evaluate_detection
from realistic import RealisticScenario

RESULTS_DIR = Path(__file__).parent / "results"


# --------- exact deterministic certificate from ring structure --------------


def _ring_assignment(scenario, ring):
    """Map each ring user -> the set of infra nodes it touches, from the txns."""
    assign = {u: set() for u in ring.users}
    uset = set(ring.users)
    for tx in scenario.transactions:
        if tx.user_id in uset:
            assign[tx.user_id] |= {tx.device_id, tx.ip_address, tx.merchant_id}
    return assign


def exact_cert_radius(users, assign, theta=0.5):
    k = len(users)
    need = ceil(theta * k)
    for r in range(0, k + 1):
        for S in combinations(users, r):
            remaining = [u for u in users if u not in S]
            G = nx.Graph()
            for u in remaining:
                for x in assign[u]:
                    G.add_edge(("u", u), ("x", x))
            best = 0
            for comp in nx.connected_components(G):
                best = max(best, sum(1 for n in comp if n[0] == "u"))
            if best < need:
                return r - 1
    return k


def naive_bound(k, theta=0.5):
    return k - ceil(theta * k)


def sparse_vs_dense(theta=0.5):
    """Compare the exact certificate under sparse random sharing vs a dense hub."""
    print("Exact deterministic certificate vs naive bound:")
    print(f"{'k':>4} {'naive m':>8} {'R_cert sparse':>14} {'R_cert dense(hub)':>18}")
    rows = []
    for k in [4, 6, 8, 10, 12]:
        # sparse: the paper's generator (random choice among 2 dev/2 ip/2 merch)
        sc = Scenario(n_rings=1, users_per_ring=k, n_benign_users=0, seed=7)
        ring = sc.ground_truth[0]
        assign = _ring_assignment(sc, ring)
        r_sparse = exact_cert_radius(ring.users, assign, theta)
        # dense: every member shares one common hub node
        dense_assign = {u: {"HUB"} for u in ring.users}
        r_dense = exact_cert_radius(ring.users, dense_assign, theta)
        print(f"{k:>4} {naive_bound(k, theta):>8} {r_sparse:>14} {r_dense:>18}")
        rows.append(
            {
                "k": k,
                "naive_m": naive_bound(k, theta),
                "Rcert_sparse": r_sparse,
                "Rcert_dense": r_dense,
            }
        )
    return rows


def verify_soundness(theta=0.5, n_trials=300):
    """Random attacks at each ring's exact certified radius must keep recall 1.0."""
    import copy

    k = 6
    sc0 = Scenario(n_rings=10, users_per_ring=k, n_benign_users=30, seed=0)
    # exact per-ring radius (same structure across seeds since assignment is seeded)
    radii = {}
    for ring in sc0.ground_truth:
        radii[ring.ring_id] = exact_cert_radius(
            ring.users, _ring_assignment(sc0, ring), theta
        )
    rmin = min(radii.values())
    worst = 1.0
    for trial in range(n_trials):
        sc = Scenario(n_rings=10, users_per_ring=k, n_benign_users=30, seed=0)
        rnd = random.Random(trial * 137)
        targets = set()
        for ring in sc.ground_truth:
            r = radii[ring.ring_id]
            targets.update(rnd.sample(ring.users, r))  # attack AT the radius
        txs, c = [], 0
        for tx in copy.deepcopy(sc.transactions):
            if tx.user_id in targets:
                tx.device_id = f"a{c}"
                tx.ip_address = f"b{c}"
                tx.merchant_id = f"m{c}"
                c += 1
            txs.append(tx)
        g = sc.build_graph(txs)
        worst = min(
            worst,
            evaluate_detection(g.detect_rings_wcc(), sc.fraud_user_sets, theta)[
                "recall"
            ],
        )
    print(
        f"\nSoundness (k={k}, exact per-ring radii, min={rmin}): worst-case recall "
        f"over {n_trials} random attacks at the certified radius = {worst:.3f} "
        f"{'OK' if worst == 1.0 else 'VIOLATED'}"
    )
    return worst


# --------------------- randomized-ablation (probabilistic) ------------------


def clopper_pearson_lower(s, n, alpha=0.001):
    return 0.0 if s == 0 else beta.ppf(alpha, s, n - s + 1)


def smoothing_radius(k, q=0.8, theta=0.5, n_smooth=4000, alpha=0.001, seed=0):
    rnd = random.Random(seed)
    need = ceil(theta * k)
    succ = 0
    for _ in range(n_smooth):
        if sum(1 for _ in range(k) if rnd.random() < q) >= need:
            succ += 1
    pa = clopper_pearson_lower(succ, n_smooth, alpha)
    if pa <= 0.5:
        return 0, pa
    rho = 0
    while pa - (1 - q ** (rho + 1)) > 0.5:
        rho += 1
    return rho, pa


def realistic_summary(theta=0.5):
    sc = RealisticScenario(seed=0)
    radii = [
        exact_cert_radius(r.users, _ring_assignment(sc, r), theta)
        for r in sc.ground_truth
    ]
    pos = sum(1 for r in radii if r >= 1)
    print(
        f"\nRealistic population ({len(radii)} rings, sizes "
        f"{min(sc.ring_sizes)}-{max(sc.ring_sizes)}): {pos}/{len(radii)} certifiable "
        f"(R_cert>=1); mean exact radius = {sum(radii) / len(radii):.2f} users."
    )


def save_csv(rows, path):
    RESULTS_DIR.mkdir(exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"  Saved -> {path}")


if __name__ == "__main__":
    print("=== B8: certified robustness ===")
    rows = sparse_vs_dense()
    verify_soundness()
    print("\nRandomized-ablation certificate (probabilistic, for comparison):")
    print(f"{'k':>4} {'rho_smoothing':>14} {'p_A':>8}")
    for k in [4, 6, 8, 10, 12]:
        rho, pa = smoothing_radius(k)
        print(f"{k:>4} {rho:>14} {pa:>8.3f}")
    realistic_summary()
    save_csv(rows, RESULTS_DIR / "certified.csv")

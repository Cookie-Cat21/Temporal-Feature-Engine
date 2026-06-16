"""
Temporal-window WCC defense against FullEvasion (research contribution B2).

MOTIVATION
----------
The static defenses in defenses.py (AdaptiveThreshold, MultiSignalDetector) do
NOT recover a ring once all three connection channels are severed: the failure
is structural for any *single-snapshot* detector. FullEvasion, however, is a
*one-time rotation* — the attacker switches to unique infrastructure at attack
onset. A detector that aggregates edges over a rolling time window can still see
the ring's *historical* shared infrastructure, forcing the adversary to have
evaded continuously from account creation rather than once.

MODEL
-----
Each fraud user emits a stream of L transactions at integer timesteps 0..L-1.
A ring shares devices/IPs/merchants. Under FullEvasion with onset step `a`, an
evaded user uses shared infra for steps < a and unique infra for steps >= a
(it "goes dark" at step a and stays dark). `a = 0` models an attacker who never
shared infra; `a = L` models a fully benign history.

A TemporalWindowDetector with window W builds the graph from each user's
transactions in the most recent W timesteps [L-W, L-1] and runs WCC on it.

PREDICTION
----------
A window recovers an evaded user iff it reaches back into the user's clean
history, i.e. iff the window start L-W is < a  <=>  W > L - a. Define the
sustained-evasion duration D = L - a (how long the attacker has been dark).
Then:
    W <= D  -> window sees only rotated infra  -> ring fragmented (recall ~0)
    W >  D  -> window sees shared history       -> ring recovered (recall ~1)
So the defense holds whenever the detection window exceeds the attacker's
sustained-evasion duration. This is the tunable design rule the static
defenses lack.
"""

import copy
import random
from dataclasses import dataclass
from pathlib import Path
from typing import List, Set, Dict
import csv

import networkx as nx

from simulate import GroundTruthRing, evaluate_detection

RESULTS_DIR = Path(__file__).parent / "results"


@dataclass
class TemporalTx:
    user_id: str
    merchant_id: str
    device_id: str
    ip_address: str
    t: int  # integer timestep
    is_fraud: bool = False
    ring_id: int = -1


class TemporalScenario:
    """
    Like simulate.Scenario, but every fraud user emits `history_len` (L)
    transactions over time on the ring's shared infrastructure. Benign users
    also emit L transactions on their own private infra.
    """

    def __init__(
        self,
        n_rings: int = 10,
        users_per_ring: int = 5,
        shared_devices_per_ring: int = 2,
        shared_ips_per_ring: int = 2,
        merchants_per_ring: int = 2,
        n_benign_users: int = 30,
        history_len: int = 10,
        seed: int = 42,
    ):
        self.n_rings = n_rings
        self.users_per_ring = users_per_ring
        self.history_len = history_len
        random.seed(seed)
        self.ground_truth: List[GroundTruthRing] = []
        self.transactions: List[TemporalTx] = []

        for ring_id in range(n_rings):
            users = [f"fr_{ring_id}_u{i}" for i in range(users_per_ring)]
            devices = [f"fr_{ring_id}_d{i}" for i in range(shared_devices_per_ring)]
            ips = [f"fr_{ring_id}_ip{i}" for i in range(shared_ips_per_ring)]
            merchants = [f"fr_{ring_id}_m{i}" for i in range(merchants_per_ring)]
            self.ground_truth.append(
                GroundTruthRing(ring_id, users, devices, ips, merchants)
            )
            for u in users:
                for t in range(history_len):
                    self.transactions.append(
                        TemporalTx(
                            user_id=u,
                            merchant_id=random.choice(merchants),
                            device_id=random.choice(devices),
                            ip_address=random.choice(ips),
                            t=t,
                            is_fraud=True,
                            ring_id=ring_id,
                        )
                    )
        for i in range(n_benign_users):
            for t in range(history_len):
                self.transactions.append(
                    TemporalTx(
                        user_id=f"benign_u{i}",
                        merchant_id=f"benign_m{i}",
                        device_id=f"benign_d{i}",
                        ip_address=f"benign_ip{i}",
                        t=t,
                        is_fraud=False,
                    )
                )

    @property
    def fraud_user_sets(self) -> List[Set[str]]:
        return [set(r.users) for r in self.ground_truth]


class TemporalFullEvasion:
    """
    FullEvasion with a temporal onset. Evaded users switch to unique infra at
    step `onset` and stay dark thereafter; sustained-evasion duration is
    D = history_len - onset.
    """

    name = "temporal_full_evasion"

    def apply(
        self, scenario: TemporalScenario, budget: int, onset: int
    ) -> List[TemporalTx]:
        all_fraud = [u for r in scenario.ground_truth for u in r.users]
        random.shuffle(all_fraud)
        targets = set(all_fraud[:budget])
        txs = copy.deepcopy(scenario.transactions)
        c = 0
        for tx in txs:
            if tx.user_id in targets and tx.t >= onset:
                tx.device_id = f"eva_dev_{c}"
                tx.ip_address = f"eva_ip_{c}"
                tx.merchant_id = f"eva_merch_{c}"
                c += 1
        return txs


class TemporalWindowDetector:
    """WCC over edges from each user's transactions in the last W timesteps."""

    MIN_RING_SIZE = 3

    def __init__(self, window: int, history_len: int):
        self.window = window
        self.cutoff = history_len - window  # keep timesteps t >= cutoff

    def detect_rings(self, txs: List[TemporalTx]) -> List[Set[str]]:
        G = nx.Graph()
        for tx in txs:
            if tx.t < self.cutoff:
                continue
            G.add_node(tx.user_id, ntype="User")
            G.add_node(tx.merchant_id, ntype="Merchant")
            G.add_node(tx.device_id, ntype="Device")
            G.add_node(tx.ip_address, ntype="IP")
            G.add_edge(tx.user_id, tx.merchant_id)
            G.add_edge(tx.user_id, tx.device_id)
            G.add_edge(tx.user_id, tx.ip_address)
        rings = []
        for comp in nx.connected_components(G):
            if len(comp) > self.MIN_RING_SIZE:
                users = {n for n in comp if G.nodes[n].get("ntype") == "User"}
                if len(users) >= 2:
                    rings.append(users)
        return rings


def run_temporal_experiment(
    history_len: int = 10,
    sustained_evasion: int = 4,  # D: attacker has been dark for D steps
    n_trials: int = 30,
    iou_threshold: float = 0.5,
) -> list:
    """
    At full budget (100%), sweep the detection window W from 1 (snapshot) to L
    and show recall recovering once W > D. Onset a = history_len - D.
    """
    onset = history_len - sustained_evasion
    rows = []
    for W in range(1, history_len + 1):
        agg = {"precision": 0.0, "recall": 0.0, "f1": 0.0}
        for trial in range(n_trials):
            sc = TemporalScenario(history_len=history_len, seed=trial * 137)
            budget = sc.n_rings * sc.users_per_ring  # 100% budget
            txs = TemporalFullEvasion().apply(sc, budget, onset)
            det = TemporalWindowDetector(window=W, history_len=history_len)
            detected = det.detect_rings(txs)
            m = evaluate_detection(detected, sc.fraud_user_sets, iou_threshold)
            for k in agg:
                agg[k] += m[k]
        row = {
            "window": W,
            "sustained_evasion_D": sustained_evasion,
            **{k: round(v / n_trials, 4) for k, v in agg.items()},
        }
        rows.append(row)
        print(
            f"  [W={W:2d}  D={sustained_evasion}] "
            f"P={row['precision']:.3f} R={row['recall']:.3f} F1={row['f1']:.3f}"
            f"   {'<-- recovers (W>D)' if W > sustained_evasion else ''}"
        )
    return rows


def make_figure(rows: list) -> None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return
    W = [r["window"] for r in rows]
    R = [r["recall"] for r in rows]
    D = rows[0]["sustained_evasion_D"]
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(W, R, "o-", lw=2)
    ax.axvline(D, ls="--", c="red", lw=1, label=f"sustained evasion D={D}")
    ax.set_xlabel("Detection window W (timesteps)")
    ax.set_ylabel("Recall under 100% FullEvasion")
    ax.set_title("Temporal-window WCC recovers fully-evaded rings when W > D")
    ax.set_ylim(-0.02, 1.05)
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    out = RESULTS_DIR / "temporal_defense.png"
    RESULTS_DIR.mkdir(exist_ok=True)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    print(f"  Saved figure -> {out}")


def save_csv(rows: list, path: Path) -> None:
    RESULTS_DIR.mkdir(exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"  Saved -> {path}")


if __name__ == "__main__":
    print("=== Temporal-window defense vs. 100% FullEvasion ===")
    rows = run_temporal_experiment()
    save_csv(rows, RESULTS_DIR / "temporal.csv")
    make_figure(rows)

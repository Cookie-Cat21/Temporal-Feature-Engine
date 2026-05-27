"""
Simulation engine for TemporalEngine research experiments.

Replicates the graph topology (Memgraph) and WCC-based ring detection
(ring_hunter.py) in-memory using NetworkX so experiments can run without
the full Docker stack.
"""
import random
import networkx as nx
from dataclasses import dataclass, field
from typing import List, Dict, Set


@dataclass
class Transaction:
    user_id: str
    merchant_id: str
    device_id: str
    ip_address: str
    amount: float
    is_fraud: bool = False
    ring_id: int = -1


@dataclass
class GroundTruthRing:
    ring_id: int
    users: List[str]
    devices: List[str]
    ips: List[str]
    merchants: List[str]


class FraudGraph:
    """
    In-memory replica of the TemporalEngine Memgraph topology.

    Node types: User, Merchant, Device, IP
    Edge types: TRANSACTED_WITH (User→Merchant), LOGGED_IN_FROM (User→Device/IP)

    WCC threshold mirrors ring_hunter.py: component_size > MIN_RING_SIZE (counts
    all node types, as the Cypher does).

    For evaluation, detected rings are matched against ground truth using
    the USER-only IoU — infrastructure nodes (devices, IPs, merchants) are
    excluded from the overlap calculation.
    """

    # Minimum component size to flag as a ring (mirrors ring_hunter.py `size > 3`)
    MIN_RING_SIZE = 3

    def __init__(self):
        self.G = nx.Graph()

    def add_transaction(self, tx: Transaction) -> None:
        self.G.add_node(tx.user_id,     ntype="User")
        self.G.add_node(tx.merchant_id, ntype="Merchant")
        self.G.add_node(tx.device_id,   ntype="Device")
        self.G.add_node(tx.ip_address,  ntype="IP")

        self.G.add_edge(tx.user_id, tx.merchant_id, etype="TRANSACTED_WITH", amount=tx.amount)
        self.G.add_edge(tx.user_id, tx.device_id,   etype="LOGGED_IN_FROM")
        self.G.add_edge(tx.user_id, tx.ip_address,  etype="LOGGED_IN_FROM")

    def detect_rings_wcc(self) -> List[Set[str]]:
        """
        Returns WCC components above MIN_RING_SIZE, each reduced to its
        User-typed nodes only (so evaluation can compare against ground truth
        rings which are also defined as sets of users).
        """
        components = nx.connected_components(self.G)
        rings = []
        for comp in components:
            if len(comp) > self.MIN_RING_SIZE:
                # Keep only User nodes for downstream evaluation
                user_nodes = {n for n in comp
                              if self.G.nodes[n].get("ntype") == "User"}
                if len(user_nodes) >= 2:  # at least 2 users to be a meaningful ring
                    rings.append(user_nodes)
        return rings

    def reset(self) -> None:
        self.G.clear()


class Scenario:
    """
    Builds a reproducible experimental scenario:
    - Plants N known fraud rings
    - Adds M benign users as background noise
    """

    def __init__(
        self,
        n_rings: int = 10,
        users_per_ring: int = 5,
        shared_devices_per_ring: int = 2,
        shared_ips_per_ring: int = 2,
        merchants_per_ring: int = 2,
        n_benign_users: int = 20,
        seed: int = 42,
    ):
        self.n_rings = n_rings
        self.users_per_ring = users_per_ring
        self.shared_devices_per_ring = shared_devices_per_ring
        self.shared_ips_per_ring = shared_ips_per_ring
        self.merchants_per_ring = merchants_per_ring
        self.n_benign_users = n_benign_users
        random.seed(seed)

        self.ground_truth: List[GroundTruthRing] = []
        self.transactions: List[Transaction] = []
        self._build()

    def _build(self) -> None:
        for ring_id in range(self.n_rings):
            users     = [f"fr_{ring_id}_u{i}" for i in range(self.users_per_ring)]
            devices   = [f"fr_{ring_id}_d{i}" for i in range(self.shared_devices_per_ring)]
            ips       = [f"fr_{ring_id}_ip{i}" for i in range(self.shared_ips_per_ring)]
            merchants = [f"fr_{ring_id}_m{i}" for i in range(self.merchants_per_ring)]

            self.ground_truth.append(GroundTruthRing(ring_id, users, devices, ips, merchants))

            for u in users:
                self.transactions.append(Transaction(
                    user_id=u,
                    merchant_id=random.choice(merchants),
                    device_id=random.choice(devices),
                    ip_address=random.choice(ips),
                    amount=round(random.uniform(100, 500), 2),
                    is_fraud=True,
                    ring_id=ring_id,
                ))

        for i in range(self.n_benign_users):
            self.transactions.append(Transaction(
                user_id=f"benign_u{i}",
                merchant_id=f"benign_m{i}",
                device_id=f"benign_d{i}",
                ip_address=f"benign_ip{i}",
                amount=round(random.uniform(10, 200), 2),
                is_fraud=False,
            ))

    def build_graph(self, transactions: List[Transaction] = None) -> FraudGraph:
        g = FraudGraph()
        for tx in (transactions if transactions is not None else self.transactions):
            g.add_transaction(tx)
        return g

    @property
    def fraud_user_sets(self) -> List[Set[str]]:
        return [set(r.users) for r in self.ground_truth]


def evaluate_detection(
    detected_rings: List[Set[str]],
    ground_truth_rings: List[Set[str]],
    iou_threshold: float = 0.5,
) -> Dict[str, float]:
    """
    Computes precision, recall, F1 for ring detection.

    Both detected_rings and ground_truth_rings should contain User-node sets.
    A detected ring is a TP if its Jaccard overlap with any ground-truth ring
    exceeds iou_threshold.
    """
    tp = 0
    matched_gt: Set[int] = set()

    for det_users in detected_rings:
        for gt_idx, gt_users in enumerate(ground_truth_rings):
            if gt_idx in matched_gt:
                continue
            intersection = det_users & gt_users
            union = det_users | gt_users
            if union and len(intersection) / len(union) >= iou_threshold:
                tp += 1
                matched_gt.add(gt_idx)
                break

    fp = len(detected_rings) - tp
    fn = len(ground_truth_rings) - tp

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall    = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1        = (2 * precision * recall / (precision + recall)
                 if (precision + recall) > 0 else 0.0)

    return {"precision": precision, "recall": recall, "f1": f1,
            "tp": tp, "fp": fp, "fn": fn,
            "n_detected": len(detected_rings),
            "n_ground_truth": len(ground_truth_rings)}

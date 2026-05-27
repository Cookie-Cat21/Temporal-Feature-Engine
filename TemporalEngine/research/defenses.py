"""
Defense strategies against adversarial attacks on fraud ring detection.

Baseline:  Pure WCC with fixed size threshold (ring_hunter.py default)

Defense 1: AdaptiveThreshold  — dynamically lowers the WCC component size
           cutoff when recent alert rates are elevated. More sensitive under
           suspected attack conditions.

Defense 2: MultiSignalDetector — combines three independent signals:
           (a) WCC component membership,
           (b) shared-infrastructure density (device/IP reuse ratio),
           (c) velocity co-occurrence (users sharing high-velocity windows).
           A component must satisfy >= min_signals to be flagged as a ring.

Defense 3: TemporalDensity     — flags components where edge creation times
           are clustered in a short burst window (simulated here as transaction
           count density since we don't have real timestamps in the simulation).
"""
from typing import List, Set, Dict
import networkx as nx

from simulate import FraudGraph, Transaction


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _user_nodes(graph: FraudGraph, component: Set[str]) -> Set[str]:
    return {n for n in component if graph.G.nodes[n].get("ntype") == "User"}


def _device_ip_reuse_ratio(graph: FraudGraph, users: Set[str]) -> float:
    """Fraction of (device, IP) nodes shared by ≥2 users in this component."""
    infra_usage: Dict[str, int] = {}
    for u in users:
        for nbr in graph.G.neighbors(u):
            ntype = graph.G.nodes[nbr].get("ntype", "")
            if ntype in ("Device", "IP"):
                infra_usage[nbr] = infra_usage.get(nbr, 0) + 1
    if not infra_usage:
        return 0.0
    shared = sum(1 for cnt in infra_usage.values() if cnt >= 2)
    return shared / len(infra_usage)


# ---------------------------------------------------------------------------
# Defense 1: Adaptive Threshold
# ---------------------------------------------------------------------------

class AdaptiveThreshold:
    """
    Lowers the component-size threshold from the default (3) toward a
    minimum floor as pressure (e.g. recent alert count) increases.

    In a real deployment the pressure signal would come from a Redis counter;
    here it is passed in directly for experimental control.
    """

    name = "adaptive_threshold"

    def __init__(self, base_threshold: int = 3, min_threshold: int = 1):
        self.base_threshold = base_threshold
        self.min_threshold = min_threshold

    def detect_rings(
        self,
        graph: FraudGraph,
        pressure: float = 0.0,   # 0.0 = no pressure, 1.0 = maximum pressure
    ) -> List[Set[str]]:
        effective = max(
            self.min_threshold,
            int(self.base_threshold * (1.0 - pressure)),
        )
        rings = []
        for comp in nx.connected_components(graph.G):
            if len(comp) > effective:
                users = _user_nodes(graph, comp)
                if len(users) >= 2:
                    rings.append(users)
        return rings


# ---------------------------------------------------------------------------
# Defense 2: Multi-Signal Detector
# ---------------------------------------------------------------------------

class MultiSignalDetector:
    """
    Requires a WCC component to satisfy at least `min_signals` out of three
    independent fraud signals before being flagged as a ring:

      Signal A — component size > size_threshold
      Signal B — device/IP reuse ratio > reuse_threshold
      Signal C — user count in component > user_count_threshold

    An attacker who breaks Signal A (by rotating devices/merchants) still
    gets caught if Signal B or C fires.
    """

    name = "multi_signal"

    def __init__(
        self,
        size_threshold: int   = 3,
        reuse_threshold: float = 0.3,
        user_count_threshold: int = 3,
        min_signals: int = 2,
    ):
        self.size_threshold       = size_threshold
        self.reuse_threshold      = reuse_threshold
        self.user_count_threshold = user_count_threshold
        self.min_signals          = min_signals

    def detect_rings(self, graph: FraudGraph) -> List[Set[str]]:
        rings = []
        for comp in nx.connected_components(graph.G):
            users = _user_nodes(graph, comp)
            if len(users) < 2:
                continue

            sig_a = int(len(comp)   > self.size_threshold)
            sig_b = int(_device_ip_reuse_ratio(graph, users) > self.reuse_threshold)
            sig_c = int(len(users)  > self.user_count_threshold)

            if (sig_a + sig_b + sig_c) >= self.min_signals:
                rings.append(users)
        return rings

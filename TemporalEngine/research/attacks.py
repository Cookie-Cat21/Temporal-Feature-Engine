"""
Adversarial attack strategies against WCC-based fraud ring detection.

The ring_hunter.py WCC algorithm connects users through three types of shared
infrastructure: Devices, IPs, and Merchants. The attacks below progressively
sever these connections.

Strategies
----------
1. DeviceIPRotation   — replace shared devices/IPs with unique ones per user;
                        merchant connections remain, so rings may still be detected
                        via shared merchants. Tests: "Are device/IP signals sufficient?"

2. MerchantRotation   — give each ring user a unique merchant; device/IP sharing
                        remains. Tests: "Are merchant signals sufficient?"

3. FullEvasion        — rotate devices, IPs, and merchants. All WCC paths broken.
                        Tests: the maximum adversarial capability.

Budget semantics
----------------
Budget = number of ring users to attack (out of users_per_ring total).
A budget of 0 = no attack; budget >= users_per_ring = all users attacked.
"""
import copy
import random
from typing import List

from simulate import Scenario, Transaction


class DeviceIPRotation:
    """
    Replaces each targeted ring user's shared device and IP with unique ones.
    Merchant connections survive — rings remain connected via shared merchants.

    Expected result: partial recall loss only when budget >= users_per_ring
    and rings lack shared merchants.
    """

    name = "device_ip_rotation"

    def apply(
        self,
        scenario: Scenario,
        transactions: List[Transaction],
        budget: int,
    ) -> List[Transaction]:
        txs = copy.deepcopy(transactions)
        targets = _sample_fraud_users(scenario, budget)

        counter = 0
        for tx in txs:
            if tx.user_id in targets:
                tx.device_id  = f"rot_dev_{counter}"
                tx.ip_address = f"rot_ip_{counter}"
                counter += 1
        return txs


class MerchantRotation:
    """
    Gives each targeted ring user a unique merchant, severing merchant-level
    WCC connections. Device/IP sharing remains intact.

    Expected result: stronger recall loss than DeviceIPRotation because
    merchant edges are the densest inter-user bridge in practice.
    """

    name = "merchant_rotation"

    def apply(
        self,
        scenario: Scenario,
        transactions: List[Transaction],
        budget: int,
    ) -> List[Transaction]:
        txs = copy.deepcopy(transactions)
        targets = _sample_fraud_users(scenario, budget)

        counter = 0
        for tx in txs:
            if tx.user_id in targets:
                tx.merchant_id = f"rot_merch_{counter}"
                counter += 1
        return txs


class FullEvasion:
    """
    Rotates devices, IPs, and merchants for targeted users, severing all
    WCC inter-user paths. This is the maximum adversarial capability.

    Expected result: near-zero recall once budget reaches users_per_ring.
    """

    name = "full_evasion"

    def apply(
        self,
        scenario: Scenario,
        transactions: List[Transaction],
        budget: int,
    ) -> List[Transaction]:
        txs = copy.deepcopy(transactions)
        targets = _sample_fraud_users(scenario, budget)

        counter = 0
        for tx in txs:
            if tx.user_id in targets:
                tx.device_id   = f"eva_dev_{counter}"
                tx.ip_address  = f"eva_ip_{counter}"
                tx.merchant_id = f"eva_merch_{counter}"
                counter += 1
        return txs


def _sample_fraud_users(scenario: Scenario, budget: int) -> set:
    """
    Uniformly sample `budget` fraud users across all rings (at most
    users_per_ring from each ring, spread evenly when budget is small).
    """
    all_fraud_users = [u for ring in scenario.ground_truth for u in ring.users]
    random.shuffle(all_fraud_users)
    return set(all_fraud_users[:budget])


class VelocityThrottle:
    """
    Targets the Flink VelocityDetector (COUNT_THRESHOLD=5, SUM_THRESHOLD=$1000).

    Splits each fraud user's transaction into `split_factor` micro-transactions
    spaced across distinct 5-minute windows so neither the count nor the sum
    threshold is breached per window. This defeats velocity-based alerts but
    does NOT change the graph topology — WCC detection is unaffected.

    In the simulation we simply reduce per-transaction amount so the 5-min
    window sum stays below SUM_THRESHOLD / split_factor.

    Budget = number of fraud users whose transactions are throttled.
    """

    name = "velocity_throttle"

    WINDOW_SUM_THRESHOLD = 1000.0  # mirrors processor.py
    WINDOW_COUNT_THRESHOLD = 5

    def apply(
        self,
        scenario: Scenario,
        transactions: List[Transaction],
        budget: int,
    ) -> List[Transaction]:
        txs = copy.deepcopy(transactions)
        targets = _sample_fraud_users(scenario, budget)

        for tx in txs:
            if tx.user_id in targets:
                # Cap amount so a 5-min window sum stays safely under threshold
                tx.amount = round(
                    min(tx.amount, self.WINDOW_SUM_THRESHOLD / (self.WINDOW_COUNT_THRESHOLD + 1)),
                    2,
                )
        return txs


class CombinedEvasion:
    """
    Combines FullEvasion (graph fragmentation) + VelocityThrottle (pipeline evasion).
    Defeats both the WCC ring detector and the Flink velocity alerter simultaneously.
    Represents maximum adversarial capability.
    """

    name = "combined_evasion"

    def apply(
        self,
        scenario: Scenario,
        transactions: List[Transaction],
        budget: int,
    ) -> List[Transaction]:
        txs = FullEvasion().apply(scenario, transactions, budget)
        txs = VelocityThrottle().apply(scenario, txs, budget)
        return txs


ALL_ATTACKS = [
    DeviceIPRotation(),
    MerchantRotation(),
    FullEvasion(),
    VelocityThrottle(),
    CombinedEvasion(),
]

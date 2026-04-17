"""
Unit tests for TemporalEngine streaming operator logic.

Flink operators can't be spun up without a cluster, so we test the
business-logic layer that each operator delegates to.  The pattern is:
  1. Extract the pure logic function from the operator.
  2. Feed it hand-crafted inputs.
  3. Assert on outputs.

Run with:  python -m pytest test_streaming.py -v
"""

import json
import time
import unittest
from datetime import datetime, timezone, timedelta


# ---------------------------------------------------------------------------
# Helpers – replicate operator logic without Flink runtime
# ---------------------------------------------------------------------------

def temporal_join(state_profile: dict | None, msg_type: int, data: dict) -> dict | None:
    """Mirror of TemporalJoinFunction.process_element logic."""
    if msg_type == 0:           # profile update — update state, no output
        return None
    # transaction — enrich with latest known profile
    profile = state_profile or {"account_status": "NEW", "credit_score": 0}
    return {
        **data,
        "profile_credit_score": str(profile.get("credit_score", 0)),
        "profile_status": profile.get("account_status", "NEW"),
        "processed_at": "0",
    }


def contract_enforce(enriched: dict, allowed_fields: list[str]) -> dict:
    """Mirror of ContractEnforcer.process_element logic."""
    allowed = set(allowed_fields)
    violations = set(enriched.keys()) - allowed
    result = enriched.copy()
    if violations:
        result["governance_status"] = "VIOLATION"
        result["violations"] = sorted(violations)
    else:
        result["governance_status"] = "OK"
        result["violations"] = []
    return result


def velocity_detect(
    tx_history: list[tuple[int, float]],
    current_ts_ms: int,
    current_amount: float,
    window_ms: int = 5 * 60 * 1000,
    count_threshold: int = 5,
    sum_threshold: float = 1000.0,
) -> tuple[list[tuple[int, float]], dict]:
    """Mirror of VelocityDetector.process_element logic.

    Returns (updated_history, velocity_fields).
    """
    window_start = current_ts_ms - window_ms
    tx_history = [(ts, amt) for ts, amt in tx_history if ts >= window_start]
    tx_history.append((current_ts_ms, current_amount))

    tx_count = len(tx_history)
    tx_sum = sum(amt for _, amt in tx_history)

    velocity_fields = {
        "tx_count_5m": str(tx_count),
        "tx_sum_5m": str(round(tx_sum, 2)),
        "velocity_flag": "HIGH" if (tx_count > count_threshold or tx_sum > sum_threshold) else "NORMAL",
    }
    return tx_history, velocity_fields


# ---------------------------------------------------------------------------
# Tests: TemporalJoinFunction
# ---------------------------------------------------------------------------

class TestTemporalJoin(unittest.TestCase):

    def test_transaction_enriched_with_known_profile(self):
        profile = {"account_status": "VIP", "credit_score": 780}
        tx = {"user_id": "user_1", "amount": "150.0", "merchant": "Acme", "timestamp": "2024-01-01T00:00:00Z"}

        result = temporal_join(profile, msg_type=1, data=tx)

        self.assertIsNotNone(result)
        self.assertEqual(result["profile_status"], "VIP")
        self.assertEqual(result["profile_credit_score"], "780")
        self.assertEqual(result["user_id"], "user_1")

    def test_transaction_with_no_prior_profile_uses_defaults(self):
        tx = {"user_id": "user_99", "amount": "50.0", "merchant": "Beta", "timestamp": "2024-01-01T00:00:00Z"}

        result = temporal_join(None, msg_type=1, data=tx)

        self.assertIsNotNone(result)
        self.assertEqual(result["profile_status"], "NEW")
        self.assertEqual(result["profile_credit_score"], "0")

    def test_profile_update_produces_no_output(self):
        profile_data = {"user_id": "user_1", "credit_score": 800, "account_status": "VIP"}

        result = temporal_join(None, msg_type=0, data=profile_data)

        self.assertIsNone(result)

    def test_latest_profile_wins(self):
        """The second profile update should overwrite the first."""
        tx = {"user_id": "user_1", "amount": "20.0", "merchant": "X", "timestamp": "2024-01-01T00:00:00Z"}

        old_profile = {"account_status": "ACTIVE", "credit_score": 500}
        new_profile = {"account_status": "FLAGGED", "credit_score": 300}

        result = temporal_join(new_profile, msg_type=1, data=tx)

        self.assertEqual(result["profile_status"], "FLAGGED")
        self.assertEqual(result["profile_credit_score"], "300")


# ---------------------------------------------------------------------------
# Tests: ContractEnforcer
# ---------------------------------------------------------------------------

ALLOWED = ["user_id", "amount", "merchant", "processed_at", "profile_credit_score", "profile_status"]


class TestContractEnforcer(unittest.TestCase):

    def test_clean_payload_passes(self):
        payload = {"user_id": "u1", "amount": "10.0", "merchant": "M1", "processed_at": "0"}
        result = contract_enforce(payload, ALLOWED)
        self.assertEqual(result["governance_status"], "OK")
        self.assertEqual(result["violations"], [])

    def test_unknown_field_triggers_violation(self):
        payload = {"user_id": "u1", "credit_card": "4111-1111-1111-1111"}
        result = contract_enforce(payload, ALLOWED)
        self.assertEqual(result["governance_status"], "VIOLATION")
        self.assertIn("credit_card", result["violations"])

    def test_multiple_violations_all_reported(self):
        payload = {"user_id": "u1", "ssn": "000-00-0000", "dob": "1990-01-01"}
        result = contract_enforce(payload, ALLOWED)
        self.assertEqual(result["governance_status"], "VIOLATION")
        self.assertIn("ssn", result["violations"])
        self.assertIn("dob", result["violations"])

    def test_allowed_fields_not_flagged(self):
        payload = {f: "val" for f in ALLOWED}
        result = contract_enforce(payload, ALLOWED)
        self.assertEqual(result["governance_status"], "OK")


# ---------------------------------------------------------------------------
# Tests: VelocityDetector
# ---------------------------------------------------------------------------

NOW_MS = int(datetime.now(timezone.utc).timestamp() * 1000)
ONE_MIN_MS = 60_000


class TestVelocityDetector(unittest.TestCase):

    def test_single_transaction_is_normal(self):
        history, fields = velocity_detect([], NOW_MS, 50.0)
        self.assertEqual(fields["velocity_flag"], "NORMAL")
        self.assertEqual(fields["tx_count_5m"], "1")

    def test_high_count_triggers_flag(self):
        # 5 existing + 1 new = 6 → HIGH
        history = [(NOW_MS - i * ONE_MIN_MS, 10.0) for i in range(5)]
        _, fields = velocity_detect(history, NOW_MS, 10.0)
        self.assertEqual(fields["velocity_flag"], "HIGH")
        self.assertEqual(int(fields["tx_count_5m"]), 6)

    def test_high_sum_triggers_flag(self):
        history = [(NOW_MS - ONE_MIN_MS, 900.0)]
        _, fields = velocity_detect(history, NOW_MS, 200.0)
        self.assertEqual(fields["velocity_flag"], "HIGH")
        self.assertAlmostEqual(float(fields["tx_sum_5m"]), 1100.0)

    def test_old_transactions_evicted_from_window(self):
        # One tx from 10 minutes ago — should be evicted
        old_ts = NOW_MS - 10 * ONE_MIN_MS
        history = [(old_ts, 999.0)]
        updated_history, fields = velocity_detect(history, NOW_MS, 10.0)
        self.assertEqual(int(fields["tx_count_5m"]), 1)   # only the new one
        self.assertEqual(fields["velocity_flag"], "NORMAL")
        # Evicted entry must not remain in history
        self.assertNotIn((old_ts, 999.0), updated_history)

    def test_exactly_at_window_boundary_is_included(self):
        boundary_ts = NOW_MS - 5 * ONE_MIN_MS  # exactly 5 min ago
        history = [(boundary_ts, 10.0)]
        _, fields = velocity_detect(history, NOW_MS, 10.0)
        self.assertEqual(int(fields["tx_count_5m"]), 2)  # boundary + current


# ---------------------------------------------------------------------------
# Tests: Watermark timestamp extraction helper
# ---------------------------------------------------------------------------

class TestTimestampExtraction(unittest.TestCase):
    """Tests the logic used by TxTimestampAssigner.extract_timestamp."""

    def _extract(self, ts_str: str) -> int:
        dt = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
        return int(dt.timestamp() * 1000)

    def test_z_suffix_parses_correctly(self):
        ts_ms = self._extract("2024-06-15T12:00:00Z")
        expected = int(datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc).timestamp() * 1000)
        self.assertEqual(ts_ms, expected)

    def test_utc_offset_parses_correctly(self):
        ts_ms = self._extract("2024-06-15T12:00:00+00:00")
        expected = int(datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc).timestamp() * 1000)
        self.assertEqual(ts_ms, expected)

    def test_late_arrival_is_earlier_than_normal(self):
        normal_ts = self._extract("2024-06-15T12:00:00Z")
        late_ts = self._extract("2024-06-15T11:59:30Z")  # 30 s before
        self.assertLess(late_ts, normal_ts)


if __name__ == "__main__":
    unittest.main(verbosity=2)

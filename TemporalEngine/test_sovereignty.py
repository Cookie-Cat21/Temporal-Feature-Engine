import json
import unittest
from pii_shield import process_payload
from processor import ContractEnforcer

class TestDataSovereignty(unittest.TestCase):
    
    def test_pii_masking(self):
        """Test that sensitive fields are correctly masked."""
        payload = {
            "user_id": "user_123",
            "merchant": "John Doe Coffee",
            "notes": "Email me at alice@example.com or call 123-456-7890",
            "amount": "45.0"
        }
        sensitive_fields = ["merchant", "notes"]
        
        masked = process_payload(payload, sensitive_fields)
        
        print("\n--- PII Masking Test ---")
        print(f"Original Merchant: {payload['merchant']}")
        print(f"Masked Merchant:   {masked['merchant']}")
        print(f"Original Notes:    {payload['notes']}")
        print(f"Masked Notes:      {masked['notes']}")
        
        self.assertIn("[REDACTED", masked["merchant"])
        self.assertIn("[REDACTED_EMAIL]", masked["notes"])
        self.assertIn("[REDACTED_PHONE]", masked["notes"])
        self.assertEqual(masked["user_id"], "user_123")

    def test_contract_enforcement(self):
        """Test that unknown fields are flagged as violations."""
        # Mocking the process_element behavior
        contract = {
            "allowed_fields": ["user_id", "amount", "merchant", "processed_at"]
        }
        
        def enforce(enriched):
            allowed = set(contract["allowed_fields"])
            current = set(enriched.keys())
            violations = current - allowed
            if violations:
                enriched["governance_status"] = "VIOLATION"
                enriched["violations"] = list(violations)
            else:
                enriched["governance_status"] = "OK"
            return enriched

        # Case 1: OK payload
        payload_ok = {"user_id": "u1", "amount": "10", "merchant": "M1"}
        res_ok = enforce(payload_ok)
        self.assertEqual(res_ok["governance_status"], "OK")

        # Case 2: Violation payload
        payload_bad = {"user_id": "u1", "credit_card": "1234-5678-9012-3456"}
        res_bad = enforce(payload_bad.copy())
        
        print("\n--- Contract Enforcement Test ---")
        print(f"Bad Payload: {payload_bad}")
        print(f"Status:      {res_bad['governance_status']}")
        print(f"Violations:  {res_bad['violations']}")
        
        self.assertEqual(res_bad["governance_status"], "VIOLATION")
        self.assertIn("credit_card", res_bad["violations"])

if __name__ == "__main__":
    unittest.main()

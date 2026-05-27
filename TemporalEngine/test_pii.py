import unittest
from pii_shield import process_payload

class TestPIIShield(unittest.TestCase):
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

if __name__ == "__main__":
    unittest.main()

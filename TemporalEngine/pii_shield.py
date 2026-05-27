import json
from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

class PIIShield:
    """A wrapper for Presidio Analyzer and Anonymizer engines."""

    def __init__(self):
        # Lazy loading to avoid serialization issues during Flink task deployment
        self.analyzer = None
        self.anonymizer = None

    def _ensure_loaded(self):
        if self.analyzer is None:
            self.analyzer = AnalyzerEngine()
        if self.anonymizer is None:
            self.anonymizer = AnonymizerEngine()

    def mask_pii(self, text: str) -> str:
        """Finds and masks PII in the given text."""
        if not text or not isinstance(text, str):
            return text

        self._ensure_loaded()

        # Analyze the text for PII
        results = self.analyzer.analyze(text=text, language='en')

        # Anonymize the text (masking PII)
        anonymized_result = self.anonymizer.anonymize(
            text=text,
            analyzer_results=results,
            operators={
                "DEFAULT": OperatorConfig("replace", {"new_value": "[REDACTED]"}),
                "PERSON": OperatorConfig("replace", {"new_value": "[REDACTED_NAME]"}),
                "EMAIL_ADDRESS": OperatorConfig("replace", {"new_value": "[REDACTED_EMAIL]"}),
                "PHONE_NUMBER": OperatorConfig("replace", {"new_value": "[REDACTED_PHONE]"})
            }
        )

        return anonymized_result.text

_default_shield: PIIShield | None = None


def get_shield() -> PIIShield:
    """Return the module-level singleton, creating it on first call."""
    global _default_shield
    if _default_shield is None:
        _default_shield = PIIShield()
        _default_shield._ensure_loaded()
    return _default_shield


def process_payload(payload: dict, sensitive_fields: list, shield: PIIShield | None = None) -> dict:
    """Scans and masks sensitive fields in a dictionary.

    Pass a pre-initialized ``shield`` to avoid repeated engine construction
    (e.g. from a Flink operator's ``open()`` method).
    """
    active_shield = shield if shield is not None else get_shield()
    masked_payload = payload.copy()

    for field in sensitive_fields:
        if field in masked_payload:
            masked_payload[field] = active_shield.mask_pii(masked_payload[field])

    return masked_payload

if __name__ == "__main__":
    # Test
    test_data = {
        "merchant": "John Doe Coffee Shop",
        "notes": "Contact me at john.doe@example.com or call 555-0199"
    }
    sensitive = ["merchant", "notes"]
    print("Original:", test_data)
    print("Masked:  ", process_payload(test_data, sensitive))

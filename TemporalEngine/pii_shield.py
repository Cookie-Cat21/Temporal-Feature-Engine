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

def process_payload(payload: dict, sensitive_fields: list) -> dict:
    """Scans and masks sensitive fields in a dictionary."""
    shield = PIIShield()
    masked_payload = payload.copy()
    
    for field in sensitive_fields:
        if field in masked_payload:
            original_value = masked_payload[field]
            masked_payload[field] = shield.mask_pii(original_value)
            
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

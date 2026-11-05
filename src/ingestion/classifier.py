"""Document relevance classifier and scope guard.
Implements INGEST-006: Document Relevance Classification & Scope Guard.
"""

import re

from src.config import PropertySettings
from src.domain.models import DocumentCategory, DocumentClassification

# Specific keywords indicating Compliance Certificates
COMPLIANCE_PATTERNS = [
    re.compile(r"gas\s+safety\s+record", re.IGNORECASE),
    re.compile(r"gas\s+safety\s+certificate", re.IGNORECASE),
    re.compile(r"landlord\s+gas\s+safety", re.IGNORECASE),
    re.compile(r"energy\s+performance\s+certificate", re.IGNORECASE),
    re.compile(r"\bepc\b", re.IGNORECASE),
    re.compile(r"electrical\s+installation\s+condition\s+report", re.IGNORECASE),
    re.compile(r"\beicr\b", re.IGNORECASE),
    re.compile(r"legionella\s+risk\s+assessment", re.IGNORECASE),
    re.compile(r"smoke\s+(?:and|&)\s+carbon\s+monoxide", re.IGNORECASE),
]

# Keywords indicating Letting Agency Rental Statements
STATEMENT_PATTERNS = [
    re.compile(r"landlord\s+statement", re.IGNORECASE),
    re.compile(r"rent\s+statement", re.IGNORECASE),
    re.compile(r"rent\s+from", re.IGNORECASE),
    re.compile(r"net\s+to\s+landlord", re.IGNORECASE),
    re.compile(r"landlord\s+payment", re.IGNORECASE),
    re.compile(r"statement\s+number", re.IGNORECASE),
]

# Keywords indicating Contractor Invoices
INVOICE_PATTERNS = [
    re.compile(r"tax\s+invoice", re.IGNORECASE),
    re.compile(r"\binvoice\b", re.IGNORECASE),
    re.compile(r"bill\s+to", re.IGNORECASE),
    re.compile(r"invoice\s+(?:no|number|#)", re.IGNORECASE),
    re.compile(r"job\s+(?:no|number|description)", re.IGNORECASE),
    re.compile(r"total\s+due", re.IGNORECASE),
]

# Standard UK Postcode regex pattern
UK_POSTCODE_REGEX = re.compile(
    r"\b([A-Z]{1,2}\d[A-Z\d]?)\s*(\d[A-Z]{2})\b",
    re.IGNORECASE,
)


# [spec: INGEST-006]
def detect_postcode_in_text(text: str) -> str | None:
    """Extract first detected UK postcode from text normalized to uppercase without spaces."""
    match = UK_POSTCODE_REGEX.search(text)
    if match:
        outward = match.group(1).upper()
        inward = match.group(2).upper()
        return f"{outward} {inward}"
    return None


# [spec: INGEST-006]
def check_property_match(
    text: str,
    property_config: PropertySettings | None = None,
) -> tuple[bool, str | None, str | None]:
    """Verify whether the document matches configured property postcode or reference.

    Returns:
        (property_match, detected_postcode, detected_reference)
    """
    if property_config is None:
        return True, None, None

    detected_postcode = detect_postcode_in_text(text)
    detected_ref: str | None = None

    if property_config.reference and property_config.reference.lower() in text.lower():
        detected_ref = property_config.reference

    # If document has a detected postcode and config defines a postcode prefix or full code:
    if detected_postcode and property_config.postcode:
        norm_detected = detected_postcode.replace(" ", "").upper()
        norm_expected = property_config.postcode.replace(" ", "").upper()
        # Mismatch if detected postcode doesn't share prefix or match
        if not norm_detected.startswith(norm_expected) and not norm_expected.startswith(norm_detected):
            return False, detected_postcode, detected_ref

    return True, detected_postcode, detected_ref


# [spec: INGEST-006]
def classify_document(
    raw_text: str,
    property_config: PropertySettings | None = None,
) -> DocumentClassification:
    """Classify document category and verify property scope using lean heuristics.

    Follows INGEST-006:
    - AC-INGEST-006.1: Classifies into RENTAL_STATEMENT, CONTRACTOR_INVOICE,
      COMPLIANCE_CERTIFICATE, or UNRECOGNIZED_DOCUMENT.
    - AC-INGEST-006.2: Flags UNRECOGNIZED_DOCUMENT if no distinct rental/invoice/compliance patterns match.
    - AC-INGEST-006.3: Checks property scope against configured postcode/reference.
    - AC-INGEST-006.4: Categorizes compliance certificates for dedicated routing.
    """
    property_match, detected_pc, detected_ref = check_property_match(raw_text, property_config)

    # 1. Check for compliance certificates
    for pat in COMPLIANCE_PATTERNS:
        if pat.search(raw_text):
            return DocumentClassification(
                category=DocumentCategory.COMPLIANCE_CERTIFICATE,
                confidence=0.95,
                reason=f"Matched compliance pattern: '{pat.pattern}'",
                property_match=property_match,
                detected_reference=detected_ref,
                detected_postcode=detected_pc,
            )

    # 2. Check for rental statements
    statement_matches = sum(1 for pat in STATEMENT_PATTERNS if pat.search(raw_text))
    if statement_matches >= 1 and ("statement" in raw_text.lower() or "rent" in raw_text.lower()):
        return DocumentClassification(
            category=DocumentCategory.RENTAL_STATEMENT,
            confidence=0.9,
            reason=f"Matched {statement_matches} rental statement keyword pattern(s)",
            property_match=property_match,
            detected_reference=detected_ref,
            detected_postcode=detected_pc,
        )

    # 3. Check for contractor invoices
    invoice_matches = sum(1 for pat in INVOICE_PATTERNS if pat.search(raw_text))
    if invoice_matches >= 1 and ("invoice" in raw_text.lower() or "bill to" in raw_text.lower()):
        return DocumentClassification(
            category=DocumentCategory.CONTRACTOR_INVOICE,
            confidence=0.85,
            reason=f"Matched {invoice_matches} contractor invoice keyword pattern(s)",
            property_match=property_match,
            detected_reference=detected_ref,
            detected_postcode=detected_pc,
        )

    # 4. Unrecognized document
    return DocumentClassification(
        category=DocumentCategory.UNRECOGNIZED_DOCUMENT,
        confidence=0.0,
        reason="No rental statement, invoice, or compliance markers detected in document text",
        property_match=property_match,
        detected_reference=detected_ref,
        detected_postcode=detected_pc,
    )

"""Tests for INGEST-006 (Classification & Scope Guard) and INGEST-007 (Degradation Resilience)."""

from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.config import AppConfig, MortgageSettings, OllamaSettings, PropertySettings
from src.domain.models import DocumentCategory, ExpenditureLine, RentalStatement
from src.ingestion.batch import BatchIngestionService
from src.ingestion.classifier import (
    classify_document,
)
from src.ingestion.pdf_reader import (
    EncryptedPdfError,
    ScannedImagePdfError,
    extract_text_from_pdf,
)
from src.ingestion.reconciler import reconcile_statement
from src.storage.database import Database


@pytest.fixture
def test_config():
    return AppConfig(
        ollama=OllamaSettings(base_url="http://localhost:11434", model="llama3.2:3b"),
        mortgage=MortgageSettings(
            monthly_direct_debit=Decimal("1997.00"),
            interest_rate=Decimal("4.30"),
            fixed_deal_end_date="30-11-2027",
            effective_from="01-11-2025",
            initial_principal=Decimal("68735.81"),
        ),
        property=PropertySettings(
            postcode="AL7 4SS",
            reference="WGL230032",
        ),
    )


# [verifies: INGEST-006/AC-INGEST-006.1]
def test_document_classification_into_all_four_categories():
    """Verify classification into RENTAL_STATEMENT, CONTRACTOR_INVOICE, COMPLIANCE_CERTIFICATE, and UNRECOGNIZED_DOCUMENT."""
    statement_text = "Landlord Statement for property WGL230032. Rent from tenant: £1,750. Net to landlord: £1,500."
    c1 = classify_document(statement_text)
    assert c1.category == DocumentCategory.RENTAL_STATEMENT

    invoice_text = "Tax Invoice #1024 Bill To: Landlord Services. Total Due: £340.00. Job description: boiler fix."
    c2 = classify_document(invoice_text)
    assert c2.category == DocumentCategory.CONTRACTOR_INVOICE

    compliance_text = "Landlord Gas Safety Record CP12 inspection certificate. Pass."
    c3 = classify_document(compliance_text)
    assert c3.category == DocumentCategory.COMPLIANCE_CERTIFICATE

    random_text = "Coffee machine operating instructions and warranty manual. Press button to brew espresso."
    c4 = classify_document(random_text)
    assert c4.category == DocumentCategory.UNRECOGNIZED_DOCUMENT


# [verifies: INGEST-006/AC-INGEST-006.2]
def test_unrecognized_document_rejection(tmp_path: Path, test_config):
    """Verify that an unrecognized document is rejected without database insertion."""
    db = Database(db_path=tmp_path / "test.db")
    service = BatchIngestionService(db=db, config=test_config)

    dummy_pdf = tmp_path / "brochure.pdf"
    dummy_pdf.write_bytes(b"%PDF-1.4 brochure text")

    with patch("src.ingestion.batch.extract_text_from_pdf", return_value="Welcome to the building user guide"):
        result = service.process_file(dummy_pdf)
        assert result.status == "rejected"
        assert result.doc_type == "unrecognized"
        assert "UNRECOGNIZED_DOCUMENT" in result.details

        # DB must have zero monthly records and zero invoices
        conn = db._get_connection()
        assert conn.execute("SELECT COUNT(*) FROM monthly_records").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM contractor_invoices").fetchone()[0] == 0


# [verifies: INGEST-006/AC-INGEST-006.3]
def test_property_scope_guard_postcode_mismatch(tmp_path: Path, test_config):
    """Verify that an invoice or statement referencing an external property is flagged and rejected."""
    # Configured property postcode is AL7 4SS
    mismatched_text = "Landlord Statement for Flat 4, 12 High Street, Birmingham, B1 1BB. Rent from tenant: £900. Net to landlord: £800."
    classification = classify_document(mismatched_text, property_config=test_config.property)
    assert classification.property_match is False
    assert classification.detected_postcode == "B1 1BB"

    # Batch service rejection
    db = Database(db_path=tmp_path / "test.db")
    service = BatchIngestionService(db=db, config=test_config)
    pdf_path = tmp_path / "birmingham_rent.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 dummy birmingham")

    with patch("src.ingestion.batch.extract_text_from_pdf", return_value=mismatched_text):
        result = service.process_file(pdf_path)
        assert result.status == "rejected"
        assert result.doc_type == "mismatch"
        assert "PROPERTY_MISMATCH" in result.details

        conn = db._get_connection()
        assert conn.execute("SELECT COUNT(*) FROM monthly_records").fetchone()[0] == 0


# [verifies: INGEST-006/AC-INGEST-006.4]
def test_compliance_certificate_routing_without_financial_ledger(tmp_path: Path, test_config):
    """Verify that compliance certificates are indexed without financial ledger insertion."""
    db = Database(db_path=tmp_path / "test.db")
    service = BatchIngestionService(db=db, config=test_config)
    cert_path = tmp_path / "epc_cert.pdf"
    cert_path.write_bytes(b"%PDF-1.4 EPC inspection certificate")

    epc_text = "Energy Performance Certificate (EPC) for 12 Example Way AL7 4SS. Rating C. Valid until 2030."

    with patch("src.ingestion.batch.extract_text_from_pdf", return_value=epc_text):
        result = service.process_file(cert_path)
        assert result.status == "compliance"
        assert result.doc_type == "compliance"
        assert "COMPLIANCE_CERTIFICATE" in result.details

        # Ensure no financial records entered
        conn = db._get_connection()
        assert conn.execute("SELECT COUNT(*) FROM monthly_records").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM contractor_invoices").fetchone()[0] == 0


# [verifies: INGEST-007/AC-INGEST-007.1]
def test_scanned_image_pdf_character_threshold(tmp_path: Path, test_config):
    """Verify that PDFs yielding fewer than 40 characters are classified as SCANNED_IMAGE_PDF."""
    sparse_pdf = tmp_path / "scanned.pdf"
    sparse_pdf.write_bytes(b"%PDF-1.4 sparse")

    # When pdf_reader extract_text_from_pdf sees < 40 chars, it raises ScannedImagePdfError
    with (
        patch("pypdf.PdfReader") as mock_reader_cls,
        patch("pdfplumber.open") as mock_pdfplumber,
    ):
        mock_reader = MagicMock()
        mock_reader.is_encrypted = False
        mock_reader_cls.return_value = mock_reader

        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Scanned"  # only 7 chars
        mock_plumber_inst = MagicMock()
        mock_plumber_inst.__enter__.return_value.pages = [mock_page]
        mock_pdfplumber.return_value = mock_plumber_inst

        with pytest.raises(ScannedImagePdfError):
            extract_text_from_pdf(sparse_pdf)

    # In batch processing, ScannedImagePdfError is caught gracefully
    db = Database(db_path=tmp_path / "test.db")
    service = BatchIngestionService(db=db, config=test_config)

    with patch(
        "src.ingestion.batch.extract_text_from_pdf",
        side_effect=ScannedImagePdfError("Yielded fewer than 40 characters"),
    ):
        result = service.process_file(sparse_pdf)
        assert result.status == "scanned"
        assert result.doc_type == "scanned"
        assert "SCANNED_IMAGE_PDF" in result.details


# [verifies: INGEST-007/AC-INGEST-007.2]
def test_encrypted_pdf_handling(tmp_path: Path, test_config):
    """Verify that password-protected or encrypted PDFs are skipped without crashing."""
    enc_pdf = tmp_path / "locked.pdf"
    enc_pdf.write_bytes(b"%PDF-1.4 locked")

    with patch("pypdf.PdfReader") as mock_reader_cls:
        mock_reader = MagicMock()
        mock_reader.is_encrypted = True
        mock_reader_cls.return_value = mock_reader

        with pytest.raises(EncryptedPdfError):
            extract_text_from_pdf(enc_pdf)

    # In batch processing, EncryptedPdfError is caught gracefully
    db = Database(db_path=tmp_path / "test.db")
    service = BatchIngestionService(db=db, config=test_config)

    with patch(
        "src.ingestion.batch.extract_text_from_pdf",
        side_effect=EncryptedPdfError("Password-protected"),
    ):
        result = service.process_file(enc_pdf)
        assert result.status == "encrypted"
        assert result.doc_type == "encrypted"
        assert "ENCRYPTED_PDF" in result.details


# [verifies: INGEST-007/AC-INGEST-007.3]
def test_deficit_month_negative_landlord_payout_reconciliation(tmp_path: Path, test_config):
    """Verify that negative net landlord payout (expenses > income) reconciles deterministically and saves."""
    db = Database(db_path=tmp_path / "test.db")

    # Gross rent: £1,200, deductions: £1,500, net payout: -£300.00
    deficit_statement = RentalStatement(
        statement_date="15/09/2026",
        reference="WGL230032",
        statement_number="2026-09",
        gross_income=Decimal("1200.00"),
        expenditures=[
            ExpenditureLine(
                description="Major Boiler Repair",
                net=Decimal("1250.00"),
                vat=Decimal("250.00"),
                gross=Decimal("1500.00"),
            )
        ],
        net_payout=Decimal("-300.00"),
    )

    reconciliation = reconcile_statement(deficit_statement)
    assert reconciliation.is_balanced is True
    assert reconciliation.discrepancy == Decimal("0.00")
    assert reconciliation.status == "BALANCED"

    # Persist to database
    record_id = db.save_monthly_statement(
        statement=deficit_statement,
        mortgage_debit=test_config.mortgage.monthly_direct_debit,
        outstanding_balance=Decimal("65000.00"),
    )
    assert record_id is not None

    # Verify stored values in SQLite
    conn = db._get_connection()
    row = conn.execute(
        "SELECT gross_income, total_expenditure, net_payout FROM monthly_records WHERE id = ?", (record_id,)
    ).fetchone()
    assert Decimal(row["gross_income"]) == Decimal("1200.00")
    assert Decimal(row["total_expenditure"]) == Decimal("1500.00")
    assert Decimal(row["net_payout"]) == Decimal("-300.00")

"""TDD Test Suite for PDF Ingestion, Offline Extraction, Duplicate Detection, and Reconciliation.
Bound to specifications in specs/ingestion/pdf_ingestion.md.
"""

from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from src.config import AppConfig, MortgageSettings, OllamaSettings
from src.domain.models import (
    ContractorInvoice,
    DuplicateType,
    ExpenditureLine,
    RentalStatement,
)
from src.ingestion.duplicate_checker import DuplicateChecker, InMemoryDocumentStore
from src.ingestion.extractor import (
    OllamaExtractor,
    OllamaServiceUnreachableError,
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
    )


# [verifies: INGEST-001/AC-INGEST-001.1]
def test_extract_rental_statement_structure():
    """Verify extraction of statement date, reference, statement number, gross rent, line items, and net payout."""
    extractor = OllamaExtractor(base_url="http://localhost:11434")

    mock_llm_response = {
        "statement_date": "2026-10-16",
        "reference": "WGL230032",
        "statement_number": "13",
        "gross_rent": "1750.00",
        "expenditures": [
            {
                "description": "Invoice from Gas Flow Heating: cistern, toilet seats, riser",
                "net": "84.00",
                "vat": "0.00",
                "gross": "84.00",
            },
            {
                "description": "Letting fees at 10%",
                "net": "175.00",
                "vat": "35.00",
                "gross": "210.00",
            },
        ],
        "net_payout": "1456.00",
    }

    with patch.object(extractor, "_query_ollama", return_value=mock_llm_response):
        statement = extractor.parse_rental_statement("Sample statement raw text")
        assert isinstance(statement, RentalStatement)
        assert statement.statement_date == "2026-10-16"
        assert statement.reference == "WGL230032"
        assert statement.statement_number == "13"
        assert statement.gross_income == Decimal("1750.00")
        assert len(statement.expenditures) == 2
        assert statement.expenditures[0].gross == Decimal("84.00")
        assert statement.expenditures[1].vat == Decimal("35.00")
        assert statement.net_payout == Decimal("1456.00")


# [verifies: INGEST-001/AC-INGEST-001.1]
def test_extract_rental_statement_with_currency_symbols_and_commas():
    """Verify that statement extraction handles currency symbols (£, $), commas, and spaces in numeric values."""
    extractor = OllamaExtractor(base_url="http://localhost:11434")

    mock_llm_response = {
        "statement_date": "16/10/2026",
        "reference": "WGL230032",
        "statement_number": "13",
        "gross_rent": "£1,750.00",
        "expenditures": [
            {"description": "Letting fee", "net": "£70.00", "vat": "£14.00", "gross": "£84.00"},
            {"description": "Repair", "net": "175.00", "vat": "35.00", "gross": " 210.00 "},
        ],
        "net_payout": "£1,456.00",
    }

    with patch.object(extractor, "_query_ollama", return_value=mock_llm_response):
        statement = extractor.parse_rental_statement("Sample statement raw text")
        assert statement.gross_income == Decimal("1750.00")
        assert statement.expenditures[0].gross == Decimal("84.00")
        assert statement.expenditures[1].gross == Decimal("210.00")
        assert statement.net_payout == Decimal("1456.00")


# [verifies: INGEST-001/AC-INGEST-001.1]
def test_ollama_json_recovery_from_markdown_or_string():
    """Verify recovery when Ollama returns JSON enclosed in markdown code blocks or double-encoded strings."""
    raw_markdown = '```json\n{"statement_date": "2026-10-16", "gross_rent": "£1,750.00", "expenditures": [], "net_payout": "£1,750.00"}\n```'
    parsed = OllamaExtractor.parse_json_safely(raw_markdown)
    assert parsed.get("gross_rent") == "£1,750.00"

    double_string = '"{\\"gross_rent\\": \\"1500.00\\"}"'
    parsed_inner = OllamaExtractor.parse_json_safely(double_string)
    assert parsed_inner.get("gross_rent") == "1500.00"


# [verifies: INGEST-001/AC-INGEST-001.2]
def test_extract_contractor_invoice_structure():
    """Verify extraction of contractor name, invoice date, invoice number, line items, gross amount, and description."""
    extractor = OllamaExtractor(base_url="http://localhost:11434")

    mock_llm_response = {
        "contractor_name": "Joe Graham + Son Ltd",
        "invoice_date": "2026-10-15",
        "invoice_number": "INV157537",
        "gross_amount": "138.00",
        "job_description": "Supply and fit extractor cooker hood",
        "line_items": ["Extractor hood unit and installation"],
    }

    with patch.object(extractor, "_query_ollama", return_value=mock_llm_response):
        invoice = extractor.parse_contractor_invoice("Sample invoice text")
        assert isinstance(invoice, ContractorInvoice)
        assert invoice.contractor_name == "Joe Graham + Son Ltd"
        assert invoice.invoice_date == "15/10/2026"
        assert invoice.invoice_number == "INV157537"
        assert invoice.gross_amount == Decimal("138.00")
        assert invoice.job_description == "Supply and fit extractor cooker hood"


# [verifies: INGEST-001/AC-INGEST-001.3]
def test_offline_zero_external_network_requests():
    """Verify extraction pipeline targets local host only and makes no external cloud API requests."""
    extractor = OllamaExtractor(base_url="http://localhost:11434")
    assert extractor.base_url.startswith("http://localhost:") or extractor.base_url.startswith("http://127.0.0.1:")


# [verifies: INGEST-001/AC-INGEST-001.4]
def test_ollama_service_unreachable_helpful_error():
    """Verify that if local Ollama service is unreachable, a helpful error message is returned asking to try again."""
    extractor = OllamaExtractor(base_url="http://localhost:11434")

    with patch("httpx.Client.post", side_effect=httpx.ConnectError("Connection refused")):
        with pytest.raises(OllamaServiceUnreachableError) as exc_info:
            extractor.parse_rental_statement("dummy text")

        assert "Local Ollama service at localhost:11434 is unreachable" in str(exc_info.value)
        assert "Please ensure Ollama is running and try again." in str(exc_info.value)


# [verifies: INGEST-001/AC-INGEST-001.4]
def test_ollama_model_not_found_error():
    """Verify that if the requested Ollama model does not exist (HTTP 404), an informative error is returned."""
    extractor = OllamaExtractor(base_url="http://localhost:11434", model="non-existent-model")

    mock_resp = httpx.Response(
        status_code=404,
        json={"error": "model 'non-existent-model' not found, try pulling it first"},
        request=httpx.Request("POST", "http://localhost:11434/api/generate"),
    )
    with patch("httpx.Client.post", return_value=mock_resp):
        with pytest.raises(OllamaServiceUnreachableError) as exc_info:
            extractor.parse_rental_statement("dummy text")

        assert "Local Ollama model 'non-existent-model' was not found" in str(exc_info.value)
        assert "Please run 'ollama pull non-existent-model'" in str(exc_info.value)


# [verifies: INGEST-002/AC-INGEST-002.1]
def test_duplicate_file_hash_detection(tmp_path: Path):
    """Verify that if file byte SHA-256 matches an already ingested file, it is flagged as duplicate."""
    sample_file = tmp_path / "statement.pdf"
    sample_file.write_bytes(b"%PDF-1.4 sample statement content")

    store = InMemoryDocumentStore()
    checker = DuplicateChecker(store=store)

    # First check: not a duplicate
    result1 = checker.check_file(sample_file)
    assert result1.is_duplicate is False

    # Ingest document
    store.add_file_hash(result1.file_hash, filename="statement.pdf")

    # Second check: exact duplicate detected
    result2 = checker.check_file(sample_file)
    assert result2.is_duplicate is True
    assert result2.duplicate_type == DuplicateType.EXACT_FILE_HASH


# [verifies: INGEST-002/AC-INGEST-002.2]
def test_duplicate_semantic_statement_prompt(tmp_path: Path):
    """Verify that if statement number and reference match an existing record but file hash differs, a confirmation is triggered."""
    store = InMemoryDocumentStore()
    # Existing statement in database
    existing_stmt = RentalStatement(
        statement_date="2026-10-16",
        reference="WGL230032",
        statement_number="13",
        gross_income=Decimal("1750.00"),
        expenditures=[],
        net_payout=Decimal("1750.00"),
        file_hash="hash_aaa111",
    )
    store.add_statement(existing_stmt)

    checker = DuplicateChecker(store=store)

    new_stmt = RentalStatement(
        statement_date="2026-10-16",
        reference="WGL230032",
        statement_number="13",
        gross_income=Decimal("1750.00"),
        expenditures=[],
        net_payout=Decimal("1750.00"),
        file_hash="hash_different_bbb222",
    )

    result = checker.check_statement_semantic(new_stmt)
    assert result.is_duplicate is True
    assert result.duplicate_type == DuplicateType.SEMANTIC_STATEMENT
    assert "Statement #13 (Reference: WGL230032) already exists" in result.message
    assert result.requires_user_confirmation is True


# [verifies: INGEST-002/AC-INGEST-002.4]
def test_overwrite_monthly_statement_replaces_atomically(tmp_path: Path):
    """Verify that when overwrite is requested for an existing month/statement, records and expenditures are replaced atomically."""
    from src.storage.database import Database

    db = Database(db_path=tmp_path / "overwrite_test.db")
    stmt_v1 = RentalStatement(
        statement_date="16/10/2026",
        reference="REF-OCT-26",
        statement_number="101",
        gross_income=Decimal("1750.00"),
        expenditures=[
            ExpenditureLine(description="Old Fee", net=Decimal("100.00"), vat=Decimal("20.00"), gross=Decimal("120.00"))
        ],
        net_payout=Decimal("1630.00"),
        file_hash="hash_v1",
    )
    db.save_monthly_statement(stmt_v1, Decimal("1997.00"), Decimal("68735.81"))

    # Overwrite statement with amended numbers
    stmt_v2 = RentalStatement(
        statement_date="16/10/2026",
        reference="REF-OCT-26",
        statement_number="101",
        gross_income=Decimal("1750.00"),
        expenditures=[
            ExpenditureLine(
                description="Amended Fee", net=Decimal("150.00"), vat=Decimal("30.00"), gross=Decimal("180.00")
            )
        ],
        net_payout=Decimal("1570.00"),
        file_hash="hash_v2",
    )
    rec2 = db.overwrite_monthly_statement(stmt_v2, Decimal("1997.00"), Decimal("68735.81"))

    conn = db._get_connection()
    # Ensure there is still exactly 1 record for this statement in database
    records = conn.execute("SELECT * FROM monthly_records WHERE reference = 'REF-OCT-26'").fetchall()
    assert len(records) == 1
    assert records[0]["net_payout"] == "1570.00"

    # Ensure expenditures were cleanly replaced
    expenditures = conn.execute("SELECT * FROM expenditures WHERE monthly_record_id = ?", (rec2,)).fetchall()
    assert len(expenditures) == 1
    assert expenditures[0]["description"] == "Amended Fee"


# [verifies: INGEST-002/AC-INGEST-002.4]
def test_database_auto_creation_and_pragmas(tmp_path: Path):
    """Verify that if the database file does not exist, Database auto-creates parent folders, tables, indices, and WAL pragmas."""
    target_db = tmp_path / "deeply" / "nested" / "rent_dashboard.db"
    assert not target_db.exists()

    db = Database(db_path=target_db)
    assert target_db.exists()

    conn = db._get_connection()
    journal_mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
    busy_timeout = conn.execute("PRAGMA busy_timeout;").fetchone()[0]
    foreign_keys = conn.execute("PRAGMA foreign_keys;").fetchone()[0]

    assert journal_mode.lower() == "wal"
    assert busy_timeout == 5000
    assert foreign_keys == 1

    # Verify table and index existence
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    assert "monthly_records" in tables
    assert "expenditures" in tables
    assert "contractor_invoices" in tables


# [verifies: INGEST-002/AC-INGEST-002.3]
def test_duplicate_contractor_invoice_detection():
    """Verify contractor invoice duplicate detection by contractor name, invoice number, and amount."""
    store = InMemoryDocumentStore()
    existing_inv = ContractorInvoice(
        contractor_name="Joe Graham + Son Ltd",
        invoice_date="2026-10-15",
        invoice_number="INV157537",
        gross_amount=Decimal("138.00"),
        job_description="Cooker hood",
        file_hash="hash_inv_111",
    )
    store.add_invoice(existing_inv)

    checker = DuplicateChecker(store=store)

    duplicate_inv = ContractorInvoice(
        contractor_name="Joe Graham + Son Ltd",
        invoice_date="2026-10-15",
        invoice_number="INV157537",
        gross_amount=Decimal("138.00"),
        job_description="Different description",
        file_hash="hash_inv_222",
    )

    result = checker.check_invoice_semantic(duplicate_inv)
    assert result.is_duplicate is True
    assert result.duplicate_type == DuplicateType.SEMANTIC_INVOICE


# [verifies: INGEST-003/AC-INGEST-003.1]
def test_financial_reconciliation_three_way_checks():
    """Verify three-way deterministic check:

    1. Income items sum to income subtotal.
    2. Expenditure items sum to expenditure subtotal.
    3. Landlord payment equals income minus expenditure.
    """
    from src.domain.models import IncomeLine

    # 1. Test Income Items check failure
    stmt_bad_income = RentalStatement(
        statement_date="2026-10-16",
        reference="WGL230032",
        statement_number="13",
        gross_income=Decimal("1750.00"),
        income_subtotal=Decimal("1750.00"),
        income_items=[
            IncomeLine(description="Rent line", net=Decimal("1500.00"), gross=Decimal("1500.00")),  # Only 1500 vs 1750!
        ],
        expenditures=[],
        expenditure_subtotal=Decimal("0.00"),
        net_payout=Decimal("1750.00"),
    )
    res_bad_income = reconcile_statement(stmt_bad_income)
    assert res_bad_income.is_balanced is False
    assert res_bad_income.income_check_passed is False
    assert any("Income items sum" in r for r in res_bad_income.failure_reasons)

    # 2. Test Expenditure Items check failure
    stmt_bad_exp = RentalStatement(
        statement_date="2026-10-16",
        reference="WGL230032",
        statement_number="13",
        gross_income=Decimal("1750.00"),
        income_subtotal=Decimal("1750.00"),
        income_items=[
            IncomeLine(description="Rent", net=Decimal("1750.00"), gross=Decimal("1750.00")),
        ],
        expenditures=[
            ExpenditureLine(description="Management Fee", net=Decimal("100.00"), gross=Decimal("120.00")),
        ],
        expenditure_subtotal=Decimal("150.00"),  # Expected 150, but items sum to 120!
        net_payout=Decimal("1600.00"),
    )
    res_bad_exp = reconcile_statement(stmt_bad_exp)
    assert res_bad_exp.is_balanced is False
    assert res_bad_exp.expenditure_check_passed is False
    assert any("Expenditure lines sum" in r for r in res_bad_exp.failure_reasons)

    # 3. Test Landlord Payout check failure
    stmt_bad_payout = RentalStatement(
        statement_date="2026-10-16",
        reference="WGL230032",
        statement_number="13",
        gross_income=Decimal("1750.00"),
        income_subtotal=Decimal("1750.00"),
        income_items=[
            IncomeLine(description="Rent", net=Decimal("1750.00"), gross=Decimal("1750.00")),
        ],
        expenditures=[
            ExpenditureLine(description="Fee", net=Decimal("100.00"), gross=Decimal("120.00")),
        ],
        expenditure_subtotal=Decimal("120.00"),
        net_payout=Decimal("1600.00"),  # 1750 - 120 = 1630! Off by 30
    )
    res_bad_payout = reconcile_statement(stmt_bad_payout)
    assert res_bad_payout.is_balanced is False
    assert res_bad_payout.payout_check_passed is False
    assert any("Landlord payment" in r for r in res_bad_payout.failure_reasons)


# [verifies: INGEST-003/AC-INGEST-003.2]
def test_financial_reconciliation_balanced_success():
    """Verify that if all three checks pass, statement is automatically marked balanced."""
    from src.domain.models import IncomeLine

    statement = RentalStatement(
        statement_date="2026-10-16",
        reference="WGL230032",
        statement_number="13",
        gross_income=Decimal("1750.00"),
        income_subtotal=Decimal("1750.00"),
        income_items=[
            IncomeLine(
                description="Rent payment", net=Decimal("1750.00"), vat=Decimal("0.00"), gross=Decimal("1750.00")
            ),
        ],
        expenditures=[
            ExpenditureLine(
                description="Agency fee", net=Decimal("175.00"), vat=Decimal("35.00"), gross=Decimal("210.00")
            ),
            ExpenditureLine(
                description="Contractor repair", net=Decimal("300.00"), vat=Decimal("0.00"), gross=Decimal("300.00")
            ),
        ],
        expenditure_subtotal=Decimal("510.00"),
        net_payout=Decimal("1240.00"),  # 1750 - 510 = 1240
    )

    reconciliation = reconcile_statement(statement)
    assert reconciliation.is_balanced is True
    assert reconciliation.income_check_passed is True
    assert reconciliation.expenditure_check_passed is True
    assert reconciliation.payout_check_passed is True
    assert reconciliation.discrepancy == Decimal("0.00")
    assert reconciliation.status == "BALANCED"


# [verifies: INGEST-003/AC-INGEST-003.1]
def test_financial_reconciliation_with_net_subtotal_and_vat():
    """Verify reconciliation succeeds when letting statement has VAT on fees and net subtotal column is extracted."""
    from src.domain.models import IncomeLine

    # Example matching user statement: Gross £1,650, Net deductions £1,226.50, VAT £99.30, Gross deductions £1,325.80, payout £324.20
    statement = RentalStatement(
        statement_date="09/12/2025",
        reference="WGL230032",
        statement_number="1",
        gross_income=Decimal("1650.00"),
        income_subtotal=Decimal("1650.00"),
        income_items=[
            IncomeLine(description="Rent", net=Decimal("1650.00"), vat=Decimal("0.00"), gross=Decimal("1650.00")),
        ],
        expenditures=[
            ExpenditureLine(
                description="Aqualisa repair", net=Decimal("646.00"), vat=Decimal("0.00"), gross=Decimal("646.00")
            ),
            ExpenditureLine(
                description="Inventory", net=Decimal("240.00"), vat=Decimal("48.00"), gross=Decimal("288.00")
            ),
            ExpenditureLine(description="Gas Flow", net=Decimal("84.00"), vat=Decimal("0.00"), gross=Decimal("84.00")),
            ExpenditureLine(description="TDS", net=Decimal("9.00"), vat=Decimal("1.80"), gross=Decimal("10.80")),
            ExpenditureLine(
                description="Letting fee", net=Decimal("165.00"), vat=Decimal("33.00"), gross=Decimal("198.00")
            ),
            ExpenditureLine(
                description="Management fee", net=Decimal("82.50"), vat=Decimal("16.50"), gross=Decimal("99.00")
            ),
        ],
        expenditure_subtotal=Decimal("1226.50"),  # Net subtotal column
        net_payout=Decimal("324.20"),  # 1650.00 - 1325.80 (Gross deductions) = 324.20
    )

    reconciliation = reconcile_statement(statement)
    assert reconciliation.is_balanced is True
    assert reconciliation.income_check_passed is True
    assert reconciliation.expenditure_check_passed is True
    assert reconciliation.payout_check_passed is True
    assert reconciliation.discrepancy == Decimal("0.00")


# [verifies: INGEST-003/AC-INGEST-003.3]
def test_rescan_retries_on_initial_reconciliation_failure(tmp_path: Path, test_config):
    """Verify that if a reconciliation check fails initially, the system retries scanning and extraction up to 3 attempts."""
    from unittest.mock import MagicMock

    from src.ingestion.batch import BatchIngestionService

    db = Database(db_path=tmp_path / "rescan_test.db")
    service = BatchIngestionService(db=db, config=test_config)

    pdf_file = tmp_path / "flaky_statement.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 sample statement content")

    stmt_attempt1 = RentalStatement(
        statement_date="16/10/2026",
        reference="REF01",
        statement_number="1",
        gross_income=Decimal("1750.00"),
        expenditures=[],
        net_payout=Decimal("1500.00"),  # Off
    )
    stmt_attempt2 = RentalStatement(
        statement_date="16/10/2026",
        reference="REF01",
        statement_number="1",
        gross_income=Decimal("1750.00"),
        expenditures=[],
        net_payout=Decimal("1750.00"),  # Balanced!
    )

    parse_mock = MagicMock(side_effect=[stmt_attempt1, stmt_attempt2])
    service.extractor.parse_rental_statement = parse_mock

    statement_text = "Landlord Statement for Reference: REF01 Statement Number: 1 Rent from 18/10/2026"
    with patch("src.ingestion.batch.extract_text_from_pdf", return_value=statement_text):
        result = service.process_file(pdf_file)

    assert parse_mock.call_count == 2
    assert result.status == "ingested"
    assert db.get_all_monthly_statements()[0]["statement_number"] == "1"


# [verifies: INGEST-003/AC-INGEST-003.4]
def test_rescan_failure_after_3_attempts_rejects_and_continues(tmp_path: Path, test_config):
    """Verify that if reconciliation fails after 3 attempts, the system rejects saving, highlights failure, and does not persist."""
    from unittest.mock import MagicMock

    from src.ingestion.batch import BatchIngestionService

    db = Database(db_path=tmp_path / "fail_test.db")
    service = BatchIngestionService(db=db, config=test_config)

    pdf_file = tmp_path / "broken_statement.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 unbalanceable statement")

    broken_statement = RentalStatement(
        statement_date="16/10/2026",
        reference="BROKEN",
        statement_number="99",
        gross_income=Decimal("1750.00"),
        expenditures=[
            ExpenditureLine(description="Fee", net=Decimal("100.00"), gross=Decimal("100.00")),
        ],
        expenditure_subtotal=Decimal("200.00"),  # 100 != 200
        net_payout=Decimal("1000.00"),  # 1750 - 200 != 1000
    )

    parse_mock = MagicMock(return_value=broken_statement)
    service.extractor.parse_rental_statement = parse_mock

    statement_text = "Landlord Statement for Reference: BROKEN Statement Number: 99 Rent from 18/10/2026"
    with patch("src.ingestion.batch.extract_text_from_pdf", return_value=statement_text):
        result = service.process_file(pdf_file)

    assert parse_mock.call_count == 3
    assert result.status == "rejected"
    assert "RECONCILIATION_FAILED (after 3 attempts)" in result.details
    assert "Expenditure lines sum" in result.details
    assert len(db.get_all_monthly_statements()) == 0


# [verifies: INGEST-003/AC-INGEST-003.1]
def test_parse_rental_statement_zero_subtotals_fallback():
    """Verify that if LLM returns 0.00 for income_subtotal or expenditure_subtotal, the extractor falls back to line item sums."""
    from unittest.mock import MagicMock

    from src.ingestion.extractor import OllamaExtractor

    extractor = OllamaExtractor()
    # Mock LLM returning 0.00 for income_subtotal and expenditure_subtotal (e.g. confusing with Opening Balance)
    mock_llm_data = {
        "statement_date": "09/03/2026",
        "reference": "WGL230032",
        "statement_number": "14",
        "income_items": [
            {"description": "Rent from 07/03/2026 to 06/04/2026", "net": "1650.00", "vat": "0.00", "gross": "1650.00"}
        ],
        "income_subtotal": "0.00",
        "gross_rent": "0.00",
        "expenditures": [
            {"description": "Tenancy Deposit Scheme", "net": "9.00", "vat": "1.80", "gross": "10.80"},
            {"description": "Letting fees at 10%", "net": "165.00", "vat": "33.00", "gross": "198.00"},
            {"description": "Management fees at 5%", "net": "82.50", "vat": "16.50", "gross": "99.00"},
        ],
        "expenditure_subtotal": "0.00",
        "net_payout": "1342.20",
    }
    extractor._query_ollama = MagicMock(return_value=mock_llm_data)

    parsed = extractor.parse_rental_statement("dummy raw text")

    # Assert robust fallback kicked in:
    assert parsed.income_subtotal == Decimal("1650.00")
    assert parsed.gross_income == Decimal("1650.00")
    assert parsed.expenditure_subtotal == Decimal("307.80")
    assert parsed.net_payout == Decimal("1342.20")

    # Reconciler should pass with flying colors
    reconcil = reconcile_statement(parsed)
    assert reconcil.is_balanced is True
    assert reconcil.income_check_passed is True
    assert reconcil.expenditure_check_passed is True
    assert reconcil.payout_check_passed is True


# [verifies: INGEST-003/AC-INGEST-003.1]
def test_parse_rental_statement_payout_text_fallback():
    """Verify that if LLM hallucinates or returns mismatching net_payout, extractor uses the exact Payment to Landlord text."""
    from unittest.mock import MagicMock

    from src.ingestion.extractor import OllamaExtractor

    extractor = OllamaExtractor()
    mock_llm_data = {
        "statement_date": "11/05/2026",
        "reference": "WGL230032",
        "statement_number": "11",
        "income_items": [
            {"description": "Rent from 07/05/2026 to 06/06/2026", "net": "1650.00", "vat": "0.00", "gross": "1650.00"}
        ],
        "income_subtotal": "1650.00",
        "gross_rent": "1650.00",
        "expenditures": [
            {"description": "Invoice from Gas Flow Heating", "net": "84.00", "vat": "0.00", "gross": "84.00"},
            {"description": "Tenancy Deposit Scheme - Monthly Fee", "net": "11.25", "vat": "2.25", "gross": "13.50"},
            {"description": "Letting fees at 10%", "net": "165.00", "vat": "33.00", "gross": "198.00"},
            {"description": "Management fees at 5%", "net": "82.50", "vat": "16.50", "gross": "99.00"},
        ],
        "expenditure_subtotal": "394.50",
        "net_payout": "1342.20",  # Hallucinated or biased
    }
    extractor._query_ollama = MagicMock(return_value=mock_llm_data)

    raw_statement_text = (
        "Property: 12 High Street\n"
        "Date Description Net VAT Gross\n"
        "Income\n"
        "11/05/2026 Rent from 07/05/2026 to 06/06/2026 £1,650.00 £0.00 £1,650.00\n"
        "Subtotal £1,650.00 £0.00 £1,650.00\n"
        "Expenditure\n"
        "11/05/2026 Invoice from Gas Flow Heating £84.00 £0.00 £84.00\n"
        "11/05/2026 Tenancy Deposit Scheme - Monthly Fee £11.25 £2.25 £13.50\n"
        "11/05/2026 Letting fees at 10% £165.00 £33.00 £198.00\n"
        "11/05/2026 Management fees at 5% £82.50 £16.50 £99.00\n"
        "Subtotal £342.75 £51.75 £394.50\n"
        "Landlord Payments\n"
        "11/05/2026 Payment to Landlord £1,255.50 £0.00 £1,255.50\n"
        "Subtotal £1,255.50 £0.00 £1,255.50\n"
    )

    parsed = extractor.parse_rental_statement(raw_statement_text)
    assert parsed.net_payout == Decimal("1255.50")

    rec = reconcile_statement(parsed)
    assert rec.is_balanced is True
    assert rec.payout_check_passed is True

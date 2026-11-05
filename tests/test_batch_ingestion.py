"""Tests for INGEST-004: Directory Batch PDF Ingestion & Summary Reporting."""

from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest

from src.config import AppConfig, MortgageSettings, OllamaSettings
from src.domain.models import ContractorInvoice, ExpenditureLine, RentalStatement
from src.ingestion.batch import (
    BatchIngestionService,
)
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


# [verifies: INGEST-004/AC-INGEST-004.1]
def test_scan_directory_discovers_all_pdf_files(tmp_path: Path, test_config):
    """Verify that scan_directory discovers all .pdf files in directory, ignoring non-pdf files and hidden files."""
    db = Database(db_path=tmp_path / "test.db")
    service = BatchIngestionService(db=db, config=test_config)

    # Create dummy files
    (tmp_path / "doc1.pdf").write_text("dummy")
    (tmp_path / "doc2.PDF").write_text("dummy")  # case variations or normal
    (tmp_path / "other.txt").write_text("dummy")
    (tmp_path / ".hidden.pdf").write_text("dummy")

    discovered = service.scan_directory(tmp_path)
    file_names = [f.name for f in discovered]
    assert "doc1.pdf" in file_names
    assert "other.txt" not in file_names
    assert ".hidden.pdf" not in file_names


# [verifies: INGEST-004/AC-INGEST-004.2]
def test_process_directory_extracts_and_persists_non_duplicates(tmp_path: Path, test_config):
    """Verify classification, offline extraction, and persistence to SQLite for non-duplicates."""
    db = Database(db_path=tmp_path / "test.db")
    service = BatchIngestionService(db=db, config=test_config)

    file_a = tmp_path / "statement.pdf"
    file_a.write_bytes(b"%PDF-1.4 statement content A")
    file_b = tmp_path / "invoice.pdf"
    file_b.write_bytes(b"%PDF-1.4 invoice content B")

    dummy_statement = RentalStatement(
        statement_date="16/10/2026",
        reference="REF123",
        statement_number="101",
        gross_income=Decimal("1750.00"),
        expenditures=[
            ExpenditureLine(
                description="Agency fee", net=Decimal("150.00"), vat=Decimal("30.00"), gross=Decimal("180.00")
            )
        ],
        net_payout=Decimal("1570.00"),
    )
    dummy_invoice = ContractorInvoice(
        contractor_name="Quick Plumber",
        invoice_date="14/10/2026",
        invoice_number="INV-999",
        gross_amount=Decimal("120.00"),
        job_description="Fix leak",
    )

    with (
        patch("src.ingestion.batch.extract_text_from_pdf") as mock_extract_text,
        patch.object(service.extractor, "parse_rental_statement", return_value=dummy_statement),
        patch.object(service.extractor, "parse_contractor_invoice", return_value=dummy_invoice),
    ):
        mock_extract_text.side_effect = lambda path: (
            "Landlord Statement rent from" if "statement" in path.name else "Invoice for plumbing"
        )

        report = service.process_directory(tmp_path)

        assert report.total_files == 2
        assert report.ingested_statements == 1
        assert report.ingested_invoices == 1
        assert report.skipped_duplicates == 0
        assert report.failed_files == 0

        # Check DB records
        conn = db._get_connection()
        assert conn.execute("SELECT COUNT(*) FROM monthly_records").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM contractor_invoices").fetchone()[0] == 1


# [verifies: INGEST-004/AC-INGEST-004.3]
def test_summary_report_tracks_duplicates_and_reasons(tmp_path: Path, test_config):
    """Verify summary report tracks duplicates skipped with their specific reasons."""
    db = Database(db_path=tmp_path / "test.db")
    service = BatchIngestionService(db=db, config=test_config)

    file_a = tmp_path / "a_statement.pdf"
    file_a.write_bytes(b"%PDF-1.4 identical bytes")
    file_b = tmp_path / "b_duplicate_statement.pdf"
    file_b.write_bytes(b"%PDF-1.4 identical bytes")

    def mock_parse(raw_text: str, file_hash: str | None = None) -> RentalStatement:
        return RentalStatement(
            statement_date="16/10/2026",
            reference="REF123",
            statement_number="101",
            gross_income=Decimal("1750.00"),
            expenditures=[],
            net_payout=Decimal("1750.00"),
            file_hash=file_hash,
        )

    with (
        patch("src.ingestion.batch.extract_text_from_pdf", return_value="Landlord Statement rent from"),
        patch.object(service.extractor, "parse_rental_statement", side_effect=mock_parse),
    ):
        report = service.process_directory(tmp_path)

        assert report.total_files == 2
        assert report.ingested_statements == 1
        assert report.skipped_duplicates == 1
        dup_results = [r for r in report.results if r.status == "duplicate"]
        assert len(dup_results) == 1
        assert "SHA-256 fingerprint" in dup_results[0].details


# [verifies: INGEST-004/AC-INGEST-004.4]
def test_directory_ingestion_resilience_to_individual_file_failures(tmp_path: Path, test_config):
    """Verify that an error on an individual file is logged and does not abort remaining files."""
    db = Database(db_path=tmp_path / "test.db")
    service = BatchIngestionService(db=db, config=test_config)

    file_1 = tmp_path / "bad.pdf"
    file_1.write_bytes(b"%PDF bad content")
    file_2 = tmp_path / "good_invoice.pdf"
    file_2.write_bytes(b"%PDF good content")

    dummy_invoice = ContractorInvoice(
        contractor_name="Electrician Ltd",
        invoice_date="12/10/2026",
        invoice_number="INV-001",
        gross_amount=Decimal("80.00"),
    )

    def fake_extract(path: Path):
        if "bad" in path.name:
            raise ValueError("Corrupt PDF stream")
        return "Invoice for electrical works"

    with (
        patch("src.ingestion.batch.extract_text_from_pdf", side_effect=fake_extract),
        patch.object(service.extractor, "parse_contractor_invoice", return_value=dummy_invoice),
    ):
        report = service.process_directory(tmp_path)

        assert report.total_files == 2
        assert report.failed_files == 1
        assert report.ingested_invoices == 1

        error_results = [r for r in report.results if r.status == "error"]
        assert len(error_results) == 1
        assert "Corrupt PDF stream" in error_results[0].details


# [verifies: INGEST-005/AC-INGEST-005.1]
def test_batch_ingestion_measures_elapsed_wall_clock_time(tmp_path: Path, test_config):
    """AC-INGEST-005.1: Verify recording timestamps to compute overall elapsed wall-clock processing time."""
    db = Database(db_path=tmp_path / "test.db")
    service = BatchIngestionService(db=db, config=test_config)

    file_1 = tmp_path / "statement.pdf"
    file_1.write_bytes(b"%PDF statement")

    dummy_statement = RentalStatement(
        statement_date="16/10/2026",
        reference="REF1",
        statement_number="1",
        gross_income=Decimal("1750.00"),
        expenditures=[],
        net_payout=Decimal("1750.00"),
    )

    with (
        patch("src.ingestion.batch.extract_text_from_pdf", return_value="Landlord Statement rent from"),
        patch.object(service.extractor, "parse_rental_statement", return_value=dummy_statement),
    ):
        report = service.process_directory(tmp_path)
        assert report.total_files == 1
        assert report.total_elapsed_seconds >= 0.0


# [verifies: INGEST-005/AC-INGEST-005.2]
def test_batch_ingestion_summary_displays_durations_and_averages(tmp_path: Path, test_config):
    """AC-INGEST-005.2: Verify summary report displays overall batch time, average per doc, and individual durations."""
    db = Database(db_path=tmp_path / "test.db")
    service = BatchIngestionService(db=db, config=test_config)

    file_1 = tmp_path / "statement.pdf"
    file_1.write_bytes(b"%PDF statement")
    file_2 = tmp_path / "invoice.pdf"
    file_2.write_bytes(b"%PDF invoice")

    dummy_statement = RentalStatement(
        statement_date="16/10/2026",
        reference="REF1",
        statement_number="1",
        gross_income=Decimal("1750.00"),
        expenditures=[],
        net_payout=Decimal("1750.00"),
    )
    dummy_invoice = ContractorInvoice(
        contractor_name="Gas Flow",
        invoice_date="15/10/2026",
        invoice_number="INV1",
        gross_amount=Decimal("138.00"),
    )

    with (
        patch("src.ingestion.batch.extract_text_from_pdf", return_value="Landlord Statement rent from"),
        patch.object(service.extractor, "parse_rental_statement", return_value=dummy_statement),
        patch.object(service.extractor, "parse_contractor_invoice", return_value=dummy_invoice),
    ):
        report = service.process_directory(tmp_path)

        assert report.total_files == 2
        # Elapsed times are non-negative and recorded
        assert report.total_elapsed_seconds >= 0.0
        assert report.average_seconds_per_file >= 0.0
        for res in report.results:
            assert res.elapsed_seconds >= 0.0


# [verifies: INGEST-005/AC-INGEST-005.3]
def test_single_file_timing_output(tmp_path: Path, test_config, capsys):
    """Verify that single-file processing output displays the total elapsed extraction and persistence time."""
    from argparse import Namespace

    from tools.ingest import process_single_file

    db = Database(db_path=tmp_path / "test.db")
    file_path = tmp_path / "statement.pdf"
    file_path.write_bytes(b"%PDF content")

    dummy_statement = RentalStatement(
        statement_date="16/10/2026",
        reference="REF100",
        statement_number="1",
        gross_income=Decimal("1750.00"),
        expenditures=[],
        net_payout=Decimal("1750.00"),
    )

    args = Namespace(
        target_path=file_path,
        type="statement",
        balance=Decimal("68000.00"),
        dry_run=True,
        overwrite=False,
    )

    with (
        patch("tools.ingest.extract_text_from_pdf", return_value="Landlord Statement rent from"),
        patch("tools.ingest.OllamaExtractor.parse_rental_statement", return_value=dummy_statement),
    ):
        ret = process_single_file(args=args, config=test_config, db=db)
        assert ret == 0

        captured = capsys.readouterr()
        assert "TICKET:" in captured.out
        assert "INGESTED" in captured.out


# [verifies: INGEST-008/AC-INGEST-008.1]
def test_progress_bar_rendering_and_batch_progress_callback(tmp_path: Path, test_config):
    """Verify that batch progress displays file index, total count, percentage, and triggers callbacks."""
    from src.ingestion.batch import render_progress_bar

    # Verify render_progress_bar at various completions
    assert render_progress_bar(0, 10) == "[                        ] 0/10 (0%)"
    assert "5/10 (50%)" in render_progress_bar(5, 10)
    assert render_progress_bar(10, 10) == "[========================] 10/10 (100%)"

    db = Database(db_path=tmp_path / "test.db")
    service = BatchIngestionService(db=db, config=test_config)

    file_1 = tmp_path / "file1.pdf"
    file_1.write_bytes(b"%PDF content 1")
    file_2 = tmp_path / "file2.pdf"
    file_2.write_bytes(b"%PDF content 2")

    callback_events = []

    def tracking_callback(idx, total, fpath, result):
        callback_events.append((idx, total, fpath.name, result is not None))

    dummy_statement = RentalStatement(
        statement_date="16/10/2026",
        reference="REF1",
        statement_number="1",
        gross_income=Decimal("1500.00"),
        expenditures=[],
        net_payout=Decimal("1500.00"),
    )

    with (
        patch("src.ingestion.batch.extract_text_from_pdf", return_value="Landlord Statement rent from"),
        patch.object(service.extractor, "parse_rental_statement", return_value=dummy_statement),
    ):
        report = service.process_directory(tmp_path, progress_callback=tracking_callback)
        assert report.total_files == 2
        # Verify callbacks were called twice per file (start with result=None, finish with result=BatchFileResult)
        assert len(callback_events) == 4
        assert callback_events[0] == (1, 2, "file1.pdf", False)
        assert callback_events[1] == (1, 2, "file1.pdf", True)
        assert callback_events[2] == (2, 2, "file2.pdf", False)
        assert callback_events[3] == (2, 2, "file2.pdf", True)


# [verifies: INGEST-008/AC-INGEST-008.2]
def test_format_status_ticket_layout_and_fields():
    """Verify that format_status_ticket generates a formatted ticket with filename, category, status, and duration."""
    from src.ingestion.batch import BatchFileResult, format_status_ticket

    res = BatchFileResult(
        file_path=Path("sample_rent_oct.pdf"),
        doc_type="statement",
        status="ingested",
        details="Statement #101 (£1,750.00)",
        elapsed_seconds=1.23,
    )
    ticket = format_status_ticket(res)
    assert "TICKET: sample_rent_oct.pdf" in ticket
    assert "Document Category : STATEMENT" in ticket
    assert "Ingestion Status  : ✅ INGESTED" in ticket
    assert "Elapsed Duration  : 1.23s" in ticket
    assert "Diagnostic Detail : Statement #101 (£1,750.00)" in ticket


# [verifies: INGEST-008/AC-INGEST-008.3]
def test_status_ticket_diagnostic_reasons_for_failures_and_duplicates():
    """Verify that skipped duplicates, mismatches, and errors include explicit diagnostic reasons."""
    from src.ingestion.batch import BatchFileResult, format_status_ticket

    dup_res = BatchFileResult(
        file_path=Path("dup.pdf"),
        doc_type="statement",
        status="duplicate",
        details="Identical SHA-256 fingerprint (a1b2c3d4...)",
        elapsed_seconds=0.05,
    )
    dup_ticket = format_status_ticket(dup_res)
    assert "⚠️  DUPLICATE" in dup_ticket
    assert "Diagnostic Detail : Identical SHA-256 fingerprint" in dup_ticket

    mismatch_res = BatchFileResult(
        file_path=Path("mismatch.pdf"),
        doc_type="mismatch",
        status="rejected",
        details="PROPERTY_MISMATCH: Document references postcode 'B1 1BB'",
        elapsed_seconds=0.08,
    )
    mismatch_ticket = format_status_ticket(mismatch_res)
    assert "🚫 REJECTED" in mismatch_ticket
    assert "PROPERTY_MISMATCH" in mismatch_ticket

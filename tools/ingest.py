"""CLI command for ingesting rental statements and contractor invoices."""

import argparse
import sys
from decimal import Decimal
from pathlib import Path

from src.config import load_config
from src.domain.models import DocumentCategory
from src.ingestion.batch import (
    BatchFileResult,
    BatchIngestionService,
    format_status_ticket,
    render_progress_bar,
)
from src.ingestion.classifier import classify_document
from src.ingestion.duplicate_checker import DuplicateChecker
from src.ingestion.extractor import OllamaExtractor, OllamaServiceUnreachableError
from src.ingestion.pdf_reader import EncryptedPdfError, ScannedImagePdfError, extract_text_from_pdf
from src.ingestion.reconciler import reconcile_statement
from src.storage.database import Database


# [spec: INGEST-004]
# [spec: INGEST-008]
def run_batch_folder_ingestion(
    folder_path: Path,
    config,
    db: Database,
    balance: Decimal | None = None,
    dry_run: bool = False,
    overwrite: bool = False,
) -> int:
    """Execute batch ingestion over a directory of statements and invoices with live progress and status tickets."""
    print(f"\n📂 Scanning folder: {folder_path.resolve()}")
    service = BatchIngestionService(db=db, config=config)
    pdf_files = service.scan_directory(folder_path)

    if not pdf_files:
        print(f"⚠️ No PDF files found in directory: {folder_path}")
        return 0

    total_files = len(pdf_files)
    print(f"Found {total_files} PDF file(s) to process.\n")
    print("=" * 60)

    # AC-INGEST-008.1 & AC-INGEST-008.2: Live progress callback and status ticket emission
    def on_file_progress(index: int, total: int, file_path: Path, result: BatchFileResult | None) -> None:
        if result is None:
            # File started: show progress bar with current file name
            bar = render_progress_bar(index - 1, total)
            print(f"\n{bar} ⏳ Processing [{index}/{total}]: {file_path.name}")
        else:
            # File finished: print the output status ticket
            ticket = format_status_ticket(result)
            print(ticket)

    report = service.process_directory(
        folder_path,
        balance_override=balance,
        dry_run=dry_run,
        overwrite=overwrite,
        progress_callback=on_file_progress,
    )
    print_batch_summary(report)
    return 1 if report.failed_files > 0 else 0


# [spec: INGEST-004]
# [spec: INGEST-005]
def print_batch_summary(report) -> None:
    """Print the formatted summary report for batch ingestion with performance benchmarks."""
    print("\n" + "=" * 60)
    print("📊 BATCH INGESTION SUMMARY REPORT")
    print("=" * 60)
    print(f"  • Total files found:       {report.total_files}")
    print(f"  • Statements ingested:     {report.ingested_statements}")
    print(f"  • Invoices ingested:       {report.ingested_invoices}")
    print(f"  • Duplicates skipped:      {report.skipped_duplicates}")
    print(f"  • Unrecognized rejected:   {report.skipped_unrecognized}")
    print(f"  • Scanned images flagged:  {report.skipped_scanned}")
    print(f"  • Encrypted PDFs skipped:  {report.skipped_encrypted}")
    print(f"  • Compliance certificates: {report.compliance_certificates}")
    print(f"  • Files failed / errored:  {report.failed_files}")
    print(f"  • Total processing time:   {report.total_elapsed_seconds:.2f}s")
    print(f"  • Average per document:    {report.average_seconds_per_file:.2f}s")
    print("-" * 60)

    for res in report.results:
        status_icon = (
            "✅"
            if res.status in ("ingested", "compliance")
            else ("⚠️" if res.status in ("duplicate", "scanned", "encrypted") else "❌")
        )
        doc_label = res.doc_type.upper() if res.doc_type else "UNKNOWN"
        time_tag = f"({res.elapsed_seconds:.2f}s)" if res.elapsed_seconds > 0 else ""
        print(f"  {status_icon} [{doc_label}] {res.file_path.name} {time_tag}: {res.details}")
    print("=" * 60 + "\n")


# [spec: INGEST-001]
def detect_document_type(raw_text: str, user_type: str) -> str:
    """Classify document as 'statement' or 'invoice' based on text or user override."""
    if user_type != "auto":
        return user_type
    lower_text = raw_text.lower()
    if "landlord statement" in lower_text or "rent from" in lower_text:
        return "statement"
    return "invoice"


# [spec: INGEST-001]
# [spec: INGEST-002]
# [spec: INGEST-003]
def process_statement(
    raw_text: str,
    file_hash: str,
    extractor: OllamaExtractor,
    db: Database,
    config,
    balance: Decimal | None,
    dry_run: bool,
    overwrite: bool = False,
) -> int:
    """Process, reconcile, and persist a single rental statement."""
    statement = extractor.parse_rental_statement(raw_text, file_hash=file_hash)
    print("\n✅ Successfully extracted Rental Statement:")
    print(f"  • Date: {statement.statement_date}")
    print(f"  • Statement Number: #{statement.statement_number}")
    print(f"  • Reference: {statement.reference}")
    print(f"  • Gross Rent: £{statement.gross_income}")
    print(f"  • Total Deductions: £{statement.total_expenditure} ({len(statement.expenditures)} items)")
    for item in statement.expenditures:
        print(f"      - {item.description}: £{item.gross} (Net: £{item.net}, VAT: £{item.vat})")
    print(f"  • Net Landlord Payout: £{statement.net_payout}")

    reconciliation = reconcile_statement(statement)
    if reconciliation.is_balanced:
        print("\n⚖️  Mathematical Reconciliation: ✅ BALANCED (Penny-exact)")
    else:
        print("\n⚖️  Mathematical Reconciliation: ❌ FAILED")
        for reason in reconciliation.failure_reasons:
            print(f"      • {reason}")
        print("      ⚠️ Statement will not be persisted to the database.")
        return 1

    if not overwrite and db.has_semantic_statement(statement.reference, statement.statement_number):
        print(
            f"\n⚠️ DUPLICATE DETECTED: Statement #{statement.statement_number} ({statement.reference}) already exists in database with different file bytes. Skipping insertion."
        )
        return 0

    if not dry_run:
        recorded_balance = (
            balance if balance is not None else (db.get_latest_mortgage_balance() or config.mortgage.initial_principal)
        )
        if overwrite and db.has_semantic_statement(statement.reference, statement.statement_number):
            record_id = db.overwrite_monthly_statement(
                statement=statement,
                mortgage_debit=config.mortgage.monthly_direct_debit,
                outstanding_balance=recorded_balance,
            )
            print(f"🔄 Overwrote existing monthly statement & balance in SQLite (record #{record_id})")
        else:
            record_id = db.save_monthly_statement(
                statement=statement,
                mortgage_debit=config.mortgage.monthly_direct_debit,
                outstanding_balance=recorded_balance,
            )
            print(
                f"💾 Persisted monthly statement & balance (£{recorded_balance:,.2f}) to SQLite (record #{record_id})"
            )

    return 0


# [spec: INGEST-001]
# [spec: INGEST-002]
def process_invoice(
    raw_text: str,
    file_hash: str,
    extractor: OllamaExtractor,
    db: Database,
    dry_run: bool,
) -> int:
    """Process and persist a contractor invoice."""
    invoice = extractor.parse_contractor_invoice(raw_text, file_hash=file_hash)
    print("\n✅ Successfully extracted Contractor Invoice:")
    print(f"  • Contractor: {invoice.contractor_name}")
    print(f"  • Invoice Date: {invoice.invoice_date}")
    print(f"  • Invoice Number: #{invoice.invoice_number}")
    print(f"  • Amount: £{invoice.gross_amount}")
    if invoice.job_description:
        print(f"  • Description: {invoice.job_description}")
    if invoice.line_items:
        print(f"  • Items: {', '.join(invoice.line_items)}")

    if db.has_semantic_invoice(invoice.contractor_name, invoice.invoice_number):
        print(
            f"\n⚠️ DUPLICATE DETECTED: Invoice #{invoice.invoice_number} from {invoice.contractor_name} already exists in database. Skipping insertion."
        )
        return 0

    if not dry_run:
        record_id = db.save_contractor_invoice(invoice)
        print(f"💾 Persisted contractor invoice to SQLite (record #{record_id})")

    return 0


# [spec: INGEST-001]
# [spec: INGEST-002]
# [spec: INGEST-005]
# [spec: INGEST-006]
# [spec: INGEST-007]
def process_single_file(args, config, db: Database) -> int:
    """Execute single-file ingestion workflow with duplicate detection, timing, and dispatch."""
    import time

    start_time = time.perf_counter()
    file_path = args.target_path
    print(f"\n📄 Reading PDF: {file_path.name}")
    try:
        raw_text = extract_text_from_pdf(file_path)
    except ScannedImagePdfError as exc:
        print(f"\n⚠️  SCANNED_IMAGE_PDF: {exc}", file=sys.stderr)
        return 1
    except EncryptedPdfError as exc:
        print(f"\n⚠️  ENCRYPTED_PDF: {exc}", file=sys.stderr)
        return 1

    file_hash = DuplicateChecker.compute_file_hash(file_path)
    print(f"🔒 SHA-256 Fingerprint: {file_hash[:16]}...")

    if not args.overwrite and db.has_file_hash(file_hash):
        print(
            f"⚠️ DUPLICATE DETECTED: File with identical SHA-256 ({file_hash[:16]}...) has already been ingested. Skipping insertion."
        )
        return 0

    prop_settings = getattr(config, "property", None)
    classification = classify_document(raw_text, property_config=prop_settings)

    if not classification.property_match:
        detected = classification.detected_postcode or "unknown"
        print(
            f"\n❌ PROPERTY_MISMATCH: Document references postcode '{detected}', which does not match configured property. Skipping insertion.",
            file=sys.stderr,
        )
        return 1

    if classification.category == DocumentCategory.UNRECOGNIZED_DOCUMENT:
        print(
            "\n❌ UNRECOGNIZED_DOCUMENT: No rental statement, contractor invoice, or compliance markers detected. Skipping insertion.",
            file=sys.stderr,
        )
        return 1

    if classification.category == DocumentCategory.COMPLIANCE_CERTIFICATE:
        print(
            f"\n📋 COMPLIANCE_CERTIFICATE: {classification.reason}. Indexed for compliance record (not persisted to ledger)."
        )
        return 0

    doc_type = (
        args.type
        if args.type != "auto"
        else ("statement" if classification.category == DocumentCategory.RENTAL_STATEMENT else "invoice")
    )
    print(f"🏷️  Document Category: {doc_type.upper()}")

    print(f"🧠 Querying local Ollama model '{config.ollama.model}'...")
    extractor = OllamaExtractor(base_url=config.ollama.base_url, model=config.ollama.model)

    try:
        if doc_type == "statement":
            res = process_statement(
                raw_text=raw_text,
                file_hash=file_hash,
                extractor=extractor,
                db=db,
                config=config,
                balance=args.balance,
                dry_run=args.dry_run,
                overwrite=args.overwrite,
            )
        else:
            res = process_invoice(
                raw_text=raw_text,
                file_hash=file_hash,
                extractor=extractor,
                db=db,
                dry_run=args.dry_run,
            )
        elapsed = round(time.perf_counter() - start_time, 2)
        ticket = format_status_ticket(
            BatchFileResult(
                file_path=file_path,
                doc_type=doc_type,
                status="ingested" if res == 0 else "error",
                details="Single file processed successfully" if res == 0 else "Processing failed",
                elapsed_seconds=elapsed,
            )
        )
        print("\n" + ticket)
        return res
    except OllamaServiceUnreachableError as exc:
        elapsed = round(time.perf_counter() - start_time, 2)
        ticket = format_status_ticket(
            BatchFileResult(
                file_path=file_path,
                doc_type=doc_type,
                status="error",
                details=f"Ollama unreachable: {exc}",
                elapsed_seconds=elapsed,
            )
        )
        print("\n" + ticket, file=sys.stderr)
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="ingest",
        description="Offline PDF Ingestion via local Ollama and pdfplumber (file or folder)",
    )
    parser.add_argument("target_path", type=Path, help="Path to PDF file or directory of PDFs to ingest")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config.toml"),
        help="Path to project config file (default: config.toml)",
    )
    parser.add_argument(
        "--type",
        choices=["statement", "invoice", "auto"],
        default="auto",
        help="Type of document for single file (default: auto-detect)",
    )
    parser.add_argument("--model", help="Local Ollama model override (default: from config.toml)")
    parser.add_argument(
        "--balance",
        type=Decimal,
        help="Optional month-end remaining mortgage principal to record alongside statement",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Extract and display results without persisting to database",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing statement if already recorded for this month/reference",
    )

    args = parser.parse_args()

    try:
        config = load_config(args.config)
    except Exception as exc:
        print(f"❌ Configuration error: {exc}", file=sys.stderr)
        return 1

    if args.model:
        config.ollama.model = args.model

    if not args.target_path.exists():
        print(f"❌ Error: Path not found: {args.target_path}", file=sys.stderr)
        return 1

    db = Database()

    if args.target_path.is_dir():
        return run_batch_folder_ingestion(
            folder_path=args.target_path,
            config=config,
            db=db,
            balance=args.balance,
            dry_run=args.dry_run,
            overwrite=args.overwrite,
        )

    return process_single_file(args=args, config=config, db=db)


if __name__ == "__main__":
    sys.exit(main())

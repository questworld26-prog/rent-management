"""Batch directory ingestion pipeline for statements and contractor invoices.
Bound to specifications in specs/ingestion/pdf_ingestion.md.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from src.config import AppConfig
from src.domain.models import DocumentCategory
from src.domain.mortgage import amortize_single_month
from src.ingestion.classifier import classify_document
from src.ingestion.duplicate_checker import DuplicateChecker
from src.ingestion.extractor import OllamaExtractor, OllamaServiceUnreachableError
from src.ingestion.pdf_reader import EncryptedPdfError, ScannedImagePdfError, extract_text_from_pdf
from src.ingestion.reconciler import reconcile_statement
from src.storage.database import Database


# [spec: INGEST-004]
@dataclass
class BatchFileResult:
    file_path: Path
    doc_type: str  # "statement" | "invoice" | "compliance" | "unrecognized" | "scanned" | "encrypted" | "unknown"
    status: str  # "ingested" | "duplicate" | "rejected" | "compliance" | "scanned" | "encrypted" | "error"
    details: str = ""
    record_id: int | None = None
    elapsed_seconds: float = 0.0


# Type for batch progress notification: (current_index, total_count, file_path, optional_result)
ProgressCallback = Callable[[int, int, Path, BatchFileResult | None], None]


# [spec: INGEST-008]
def render_progress_bar(current: int, total: int, width: int = 24) -> str:
    """Render a text progress bar: [=====>    ] 3/10 (30%)."""
    if total <= 0:
        return f"[{' ' * width}] 0/0 (0%)"
    fraction = min(max(current / total, 0.0), 1.0)
    filled_len = int(width * fraction)
    if filled_len == width:
        bar = "=" * width
    elif filled_len > 0:
        bar = "=" * (filled_len - 1) + ">" + " " * (width - filled_len)
    else:
        bar = " " * width
    pct = int(fraction * 100)
    return f"[{bar}] {current}/{total} ({pct}%)"


# [spec: INGEST-008]
def format_status_ticket(result: BatchFileResult) -> str:
    """Format an immediate processing status ticket for a processed file."""
    status_icon_map = {
        "ingested": "✅ INGESTED",
        "duplicate": "⚠️  DUPLICATE",
        "rejected": "🚫 REJECTED",
        "compliance": "📋 COMPLIANCE",
        "scanned": "⚠️  SCANNED_IMAGE",
        "encrypted": "🔒 ENCRYPTED",
        "error": "❌ ERROR",
    }
    status_tag = status_icon_map.get(result.status, result.status.upper())
    doc_tag = result.doc_type.upper()
    duration_str = f"{result.elapsed_seconds:.2f}s" if result.elapsed_seconds > 0 else "0.00s"

    lines = [
        f"┌─[ TICKET: {result.file_path.name} ]" + "─" * max(0, 50 - len(result.file_path.name)),
        f"│ Document Category : {doc_tag}",
        f"│ Ingestion Status  : {status_tag}",
        f"│ Elapsed Duration  : {duration_str}",
    ]
    if result.details:
        lines.append(f"│ Diagnostic Detail : {result.details}")
    lines.append("└" + "─" * 68)
    return "\n".join(lines)


# [spec: INGEST-004]
@dataclass
class BatchIngestionReport:
    total_files: int = 0
    ingested_statements: int = 0
    ingested_invoices: int = 0
    skipped_duplicates: int = 0
    skipped_unrecognized: int = 0
    skipped_scanned: int = 0
    skipped_encrypted: int = 0
    compliance_certificates: int = 0
    failed_files: int = 0
    total_elapsed_seconds: float = 0.0
    results: list[BatchFileResult] = field(default_factory=list)

    @property
    def average_seconds_per_file(self) -> float:
        """Average elapsed seconds per processed file."""
        if self.total_files == 0:
            return 0.0
        return round(self.total_elapsed_seconds / self.total_files, 2)


# [spec: INGEST-004]
class BatchIngestionService:
    """Service to discover and ingest all PDFs in a given directory."""

    def __init__(self, db: Database, config: AppConfig):
        self.db = db
        self.config = config

        self.extractor = OllamaExtractor(
            base_url=config.ollama.base_url,
            model=config.ollama.model,
        )

    def scan_directory(self, folder_path: Path) -> list[Path]:
        """Discover all PDF files in directory sorted alphabetically."""
        if not folder_path.exists() or not folder_path.is_dir():
            return []
        pdf_files = sorted(folder_path.glob("*.pdf"))
        return [f for f in pdf_files if not f.name.startswith(".")]

    # [spec: INGEST-001]
    # [spec: INGEST-002]
    # [spec: INGEST-003]
    # [spec: INGEST-006]
    # [spec: INGEST-007]
    def process_file(
        self,
        file_path: Path,
        balance_override: Decimal | None = None,
        dry_run: bool = False,
        overwrite: bool = False,
    ) -> BatchFileResult:
        """Process a single PDF: degradation check, duplicate check, classification, extraction, and persistence."""
        import time

        start_time = time.perf_counter()
        try:
            # 1. Extract text and check for degradation (INGEST-007)
            raw_text = extract_text_from_pdf(file_path)
            file_hash = DuplicateChecker.compute_file_hash(file_path)

            # 2. Level 1 duplicate check (INGEST-002)
            if not overwrite and self.db.has_file_hash(file_hash):
                elapsed = round(time.perf_counter() - start_time, 2)
                return BatchFileResult(
                    file_path=file_path,
                    doc_type="unknown",
                    status="duplicate",
                    details=f"Identical SHA-256 fingerprint ({file_hash[:12]}...)",
                    elapsed_seconds=elapsed,
                )

            # 3. Document relevance classification & scope guard (INGEST-006)
            prop_settings = getattr(self.config, "property", None)
            classification = classify_document(raw_text, property_config=prop_settings)

            # AC-INGEST-006.3: Check property address / postcode scope
            if not classification.property_match:
                elapsed = round(time.perf_counter() - start_time, 2)
                detected = classification.detected_postcode or "unknown"
                return BatchFileResult(
                    file_path=file_path,
                    doc_type="mismatch",
                    status="rejected",
                    details=f"PROPERTY_MISMATCH: Document references postcode '{detected}', does not match config",
                    elapsed_seconds=elapsed,
                )

            # AC-INGEST-006.2: Reject unrecognized documents
            if classification.category == DocumentCategory.UNRECOGNIZED_DOCUMENT:
                elapsed = round(time.perf_counter() - start_time, 2)
                return BatchFileResult(
                    file_path=file_path,
                    doc_type="unrecognized",
                    status="rejected",
                    details="UNRECOGNIZED_DOCUMENT: No rental statement, invoice, or compliance markers detected",
                    elapsed_seconds=elapsed,
                )

            # AC-INGEST-006.4: Report compliance certificates without ledger insertion
            if classification.category == DocumentCategory.COMPLIANCE_CERTIFICATE:
                elapsed = round(time.perf_counter() - start_time, 2)
                return BatchFileResult(
                    file_path=file_path,
                    doc_type="compliance",
                    status="compliance",
                    details=f"COMPLIANCE_CERTIFICATE: {classification.reason}. Indexed for compliance record.",
                    elapsed_seconds=elapsed,
                )

            # 4. Process Statements and Invoices
            if classification.category == DocumentCategory.RENTAL_STATEMENT:
                return self.process_batch_statement(
                    file_path=file_path,
                    raw_text=raw_text,
                    file_hash=file_hash,
                    start_time=start_time,
                    balance_override=balance_override,
                    dry_run=dry_run,
                    overwrite=overwrite,
                )
            else:
                return self.process_batch_invoice(
                    file_path=file_path,
                    raw_text=raw_text,
                    file_hash=file_hash,
                    start_time=start_time,
                    dry_run=dry_run,
                )

        except ScannedImagePdfError as exc:
            # AC-INGEST-007.1
            elapsed = round(time.perf_counter() - start_time, 2)
            return BatchFileResult(
                file_path=file_path,
                doc_type="scanned",
                status="scanned",
                details=f"SCANNED_IMAGE_PDF: {exc}",
                elapsed_seconds=elapsed,
            )
        except EncryptedPdfError as exc:
            # AC-INGEST-007.2
            elapsed = round(time.perf_counter() - start_time, 2)
            return BatchFileResult(
                file_path=file_path,
                doc_type="encrypted",
                status="encrypted",
                details=f"ENCRYPTED_PDF: {exc}",
                elapsed_seconds=elapsed,
            )
        except OllamaServiceUnreachableError as exc:
            elapsed = round(time.perf_counter() - start_time, 2)
            return BatchFileResult(
                file_path=file_path,
                doc_type="unknown",
                status="error",
                details=f"Ollama unreachable: {exc}",
                elapsed_seconds=elapsed,
            )
        except Exception as exc:
            elapsed = round(time.perf_counter() - start_time, 2)
            return BatchFileResult(
                file_path=file_path,
                doc_type="unknown",
                status="error",
                details=str(exc),
                elapsed_seconds=elapsed,
            )

    # [spec: INGEST-001]
    # [spec: INGEST-002]
    # [spec: INGEST-003]
    # [spec: INGEST-007]
    def process_batch_statement(
        self,
        file_path: Path,
        raw_text: str,
        file_hash: str,
        start_time: float,
        balance_override: Decimal | None,
        dry_run: bool,
        overwrite: bool,
    ) -> BatchFileResult:
        """Handle extraction, duplicate verification, 3-attempt reconciliation, and persistence for a rental statement."""
        import time

        max_attempts = 3
        last_reconciliation = None
        statement = None

        for attempt in range(1, max_attempts + 1):
            statement = self.extractor.parse_rental_statement(raw_text, file_hash=file_hash)
            last_reconciliation = reconcile_statement(statement)
            if last_reconciliation.is_balanced:
                break
            # If checks failed and attempts remain, re-extract text and retry scan
            if attempt < max_attempts:
                raw_text = extract_text_from_pdf(file_path)

        assert last_reconciliation is not None
        assert statement is not None

        # AC-INGEST-003.4: If after 3 attempts any check still fails, reject saving and report failure
        if not last_reconciliation.is_balanced:
            elapsed = round(time.perf_counter() - start_time, 2)
            fail_summary = "; ".join(last_reconciliation.failure_reasons)
            return BatchFileResult(
                file_path=file_path,
                doc_type="statement",
                status="rejected",
                details=f"RECONCILIATION_FAILED (after 3 attempts): {fail_summary}",
                elapsed_seconds=elapsed,
            )

        # Level 2 duplicate check
        if not overwrite and self.db.has_semantic_statement(statement.reference, statement.statement_number):
            existing = self.db.get_statement_by_semantic_id(statement.reference, statement.statement_number)
            rec_info = f" (record #{existing['id']})" if existing else ""
            elapsed = round(time.perf_counter() - start_time, 2)
            return BatchFileResult(
                file_path=file_path,
                doc_type="statement",
                status="duplicate",
                details=f"Statement #{statement.statement_number} ({statement.reference}) exists{rec_info}",
                elapsed_seconds=elapsed,
            )

        if not dry_run:
            # If another statement already exists in this calendar month, this is a secondary statement:
            # mortgage is paid once per month, so debit = 0.00 and balance remains unchanged.
            month_has_prior_stmt = not overwrite and self.db.has_statement_in_month(statement.statement_date)

            if balance_override is not None:
                recorded_balance = balance_override
                recorded_debit = (
                    self.config.mortgage.monthly_direct_debit if not month_has_prior_stmt else Decimal("0.00")
                )
            elif month_has_prior_stmt:
                recorded_balance = self.db.get_latest_mortgage_balance() or self.config.mortgage.initial_principal
                recorded_debit = Decimal("0.00")
            else:
                prev_balance = self.db.get_latest_mortgage_balance() or self.config.mortgage.initial_principal
                recorded_balance = amortize_single_month(
                    current_balance=prev_balance,
                    monthly_direct_debit=self.config.mortgage.monthly_direct_debit,
                    annual_interest_rate_percent=self.config.mortgage.interest_rate,
                )
                recorded_debit = self.config.mortgage.monthly_direct_debit

            if overwrite and self.db.has_semantic_statement(statement.reference, statement.statement_number):
                record_id = self.db.overwrite_monthly_statement(
                    statement=statement,
                    mortgage_debit=recorded_debit,
                    outstanding_balance=recorded_balance,
                )
            else:
                record_id = self.db.save_monthly_statement(
                    statement=statement,
                    mortgage_debit=recorded_debit,
                    outstanding_balance=recorded_balance,
                )

        elapsed = round(time.perf_counter() - start_time, 2)
        return BatchFileResult(
            file_path=file_path,
            doc_type="statement",
            status="ingested",
            details=f"Statement #{statement.statement_number} ({statement.statement_date}) net payout £{statement.net_payout:,.2f}",
            record_id=record_id,
            elapsed_seconds=elapsed,
        )

    # [spec: INGEST-001]
    # [spec: INGEST-002]
    def process_batch_invoice(
        self,
        file_path: Path,
        raw_text: str,
        file_hash: str,
        start_time: float,
        dry_run: bool,
    ) -> BatchFileResult:
        """Handle extraction, duplicate verification, and persistence for a contractor invoice."""
        import time

        invoice = self.extractor.parse_contractor_invoice(raw_text, file_hash=file_hash)

        # Level 2 duplicate check
        if self.db.has_semantic_invoice(invoice.contractor_name, invoice.invoice_number):
            elapsed = round(time.perf_counter() - start_time, 2)
            return BatchFileResult(
                file_path=file_path,
                doc_type="invoice",
                status="duplicate",
                details=f"Invoice #{invoice.invoice_number} from {invoice.contractor_name} exists",
                elapsed_seconds=elapsed,
            )

        record_id = None
        if not dry_run:
            record_id = self.db.save_contractor_invoice(invoice)
            # AC-ISSUE-001.1: Auto-suggest maintenance issue on ingestion
            self.db.suggest_issue_from_invoice(record_id)

        elapsed = round(time.perf_counter() - start_time, 2)
        return BatchFileResult(
            file_path=file_path,
            doc_type="invoice",
            status="ingested",
            details=f"{invoice.contractor_name} #{invoice.invoice_number} £{invoice.gross_amount:,.2f}",
            record_id=record_id,
            elapsed_seconds=elapsed,
        )

    # [spec: INGEST-004]
    # [spec: INGEST-005]
    # [spec: INGEST-008]
    def process_directory(
        self,
        folder_path: Path,
        balance_override: Decimal | None = None,
        dry_run: bool = False,
        overwrite: bool = False,
        progress_callback: ProgressCallback | None = None,
    ) -> BatchIngestionReport:
        """Scan directory and sequentially process all PDF files, producing a summary report with timing and progress."""
        import time

        batch_start = time.perf_counter()
        pdf_files = self.scan_directory(folder_path)
        total_count = len(pdf_files)
        report = BatchIngestionReport(total_files=total_count)

        for index, pdf_path in enumerate(pdf_files, start=1):
            if progress_callback:
                # Notify start of file processing
                progress_callback(index, total_count, pdf_path, None)

            result = self.process_file(
                pdf_path, balance_override=balance_override, dry_run=dry_run, overwrite=overwrite
            )
            report.results.append(result)

            if progress_callback:
                # Notify completion of file processing with ticket data
                progress_callback(index, total_count, pdf_path, result)

            if result.status == "ingested":
                if result.doc_type == "statement":
                    report.ingested_statements += 1
                elif result.doc_type == "invoice":
                    report.ingested_invoices += 1
            elif result.status == "duplicate":
                report.skipped_duplicates += 1
            elif result.status == "rejected":
                report.skipped_unrecognized += 1
            elif result.status == "compliance":
                report.compliance_certificates += 1
            elif result.status == "scanned":
                report.skipped_scanned += 1
            elif result.status == "encrypted":
                report.skipped_encrypted += 1
            elif result.status == "error":
                report.failed_files += 1

        report.total_elapsed_seconds = round(time.perf_counter() - batch_start, 2)
        return report

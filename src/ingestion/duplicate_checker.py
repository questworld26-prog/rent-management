"""Two-level duplicate detection engine."""

import hashlib
from pathlib import Path
from typing import Protocol

from src.domain.models import (
    ContractorInvoice,
    DuplicateCheckResult,
    DuplicateType,
    RentalStatement,
)


# [spec: INGEST-002]
class DocumentStoreProtocol(Protocol):
    def has_file_hash(self, file_hash: str) -> bool: ...
    def find_statement_by_number(self, statement_number: str, reference: str) -> RentalStatement | None: ...
    def find_invoice(self, contractor_name: str, invoice_number: str) -> ContractorInvoice | None: ...


# [spec: INGEST-002]
class InMemoryDocumentStore:
    """In-memory store for tracking ingested documents."""

    def __init__(self):
        self.file_hashes: dict[str, str] = {}  # hash -> filename
        self.statements: list[RentalStatement] = []
        self.invoices: list[ContractorInvoice] = []

    def add_file_hash(self, file_hash: str, filename: str = "") -> None:
        self.file_hashes[file_hash] = filename

    def has_file_hash(self, file_hash: str) -> bool:
        return file_hash in self.file_hashes

    def add_statement(self, stmt: RentalStatement) -> None:
        if stmt.file_hash:
            self.add_file_hash(stmt.file_hash, f"Statement #{stmt.statement_number}")
        self.statements.append(stmt)

    def find_statement_by_number(self, statement_number: str, reference: str) -> RentalStatement | None:
        for s in self.statements:
            if s.statement_number == statement_number and s.reference == reference:
                return s
        return None

    def add_invoice(self, inv: ContractorInvoice) -> None:
        if inv.file_hash:
            self.add_file_hash(inv.file_hash, f"Invoice {inv.invoice_number}")
        self.invoices.append(inv)

    def find_invoice(self, contractor_name: str, invoice_number: str) -> ContractorInvoice | None:
        for inv in self.invoices:
            if inv.contractor_name.lower() == contractor_name.lower() and inv.invoice_number == invoice_number:
                return inv
        return None


# [spec: INGEST-002]
class DuplicateChecker:
    """Enforces strict two-level duplicate detection for ingested files."""

    def __init__(self, store: DocumentStoreProtocol):
        self.store = store

    @staticmethod
    def compute_file_hash(file_path: Path | str) -> str:
        """Compute SHA-256 hash of file bytes."""
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()

    def check_file(self, file_path: Path | str) -> DuplicateCheckResult:
        """Level 1 check: Check if identical file byte hash already exists."""
        file_hash = self.compute_file_hash(file_path)
        if self.store.has_file_hash(file_hash):
            return DuplicateCheckResult(
                is_duplicate=True,
                duplicate_type=DuplicateType.EXACT_FILE_HASH,
                file_hash=file_hash,
                message=f"Duplicate detected: File with SHA-256 hash {file_hash[:12]}... has already been ingested.",
                requires_user_confirmation=False,
            )
        return DuplicateCheckResult(
            is_duplicate=False,
            file_hash=file_hash,
            message="File is unique.",
        )

    def check_statement_semantic(self, statement: RentalStatement) -> DuplicateCheckResult:
        """Level 2 check: Check if statement number and reference already exist."""
        existing = self.store.find_statement_by_number(statement.statement_number, statement.reference)
        file_hash = statement.file_hash or ""

        if existing:
            return DuplicateCheckResult(
                is_duplicate=True,
                duplicate_type=DuplicateType.SEMANTIC_STATEMENT,
                file_hash=file_hash,
                message=(
                    f"Statement #{statement.statement_number} (Reference: {statement.reference}) already exists "
                    f"in the database with different content. Skip or Overwrite?"
                ),
                requires_user_confirmation=True,
            )

        return DuplicateCheckResult(
            is_duplicate=False,
            file_hash=file_hash,
            message="Statement record is unique.",
        )

    def check_invoice_semantic(self, invoice: ContractorInvoice) -> DuplicateCheckResult:
        """Level 2 check: Check if contractor name, invoice number, and amount match existing invoice."""
        existing = self.store.find_invoice(invoice.contractor_name, invoice.invoice_number)
        file_hash = invoice.file_hash or ""

        if existing and existing.gross_amount == invoice.gross_amount:
            return DuplicateCheckResult(
                is_duplicate=True,
                duplicate_type=DuplicateType.SEMANTIC_INVOICE,
                file_hash=file_hash,
                message=(
                    f"Duplicate invoice: Invoice #{invoice.invoice_number} from '{invoice.contractor_name}' "
                    f"for £{invoice.gross_amount} has already been recorded."
                ),
                requires_user_confirmation=False,
            )

        return DuplicateCheckResult(
            is_duplicate=False,
            file_hash=file_hash,
            message="Invoice is unique.",
        )

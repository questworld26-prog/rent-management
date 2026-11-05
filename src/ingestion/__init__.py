"""Document ingestion package."""

from src.ingestion.batch import (
    BatchFileResult,
    BatchIngestionReport,
    BatchIngestionService,
    format_status_ticket,
    render_progress_bar,
)
from src.ingestion.classifier import (
    check_property_match,
    classify_document,
    detect_postcode_in_text,
)
from src.ingestion.duplicate_checker import (
    DuplicateChecker,
    InMemoryDocumentStore,
)
from src.ingestion.extractor import (
    OllamaExtractor,
    OllamaServiceUnreachableError,
)
from src.ingestion.pdf_reader import extract_text_from_pdf
from src.ingestion.reconciler import reconcile_statement

__all__ = [
    "BatchFileResult",
    "BatchIngestionReport",
    "BatchIngestionService",
    "DuplicateChecker",
    "InMemoryDocumentStore",
    "OllamaExtractor",
    "OllamaServiceUnreachableError",
    "check_property_match",
    "classify_document",
    "detect_postcode_in_text",
    "extract_text_from_pdf",
    "format_status_ticket",
    "reconcile_statement",
    "render_progress_bar",
]

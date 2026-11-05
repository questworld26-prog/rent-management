# Document Ingestion & Offline Privacy Specification

## INGEST-001: Offline PDF Extraction via Local Ollama

When a user selects or syncs rental statement or contractor invoice PDFs, the system shall extract financial figures, dates, and line items entirely offline using local PDF text extraction and Ollama at localhost:11434 without transmitting data to external servers.

Acceptance Criteria:
- AC-INGEST-001.1: For letting agency statements, the system shall extract statement date, reference, statement number, gross rental income, individual expenditure lines with net and VAT amounts, and net payment to landlord.
- AC-INGEST-001.2: For contractor invoices, the system shall extract contractor name, invoice date, invoice number, line items, and gross amount. Extract description of the job if present.
- AC-INGEST-001.3: The extraction pipeline shall execute with zero external internet requests.
- AC-INGEST-001.4: If the local Ollama service is unreachable, just give an helpful error message and ask to try again.

## INGEST-002: Strict Two-Level Duplicate Detection & Same-Month Statement Policy

When a PDF document is processed for ingestion, the system shall verify that the document is not a duplicate using both file byte SHA-256 fingerprinting and semantic statement identifiers before persisting records to the database.

Acceptance Criteria:
- AC-INGEST-002.1: If the file byte SHA-256 matches an already ingested file, the system shall flag the document as a duplicate and skip insertion.
- AC-INGEST-002.2: If the statement number and reference match an existing database record but the file byte SHA-256 differs, the system shall notify the user, skip insertion by default to prevent double-counting, and log the existing record.
- AC-INGEST-002.3: For contractor invoices, if an invoice with identical contractor name, invoice number, and amount exists, the system shall flag it as a duplicate.
- AC-INGEST-002.4: Where a statement for an already recorded rental month is ingested with an explicit overwrite flag, the system shall replace the previous month's statement record and associated expenditures atomically in SQLite.

## INGEST-003: Deterministic Financial Reconciliation

When financial figures are extracted from a rental statement, the system shall verify that gross rental income minus total expenditure equals net landlord payment using Python Decimal arithmetic before saving.

Acceptance Criteria:
- AC-INGEST-003.1: The system shall perform a three-way deterministic check: (1) verify individual income items sum to income subtotal, (2) verify individual expenditure lines sum to expenditure subtotal, and (3) verify net landlord payment equals gross income minus total expenditure to the penny.
- AC-INGEST-003.2: If all three checks pass, the system shall automatically mark the financial reconciliation status as balanced and proceed to persist the record.
- AC-INGEST-003.3: If any of the three checks fail, the system shall automatically retry scanning and extraction up to 3 attempts.
- AC-INGEST-003.4: If after 3 attempts any check still fails, the system shall reject saving to the database, highlight the specific mathematical reconciliation failure in the processing report, and proceed to the next file without halting batch execution.

## INGEST-004: Directory Batch PDF Ingestion & Summary Reporting

When a user supplies a directory containing PDF documents for ingestion, the system shall discover all PDF files, sequentially process each statement or invoice through offline extraction, duplicate checking, and database persistence, and return a structured summary report.

Acceptance Criteria:
- AC-INGEST-004.1: The system shall scan the provided folder for all .pdf files.
- AC-INGEST-004.2: For each PDF file found, the system shall classify the document as statement or invoice, run duplicate detection, extract details offline via local Ollama, and persist non-duplicates to the local SQLite database.
- AC-INGEST-004.3: The system shall output a summary report containing counts of total files processed, newly ingested statements, newly ingested contractor invoices, and skipped duplicate files with reasons.
- AC-INGEST-004.4: If an individual PDF file fails during extraction or reconciliation, the system shall log the error for that file and continue processing the remaining files in the folder.

## INGEST-005: Ingestion Processing Time & Benchmark Metrics

When a single PDF or directory batch is ingested, the system shall measure and report the elapsed wall-clock processing time overall and per-document.

Acceptance Criteria:
- AC-INGEST-005.1: The system shall record timestamps at the start and conclusion of the ingestion pipeline to compute overall elapsed wall-clock processing time in seconds.
- AC-INGEST-005.2: In directory batch mode, the summary report shall display the overall batch processing time, the average processing time per document, and individual processing durations in the file breakdown.
- AC-INGEST-005.3: In single-file ingestion mode, the CLI output shall display the total elapsed extraction and persistence time.

## INGEST-006: Document Relevance Classification & Scope Guard

When a PDF document is analyzed during ingestion, the system shall classify the document's type and verify its relevance to the configured property before applying financial extraction schemas.

Acceptance Criteria:
- AC-INGEST-006.1: The system shall classify each document into one of: RENTAL_STATEMENT, CONTRACTOR_INVOICE, COMPLIANCE_CERTIFICATE, or UNRECOGNIZED_DOCUMENT.
- AC-INGEST-006.2: If a document is classified as UNRECOGNIZED_DOCUMENT, the system shall reject the file, skip database insertion, and report the rejection in the ingestion summary.
- AC-INGEST-006.3: If an extracted invoice or statement explicitly references a property address or postcode that does not match the configured property, the system shall flag it as PROPERTY_MISMATCH and skip insertion by default.
- AC-INGEST-006.4: Where a document is classified as COMPLIANCE_CERTIFICATE, the system shall skip financial ledger insertion and report it for compliance certificate indexing.

## INGEST-007: Degradation Resilience & Scanned PDF Handling

When an ingested PDF file contains unreadable streams, no extractable text, or password protection, the system shall catch the condition gracefully and report an actionable diagnostic without halting batch execution.

Acceptance Criteria:
- AC-INGEST-007.1: If a PDF file yields fewer than 40 characters of extractable text, the system shall classify it as SCANNED_IMAGE_PDF and prompt the user that OCR or manual entry is required.
- AC-INGEST-007.2: If a PDF file is encrypted or password-protected, the system shall report it as ENCRYPTED_PDF and skip processing.
- AC-INGEST-007.3: If a statement reports deductions exceeding gross rental income resulting in a negative landlord payout, the system shall record the negative balance deterministically without failing mathematical reconciliation.

## INGEST-008: Live Ingestion Progress Indicator & Processing Status Tickets

When a batch of PDF documents or a single document is processed for ingestion, the system shall render a visible progress indicator and output individual processing status tickets marking progress and outcome alongside the file name.

Acceptance Criteria:
- AC-INGEST-008.1: In batch ingestion mode, the system shall display a progress indicator reflecting current file index, total file count, percentage completed, and current file name.
- AC-INGEST-008.2: For each document processed, the system shall emit an immediate processing status ticket displaying the file name, document classification tag, outcome status (ingested, duplicate, rejected, or error), and elapsed processing duration.
- AC-INGEST-008.3: If a document fails, is skipped as a duplicate, or is rejected due to scope mismatch, the status ticket shall include an explicit diagnostic reason.

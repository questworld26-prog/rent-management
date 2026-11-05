# Release Plan & Version Roadmap

## Release Strategy
- **Versioning**: Semantic Versioning (`MAJOR.MINOR.PATCH`).
- **Human-in-the-Loop Approval**: **Always ask the user for explicit confirmation before releasing any MAJOR or MINOR versions.**
- **Architectural Compliance (ADRs)**: Every release candidate must pass automated and manual checks against project ADRs ([ADR.md](ADR.md)):
  - *ADR-001*: Strict EARS specification traceability with normalized block hashing.
  - *ADR-002*: Absolute offline data privacy (zero external cloud API calls, local host endpoints only).
  - *ADR-003*: Pure deterministic mathematics via Python `Decimal` with penny precision.
  - *Path Standards*: Strict relative paths across all markdown documentation (zero machine-specific absolute paths).
  - *Domain Constraints*: Single-property layout (no address headers, no equity tracking or displays).
- **Two-Axis Senior Code Review**: Prior to release tagging, changes since the prior release are audited across two axes:
  - *Axis 1 (Spec & Goal Compliance)*: Traceable EARS requirements, edge cases, error state handling, regression prevention.
  - *Axis 2 (Engineering Standards & Health)*: Type annotations (PEP 585/604), clean error handling without raw traceback leaks, anti-mirage test assertions, and zero lint warnings.
- **Spec-Driven Governance**: No milestone is considered complete without a clean, passing **Spec Guardian audit report** (`uv run python -m tools.guardian audit --strict`) confirming that 100% of acceptance criteria have passing tests and zero spec hash drift.
- **Pre-Release Hygiene**: Always run `/python-lint-format` (`uv run ruff check --fix .` and `uv run ruff format .`) before committing and making any release.
- **Automated 6-Gate Release Pipeline**:
  1. Git working tree validation
  2. Architectural Compliance & Code Review Audit
  3. Spec Guardian strict audit (`uv run python -m tools.guardian audit --strict`)
  4. Full Python test suite (`uv run pytest`)
  5. Code hygiene and formatting (`uv run ruff check --fix .` and `uv run ruff format .`)
  6. Version bumping in `pyproject.toml` and creation of annotated Git release tag (`vX.Y.Z`).
- **Environment Management**: Fully managed via `uv` for reproducible local Python execution.

---

## Roadmap & Milestones (Latest at Top)

### Release `v1.3.0`: Spec-Driven Development Modernization, 4-Layer AST Verification & Reverse Traceability
- **Status**: ✅ RELEASED *(Approved by user)*
- **Focus**: Spec-Driven Development (SDD) & Airtight Two-Way Verification modernization, Spec Guardian 4-layer AST semantic validation, reverse traceability enforcement, `[PLANNED]` roadmap lifecycle management, and test unstacking to strict 1-test-to-1-AC cardinality.
- **Deliverables**:
  - [x] **Spec Guardian Modernization**: Upgraded project-local `tools/guardian` package with full AST parsing, reverse feature-creep checking, 4-layer semantic validation (1-Test-to-1-AC, call-graph symbol verification, anti-mirage assertion inspection, backtick anchor verification), monotonic regression ratchet, and normalized SHA-256 requirement block hashing ([tools/guardian/](tools/guardian/)).
  - [x] **Airtight Reverse Traceability**: Annotated all public domain classes and utility functions in `src/` with explicit `# [spec: REQ-ID]` annotations, eliminating feature-creep and achieving 100% reverse binding ([src/](src/)).
  - [x] **Strict 1-Test-to-1-AC Cardinality**: Unstacked multi-criterion test functions in batch ingestion and issues maintenance into isolated, deterministic test functions each verifying exactly one acceptance criterion ([tests/test_batch_ingestion.py](tests/test_batch_ingestion.py), [tests/test_issues_maintenance.py](tests/test_issues_maintenance.py)).
  - [x] **Roadmap Lifecycle Management**: Formalized future roadmap specifications with `[PLANNED]` tags (`TAX-001` UK Tax Year Aggregation in [specs/finance/tax_year.md](specs/finance/tax_year.md) and `TENANT-001` Tenancy Period Configuration in [specs/tenants/tenant_management.md](specs/tenants/tenant_management.md)).
  - [x] **Developer Tooling Test Isolation**: Relocated guardian tool unit tests to [tools/tests/test_guardian.py](tools/tests/test_guardian.py) and configured multi-root testpaths in [pyproject.toml](pyproject.toml), keeping `tests/` dedicated to application requirement specifications.
- **Exit Criteria**: 100% active criteria verified (73/73 across 19 active specs), 0 untested ACs, 0 orphan tags, 0 hash drift, 90/90 passing pytest suite, clean ruff lint & format.

---

### Release `v1.2.2`: Small-Model Ingestion Resilience, Multi-Statement Calendar Amortization & Date Normalization
- **Status**: ✅ RELEASED *(Approved by user)*
- **Focus**: Elimination of few-shot example bias in small Ollama models, deterministic payment-to-landlord fallback, contractor invoice date normalization to DD/MM/YYYY, single monthly mortgage amortization for multi-statement calendar months, and aggregated Current Month KPI reporting.
- **Deliverables**:
  - [x] **INGEST-001 / Small Model Prompt Optimization**: Stripped concrete numerical examples from JSON extraction schemas to eliminate few-shot memorization/bias in small local models (`llama3.2:3b`, `qwen2.5:3b`); added deterministic regex extraction fallback from `Payment to Landlord` document lines ([src/ingestion/extractor.py](src/ingestion/extractor.py)).
  - [x] **INGEST-001 & UI-002 / DD/MM/YYYY Invoice Date Normalization**: Implemented robust date normalization handling natural text dates, ordinal dates, and ISO dates into uniform `DD/MM/YYYY` format across extraction, SQLite persistence, and UI ledger rendering, with an auto-migration for existing records ([src/ingestion/extractor.py](src/ingestion/extractor.py), [src/storage/database.py](src/storage/database.py), [src/ui/components.py](src/ui/components.py)).
  - [x] **MORT-001 / Calendar-Month Mortgage Amortization**: Fixed multi-statement mortgage deductions by ensuring mortgage debit (£1,997.00) and loan amortization occur strictly once per calendar month, keeping secondary adjustment statements at £0.00 debit and matching actual bank balance ([src/ingestion/batch.py](src/ingestion/batch.py), [src/storage/database.py](src/storage/database.py)).
  - [x] **UI-003 / Current Month Multi-Statement Aggregation**: Enhanced `get_kpi_summary()` and the "Current Month" financial performance card to aggregate rent, expenses, and net payout across all statements occurring in the active calendar month with accurate single-debit shortfall computation ([src/storage/database.py](src/storage/database.py), [src/ui/components.py](src/ui/components.py)).
- **Exit Criteria**: 100% active criteria verified in Spec Guardian (73/73), 87/87 pytest pass, zero architectural violations.

---

### Release `v1.2.0`: Compliance Certificates, Statement Editing & Ledger Consolidation
- **Status**: ✅ RELEASED *(Approved by user)*
- **Focus**: Statutory compliance certificate register, statement editing in popup modal, single & batch PDF ingestion with live progress, and multi-statement month consolidation in the ledger.
- **Deliverables**:
  - [x] **COMP-001**: Statutory Landlord Compliance & Certificates register (CP12 Gas Safety, EICR, EPC, Insurance, Boiler Service, and Custom certificates) with manual entry and dynamic expiry alerting ([src/domain/compliance.py](src/domain/compliance.py)).
  - [x] **UI-001 / Statement Editing**: Interactive editing dialog for monthly statement numbers, dates, gross income, payout, and itemized deductions directly from popup cards ([src/ui/app.py](src/ui/app.py)).
  - [x] **UI-001 / Multi-Statement Consolidation**: Grouped calendar month rows displaying combined financials with statement badge pills and interactive sub-tabs in breakdown modal ([src/ui/components.py](src/ui/components.py)).
  - [x] **INGEST-003 / 3-Attempt Mathematical Reconciliation**: Pure Python pre-persistence validation ensuring income sums to subtotal, deductions sum to subtotal, and payout matches income minus expenditure, with automatic 3-attempt rescan fallback and robust zero-subtotal safeguards ([src/ingestion/reconciler.py](src/ingestion/reconciler.py), [src/ingestion/extractor.py](src/ingestion/extractor.py)).
  - [x] **INGEST-008 / Single & Folder Ingestion**: Live progress bar and completion feedback redirecting directly to statement/invoice ledger tabs upon ingestion completion.
- **Exit Criteria**: 100% active criteria verified in Spec Guardian (73/73), 84/84 pytest pass, zero architectural violations.

---

### Release `v1.1.0`: Quiet Luxury Design System & Luminous Chart Visualizations
- **Status**: ✅ RELEASED *(Approved by user)*
- **Focus**: Unified Quiet Luxury palette overhaul, luminous CSS gradient bar charts, amortisation mechanics, and clean portfolio metrics.
- **Deliverables**:
  - [x] **UI-003**: Unified Quiet Luxury aesthetic (#0E1015 obsidian surfaces, #E5C07B champagne gold accents, #86EFAC soft mint earnings, and #9F1239 warm burgundy shortfall indicators) without theme dropdown switcher ([src/ui/theme.py](src/ui/theme.py)).
  - [x] **Luminous Bar Charts**: Pure CSS/HTML flex charts replacing Mini-Charts with dual-gradient luminous bars for Rent, Deductions, and Net Earning.
  - [x] **Mortgage Amortisation Breakdown**: Cumulative interest paid to date positioned alongside initial principal; loan payoff split progress bar detailing UK capital repayment funding sources.
  - [x] **Portfolio Cumulative Summary**: Clean 4-card metric layout (Gross Rent, Expenses, Earning, Shortfall) with dual-segmented split progress bar.
  - [x] **Absolute Privacy Hardening**: Replaced external Google Fonts imports with local system typography stacks for 100% offline compliance.
- **Exit Criteria**: 100% active criteria verified in Spec Guardian (50/50), 34/34 pytest pass, zero architectural violations.

---

### Release `v1.0.0`: Production Milestone — Executive NiceGUI Dashboard
- **Status**: ✅ RELEASED *(Approved by user)*
- **Focus**: Pure Python NiceGUI single-property executive dashboard with live SQLite telemetry, statement popups, and financial trend charts.
- **Deliverables**:
  - [x] **UI-001**: Monthly statement ledger with sorting, enlarged itemized expenditure dialogs, and interactive continuous trend charts ([src/ui/app.py](src/ui/app.py)).
  - [x] **UI-002**: Contractor invoices table with cross-referencing to letting agency deductions.
  - [x] **UI-003**: Executive HUD layout with loan payoff progress bar, month-by-month cashflow tracking, and in-place folder batch ingestion.
  - [x] **Dashboard CLI**: Interactive launcher ([tools/dashboard.py](tools/dashboard.py)) binding directly to local SQLite storage.
- **Exit Criteria**: 100% active criteria verified (50/50 in Spec Guardian), 34/34 pytest pass, zero external network calls.

---

### Release `v0.7.0`: Batch Document Ingestion, Classification & Resilient Ingestion
- **Status**: ✅ RELEASED *(Approved by user)*
- **Focus**: Multi-file batch document processing, automated statement/invoice classification, graceful degradation, and live CLI progress.
- **Deliverables**:
  - [x] **INGEST-004**: Directory scanning and batch ingestion pipeline ([src/ingestion/batch.py](src/ingestion/batch.py)).
  - [x] **INGEST-005**: Rule-based document classifier ([src/ingestion/classifier.py](src/ingestion/classifier.py)) distinguishing letting statements from contractor invoices.
  - [x] **INGEST-006**: Graceful degradation on extraction discrepancies with detailed error tracking and SQLite failure logging.
  - [x] **CLI Progress Bar**: Real-time batch ingestion progress bar and report summary ([tools/ingest.py](tools/ingest.py)).
- **Exit Criteria**: All ingestion test suites passing (33/33 tests); batch processing verified against sample resources.

---

### Release `v0.6.0`: Monthly Cashflow, Mortgage Ledger & Four-Pillar Governance
- **Status**: ✅ RELEASED *(Approved by user)*
- **Focus**: End-to-end cashflow calculations, mortgage balance ledger, project configuration, and Four-Pillar quality review.
- **Deliverables**:
  - [x] **CASH-001**: Monthly landlord out-of-pocket shortfall calculation engine and CLI tool ([tools/cashflow.py](tools/cashflow.py)).
  - [x] **MORT-001**: Configurable mortgage terms, deal baseline tracking, and loan payoff progress bar with strict `DD-MM-YYYY` dates (zero equity display).
  - [x] **CONFIG-001**: Centralized configuration management ([src/config.py](src/config.py)) using [config.toml](config.example.toml) with [config.example.toml](config.example.toml) template.
  - [x] **SQLite Persistence**: Local database ([src/storage/database.py](src/storage/database.py)) for monthly statements, mortgage direct debits, and loan balance tracking with Level-1 & Level-2 duplicate detection.
  - [x] **Four-Pillar Quality Governance**: Dedicated review skill ([.agents/skills/rent-dashboard-review/SKILL.md](.agents/skills/rent-dashboard-review/SKILL.md)) and automated 6-gate release manager ([tools/release_manager.py](tools/release_manager.py)).
  - [x] **Privacy Hardening**: Git exclusion of sensitive statement PDFs, database files, and private user configuration.
  - [x] **ADR Updates**: Added `ADR-005` (Project Configuration & Loan Ledger) and aligned `ADR-002`/`ADR-004` with single-property and privacy principles.
- **Exit Criteria**: 100% active criteria verified (21/21 in Spec Guardian), 28/28 pytest pass, zero architectural violations.

---

### Release `v0.5.0`: Ingestion CLI & Documentation Guide
- **Status**: ✅ RELEASED *(Approved by user)*
- **Focus**: User-facing document ingestion tool and comprehensive verification documentation.
- **Deliverables**:
  - [x] Offline PDF ingestion CLI tool ([tools/ingest.py](tools/ingest.py)) supporting statements and invoices via local Ollama.
  - [x] Auto-detection of document types and real-time penny-exact mathematical reconciliation.
  - [x] Updated [README.md](README.md) with complete instructions for running ingestion and Spec Guardian validations.
- **Exit Criteria**: `tools.ingest` successfully executes against real statement and invoice PDFs in `Resources/`; full test suite passes.

---

### Release `v0.4.0`: Automated Release Workflow & Focused Spec Guardian
- **Status**: ✅ RELEASED *(All changes after v0.3.0 consolidated)*
- **Focus**: Standardized 5-gate release governance and noise-free Spec Guardian auditing.
- **Deliverables**:
  - [x] Automated 5-gate release manager CLI ([tools/release_manager.py](tools/release_manager.py)).
  - [x] Noise-free Focused Active Audit in [tools/guardian/auditor.py](tools/guardian/auditor.py) (default shows active specs, `--all` shows full roadmap).
  - [x] Integrated Ruff linting and formatting standards (`pyproject.toml`, `/python-lint-format`).
  - [x] Documented release protocol in [AGENTS.md](AGENTS.md).
- **Exit Criteria**: Release manager enforces strict audit, pytest, and ruff before creating annotated Git tags.

---

### Release `v0.3.0`: Milestone 2 — Offline PDF Ingestion & Duplicate Detection
- **Status**: ✅ RELEASED
- **Focus**: Completely private, local document processing.
- **Deliverables**:
  - [x] PDF text extraction using `pdfplumber` (`src/ingestion/pdf_reader.py`).
  - [x] Local Ollama client (`src/ingestion/extractor.py`) interfacing with `localhost:11434` using structured Pydantic JSON schemas (`INGEST-001`).
  - [x] Two-level duplicate detection engine (`src/ingestion/duplicate_checker.py`): file byte SHA-256 + statement number/date check (`INGEST-002`).
  - [x] Deterministic mathematical reconciliation check (`Gross - Expenditures == Net Payout`) to the penny (`INGEST-003`).
  - [x] Integration tests verifying extraction accuracy against sample documents in `Resources/`.
- **Exit Criteria**: Statements and invoices in `Resources/` parse into SQLite with 100% mathematical balance; duplicates are caught and flagged.

---

### Milestone 0: Spec-Driven Infrastructure & Tooling (`v0.1.0`)
- **Status**: ✅ RELEASED
- **Focus**: Setting up the project skeleton, EARS specifications, and the automated verification engine.
- **Deliverables**:
  - [x] Architecture Decision Records ([ADR.md](ADR.md)) and Release Plan ([release.md](release.md)).
  - [x] EARS specification files in `specs/` covering all modules (`ingestion/`, `finance/`, `operations/`, `tenants/`).
  - [x] Developer & agent protocol guide ([AGENTS.md](AGENTS.md)).
  - [x] Spec Guardian CLI engine (`tools/guardian/`) that parses EARS blocks, computes normalized SHA-256 hashes, scans code/test tags, and writes `specs/traceability.json`.
  - [x] Python environment configuration via `uv`.
- **Exit Criteria**: Spec Guardian runs cleanly and generates initial traceability baseline.

# Architecture Decision Records (ADR)

## Status Legend
- **PROPOSED**: Under review
- **ACCEPTED**: Decided and active
- **SUPERSEDED**: Replaced by a newer ADR

---

## ADR-001: Spec-Driven Development (SDD) with EARS & SHA-256 Block Hashing
- **Status**: ACCEPTED
- **Date**: 2026-10-17
- **Context**:
  The user requires strict traceability between requirements, code implementations, and automated test cases. The system must prevent spec drift, ensure every acceptance criterion has test coverage, and enable an automated agent to audit completion and violations periodically.
- **Decision**:
  1. All requirements are written in **Easy Approach to Requirements Syntax (EARS)** across modular Markdown files in `specs/`.
  2. Each requirement block (`## [REQ-ID]: [Title]`) is normalized (line endings normalized to `\n`, whitespace trimmed) and fingerprinted via SHA-256 (`requirement_sha256`).
  3. Code in `src/` annotates requirement IDs via docstrings/comments: `# [spec: REQ-ID]`.
  4. Tests in `tests/` annotate individual acceptance criteria: `# [verifies: REQ-ID/AC-ID]`.
  5. A two-tier **Spec Guardian** engine (`tools/guardian/`) verifies spec-to-code integrity via CLI (`python -m tools.guardian audit`) and Git pre-commit hooks, producing `specs/traceability.json`.
- **Consequences**:
  - Positive: Complete visibility into test coverage per criterion; zero undocumented features; automatic detection of spec drift.
  - Negative: Minor developer discipline required to annotate code and test functions.

---

## ADR-002: Local-First Privacy Architecture via Ollama and SQLite
- **Status**: ACCEPTED
- **Date**: 2026-10-17
- **Context**:
  Privacy of financial statements, invoices, tenant data, and mortgage contracts is paramount. Cloud LLM APIs expose sensitive personal data to third parties.
- **Decision**:
  1. The application operates 100% offline.
  2. PDF document extraction utilizes local `pdfplumber` and a local Ollama instance (`localhost:11434`, e.g., `llama3.2:3b`).
  3. Data persistence uses a single local SQLite database file (`data/rent_dashboard.db`).
  4. Zero network requests are made outside the local host.
  5. Sensitive financial documents (`Resources/`), database files (`data/`), and live user configuration (`config.toml`) are excluded from Git tracking via `.gitignore`.
- **Consequences**:
  - Positive: Total data ownership and privacy; zero API subscription costs; runs without internet connection.
  - Negative: Requires local Ollama running on Mac for automated extraction (with manual entry fallback if Ollama is paused).

---

## ADR-003: Deterministic Financial Mathematics via Python Decimal
- **Status**: ACCEPTED
- **Date**: 2026-10-17
- **Context**:
  LLMs are prone to arithmetic hallucinations, and IEEE-754 floating-point arithmetic (`float`) causes rounding errors in financial computations.
- **Decision**:
  1. Local LLMs are strictly confined to text extraction and field mapping.
  2. All calculations (out-of-pocket shortfall, gross-to-net deductions, mortgage amortization, tax summaries) are computed deterministically in pure Python domain modules (`src/domain/`) using `decimal.Decimal`.
  3. An automatic reconciliation check (`gross_rent - total_expenditure == net_payout`) is enforced to the penny before saving imported statements.
- **Consequences**:
  - Positive: 100% mathematical precision; verifiable audit trail; eliminates financial calculation bugs.
  - Negative: String/float inputs must always be cast explicitly to `Decimal`.

---

## ADR-004: Python-Centric Executive UI (NiceGUI) with Multi-Theme Support
- **Status**: ACCEPTED
- **Date**: 2026-10-17
- **Context**:
  The user is the sole developer and finds financial reviews stressful. The interface must be calm, professional, high-contrast, and free of screen-flicker or jarring page reloads, without introducing Node.js/npm dependencies.
- **Decision**:
  1. Build the dashboard in Python using **NiceGUI** (powered by Quasar/Vue3 and Tailwind under the hood).
  2. Implement an executive single-property layout without an address header, featuring top navigation tabs, a prominent glowing pill-style mortgage loan payoff progress bar (displaying loan reduction, remaining balance, and days remaining without equity tracking), four KPI metric cards, an interactive cashflow area chart, and a side issues board with pinned invoices and flashing compliance alert pills.
  3. Support a top-bar **Theme Switcher** featuring:
     - **Nordic Aurora** (Emerald & Cyan glow on deep obsidian — default favorite)
     - **Vibrant Multi-Color** (Color-coded metric cards: Cyan, Amber, Emerald, Coral)
     - **Midnight Sapphire** (Cobalt & Ice Blue)
     - **Titanium & Warm Gold** (Champagne Gold & Soft Mint)
- **Consequences**:
  - Positive: 100% Python codebase; fluid single-page app UX; zero npm setup; soothing, executive visual aesthetic.
  - Negative: Relies on NiceGUI component ecosystem.

---

## ADR-005: Project-Wide Configuration & Monthly Loan Balance Ledger
- **Status**: ACCEPTED
- **Date**: 2026-10-17
- **Context**:
  Mortgage deal terms, local Ollama endpoints, and document parsing options must be configurable without hardcoding constants in CLI tool source code. Furthermore, the mortgage loan principal reduces each month as direct debits are paid.
- **Decision**:
  1. Store static baseline configuration (Ollama model and endpoint, mortgage interest rate, direct debit, deal end date, effective start date, and baseline principal) in root `config.toml`, with a version-controlled template in `config.example.toml`.
  2. Maintain changing loan balances over time inside local SQLite (`data/rent_dashboard.db`) alongside ingested monthly rental statements.
  3. When generating dashboard metrics or mortgage progress bars, query the latest recorded balance from SQLite, falling back to `initial_principal` from `config.toml` only when no statement records have been persisted yet.
  4. Never track, calculate, or display property equity.
- **Consequences**:
  - Positive: Zero hardcoded fallback figures in Python tools; dynamic balance reduction over time; clean separation between code and private user configuration.
  - Negative: Requires `config.toml` to be present at runtime (or created from `config.example.toml`).

---

## Note: Business & Domain Specifications
Domain requirements and business logic (formerly draft entries for UK tax year reporting and tenancy attribution) are governed strictly by formal EARS specifications in `specs/`:
- **UK Tax Year Reporting & Section 24 Mortgage Segregation**: Governed by `TAX-001` in [specs/finance/tax_year.md](specs/finance/tax_year.md) and `MORT-002` in [specs/finance/mortgage.md](specs/finance/mortgage.md).
- **Tenancy Date-Window Attribution Model**: Governed by `TENANT-001` in [specs/tenants/tenant_management.md](specs/tenants/tenant_management.md).

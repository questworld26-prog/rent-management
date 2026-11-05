# Agent Operating Guidelines & Spec Guardian Protocols

This document defines the rules of engagement, engineering constraints, and verification protocols for any AI agent working on the **Rent Management Dashboard** codebase.

---

## 1. Prime Directives

1. **Spec-First Rule**: NEVER write implementation code or test cases without an approved EARS specification in `specs/`. All code and tests must explicitly trace to an active requirement.
2. **Absolute Data Privacy**: NEVER make outbound network calls or send financial statements, invoices, or tenant details to external cloud APIs. All extraction is done locally via Ollama (`localhost:11434`), and all data is stored in the local SQLite database (`data/rent_dashboard.db`).
3. **Deterministic Mathematics**: NEVER use LLMs to perform arithmetic or calculate financial balances. LLMs are strictly confined to unstructured document parsing. All totals, deductions, mortgage shortfalls, and tax figures must be calculated in Python using `decimal.Decimal`.
4. **Tool Execution via `uv`**: Always execute Python scripts, tests, and CLI commands using `uv` (e.g. `uv run pytest`, `uv run python -m tools.guardian audit`).
5. **No Done Without Guardian Audit**: An agent must NEVER mark a feature or milestone as completed without running `uv run python -m tools.guardian audit --strict` and verifying zero spec violations, zero hash drift, and 100% test coverage for all acceptance criteria.

---

## 2. Spec-Driven Development (SDD) Conventions

### 2.1 EARS Syntax in `specs/`
All requirements must use standard **Easy Approach to Requirements Syntax (EARS)** patterns:
- **Ubiquitous**: *The system shall [response]*
- **Event-driven**: *When [trigger], the system shall [response]*
- **State-driven**: *While [state], the system shall [response]*
- **Unwanted behaviour**: *If [condition], then the system shall [response]*
- **Optional feature**: *Where [feature flag/setting], the system shall [response]*

Each requirement must have:
- A unique ID heading: `## [REQ-ID]: [Title]` (e.g., `## CASH-001: Monthly Mortgage Excess Calculation`)
- A concise EARS statement.
- An explicit list of numbered Acceptance Criteria:
  ```markdown
  Acceptance Criteria:
  - AC-[REQ-ID].1: [Criterion 1]
  - AC-[REQ-ID].2: [Criterion 2]
  ```

### 2.2 SHA-256 Requirement Block Hashing
- The Spec Guardian computes a SHA-256 hash for each requirement block (`## [REQ-ID]:` up to the next `##` heading or EOF).
- Line endings are normalized to `\n`, leading/trailing whitespace on lines trimmed, and trailing blank lines stripped.
- If a requirement's text or criteria change, its `requirement_sha256` changes, immediately flagging mapped implementations and tests as unverified until reviewed and updated.

### 2.3 Code & Test Annotation Rules
- **Implementation files (`src/`)**: Annotate functions or classes with the requirement ID:
  ```python
  # [spec: CASH-001]
  def calculate_monthly_shortfall(net_rent: Decimal, mortgage_due: Decimal) -> CashflowResult: ...
  ```
- **Test files (`tests/`)**: Annotate test functions with the exact requirement and acceptance criterion ID:
  ```python
  # [verifies: CASH-001/AC-CASH-001.1]
  def test_shortfall_when_net_rent_is_insufficient(): ...
  ```

---

## 3. Spec Guardian Commands

Agents must use the following commands during development:
- **Run Audit**:
  ```bash
  uv run python -m tools.guardian audit
  ```
  Validates all spec hashes against implementations and tests, reports any missing coverage or drift, and updates `specs/traceability.json`.
- **Run Strict Audit (Pre-Commit / Gatekeeper)**:
  ```bash
  uv run python -m tools.guardian audit --strict
  ```
  Exits with code `1` if any acceptance criterion lacks a test, any requirement lacks an implementation, or any spec hash is dirty.
- **Generate Spec Report**:
  ```bash
  uv run python -m tools.guardian report
  ```
  Outputs a markdown table showing the current verification matrix.

---

## 4. Release Workflow & Tagging

Releases are executed through the automated 6-gate release manager:
- **List Releases**:
  ```bash
  uv run python -m tools.release_manager list
  # Or: git tag -n --sort=v:refname
  ```
- **Create Release** *(Always request user permission before Major/Minor)*:
  ```bash
  uv run python -m tools.release_manager create <VERSION> -m "<SUMMARY>"
  ```
  This command automatically runs:
  1. Git working tree validation
  2. Architectural Compliance & Code Review Audit (ADRs, privacy, relative paths, diff review)
  3. Spec Guardian strict audit (`--strict`)
  4. Pytest test suite (`pytest`)
  5. Code hygiene and formatting (`ruff check --fix` and `ruff format`)
  6. Version synchronization in `pyproject.toml` and creation of annotated Git tag `v<VERSION>`


---

## 5. UI/UX Principles for Code Generation

- The dashboard is built with **NiceGUI** (pure Python, rendering Quasar/Vue3 and Tailwind).
- Maintain the single-property executive layout (no property address header).
- Support the 4 built-in themes in the top-bar Theme Switcher:
  1. `Nordic Aurora` (Emerald & Cyan glow on deep charcoal — default)
  2. `Vibrant Multi-Color` (Color-coded KPI badges: Cyan, Amber, Emerald, Coral)
  3. `Midnight Sapphire` (Cobalt & Ice Blue)
  4. `Titanium & Warm Gold` (Champagne Gold & Soft Mint)
- Avoid jarring page reloads or full-script reruns. Update reactive components in-place.

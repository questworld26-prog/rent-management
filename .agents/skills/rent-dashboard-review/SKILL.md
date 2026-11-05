---
name: rent-dashboard-review
description: >-
  Independent Code Review and Architecture Quality Assurance skill for the Rent Management Dashboard project.
  Enforces ADR compliance, offline data privacy, deterministic decimal mathematics, spec traceability,
  zero hardcoded parameters, SQLite integrity, and anti-mirage test assertions.
---

# Senior Code Review & Architecture QA: Rent Management Dashboard

This skill defines the independent review protocol for changes, pull requests, and releases across the **Rent Management Dashboard** codebase.

---

## The Four-Pillar Review Rubric

Every code review must assess the proposed changes against four non-negotiable project pillars:

### Pillar 1: Absolute Data Privacy & Local-Only Boundary (ADR-002)
- **Zero External Network Calls**: Ensure no HTTP/HTTPS requests target any host other than local host (`127.0.0.1` or `localhost:11434`).
- **Data Protection in Git**: Verify that sensitive financial documents (`Resources/*.pdf`), local database files (`data/*.db`), and live user configuration (`config.toml`) are never committed or staged in Git.
- **Log Sanitation**: Verify that tenant names, bank account numbers, or raw tracebacks are never exposed in user-facing CLI outputs or persistent logs.

### Pillar 2: Deterministic Mathematics & Untrusted LLM Boundary (ADR-003)
- **Strict Decimal Arithmetic**: Verify that all arithmetic (payouts, shortfall, principal reductions, fees, VAT, tax aggregations) uses Python `decimal.Decimal`.
- **Zero Float Conversions**: Reject any `float` calculations in `src/domain/` or financial modules.
- **LLM Boundary Isolation**: Local LLMs (Ollama) are strictly confined to unstructured document parsing. Never allow LLM outputs to calculate arithmetic.
- **Penny-Exact Reconciliation**: Enforce `gross_income - total_expenditure == net_payout` verification before saving rental statements.

### Pillar 3: Spec-Driven Traceability & Configuration Hygiene (ADR-001, ADR-005)
- **EARS Spec Traceability**: Every implementation function/class in `src/` must tag `# [spec: REQ-ID]`. Every test in `tests/` must tag `# [verifies: REQ-ID/AC-ID]`.
- **No Spec Hash Drift**: Deliberate spec changes must be explicitly validated and audited via `tools.guardian audit --strict`.
- **Zero Hardcoded Parameters**: Operational constants, interest rates, mortgage debits, model tags, and valuation figures must be read from `config.toml` (or CLI overrides). Silent `except Exception` fallbacks to hardcoded money values are strictly rejected.
- **Domain Constraints**: Maintain single-property layout. **Never track, calculate, or display property equity**.

### Pillar 4: Engineering Health & Anti-Mirage Test Fidelity
- **Clean Code & Function Readability**: Reject bloated functions and overly long monolithic methods (e.g. methods exceeding ~40 lines). Code must be decomposed into small, single-responsibility, highly readable functions with clean parameter passing.
- **Anti-Mirage Assertions**: Reject vacuous assertions (e.g. `assert result is not None`, `assert value > 0`). Demand deterministic numeric and factual anchors.
- **Test Isolation**: Tests must never depend on the presence or contents of live user files (`config.toml`, user statements). Use temporary fixtures (`tmp_path`) or `config.example.toml`.
- **Clean Relative Paths**: All documentation links must use relative Markdown paths (e.g. `[README.md](README.md)`). Reject any machine-specific paths (e.g. `/Users/`, `/home/`, `file:///Users/`).
- **Idempotent Ingestion**: Ingestion tools must enforce Level-1 (file hash) and Level-2 (statement/invoice semantic) duplicate detection before inserting into SQLite.


---

## Review Output Format

Reviews must produce a structured report in `reviews/review_<VERSION_OR_DIFF>.md`:

```markdown
# Code Review Report: [Title / Version]
Date: [YYYY-MM-DD]
Reviewer: [Independent Reviewer Model / Agent]

## 1. Executive Summary
- **Result**: [PASS | ACTION_REQUIRED | BLOCKED]
- **Key Highlights**: ...

## 2. Four-Pillar Assessment
| Pillar | Status | Findings Summary |
| :--- | :--- | :--- |
| 1. Privacy & Local-Only Boundary | [PASS / FAIL] | ... |
| 2. Deterministic Math & LLM Boundary | [PASS / FAIL] | ... |
| 3. Spec Traceability & Config Hygiene | [PASS / FAIL] | ... |
| 4. Engineering Health & Test Fidelity | [PASS / FAIL] | ... |

## 3. Detailed Findings & Recommendations
- **[CRITICAL / HIGH / MEDIUM / LOW]**: [Description, file link, and remediation]

## 4. Release Recommendation
- [Approved for release / Remediation required prior to release]
```

---
name: rent-dashboard-test-protocol
description: >-
  Defines the test execution command, test suite structure, offline privacy constraints,
  and anti-mirage assertion standards for the Rent Management Dashboard project.
  Enforced by [Gate 4] Test Suite Execution in release management.
---

# Test Protocol: Rent Management Dashboard

This local skill defines the testing standards and runner commands for **Rent Management Dashboard**.

---

## 1. Test Command & Execution

Always execute tests within the project virtual environment via `uv`:

```bash
uv run pytest
```

### Targeted Test Runs
```bash
# Ingestion pipeline tests
uv run pytest tests/test_pdf_ingestion.py

# NiceGUI executive dashboard tests
uv run pytest tests/test_executive_ui.py

# Financial & cashflow calculations
uv run pytest tests/test_cashflow.py
```

---

## 2. Core Testing Constraints

1. **Absolute Offline Boundary (ADR-002)**:
   - Tests must NEVER make outbound internet requests.
   - External LLMs or cloud endpoints are strictly forbidden; local Ollama extraction tests must use deterministic mocks or local fixtures.
2. **Deterministic Decimal Arithmetic (ADR-003)**:
   - All financial assertions must verify exact `decimal.Decimal` penny calculations (e.g. `assert balance == Decimal("1997.00")`).
   - Float comparisons or approximate epsilon checks are rejected in domain and financial tests.
3. **Spec Traceability Annotations (ADR-001)**:
   - Every test case must annotate its corresponding acceptance criterion:
     ```python
     # [verifies: CASH-001/AC-CASH-001.1]
     def test_mortgage_shortfall(): ...
     ```
4. **Anti-Mirage Assertions**:
   - Reject vacuous assertions (`assert result is not None`, `assert len(records) > 0`).
   - Assert exact values, status codes, and database state.
5. **Fixture & Database Isolation**:
   - Tests must run against isolated temporary SQLite databases (`tmp_path`) or in-memory SQLite fixtures.
   - Never write to or depend on the contents of the live database (`data/rent_dashboard.db`) or user configuration (`config.toml`).

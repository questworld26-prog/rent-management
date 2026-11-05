# System Configuration Specification

## CONFIG-001: Project Configuration & Parameter Management

The system shall load operational and mortgage deal parameters from a root `config.toml` file (or path specified via `--config`) without relying on hardcoded parameter values.

Acceptance Criteria:
- AC-CONFIG-001.1: The system shall parse `config.toml` containing `[ollama]` settings (`model`, `base_url`) and `[mortgage]` terms (`monthly_direct_debit`, `interest_rate`, `fixed_deal_end_date`, `effective_from`, and `initial_principal`).
- AC-CONFIG-001.2: All dates in `config.toml` shall strictly use the `DD-MM-YYYY` format, and financial figures shall be parsed into Python `Decimal`.
- AC-CONFIG-001.3: If `config.toml` is missing or missing required parameters, the system shall exit with a clear diagnostic message indicating the missing keys.
- AC-CONFIG-001.4: Ingestion and cashflow tools shall load settings from `config.toml`, allowing explicit CLI flags to serve strictly as optional overrides.

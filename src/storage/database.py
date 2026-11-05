"""Local SQLite persistence for rental statements, mortgage records, and contractor invoices."""

import sqlite3
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any

from src.domain.models import ContractorInvoice, RentalStatement
from src.ingestion.extractor import normalize_date_to_dmy

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "rent_dashboard.db"


# [spec: UI-001]
def parse_date_sort_key(date_str: str) -> tuple[int, int, int]:
    """Parse date string (DD/MM/YYYY, DD-MM-YYYY, YYYY-MM-DD) into (YYYY, MM, DD) tuple."""
    if not date_str:
        return (0, 0, 0)
    cleaned = date_str.strip().replace("-", "/")
    parts = cleaned.split("/")
    if len(parts) == 3:
        try:
            if len(parts[0]) == 4:  # YYYY/MM/DD
                return (int(parts[0]), int(parts[1]), int(parts[2]))
            else:  # DD/MM/YYYY
                return (int(parts[2]), int(parts[1]), int(parts[0]))
        except ValueError:
            pass
    return (0, 0, 0)


class Database:
    """SQLite database manager for local offline financial storage."""

    def __init__(self, db_path: Path | str | None = None):
        if db_path is None:
            self.db_path = DEFAULT_DB_PATH
        else:
            self.db_path = Path(db_path)
            if not self.db_path.is_absolute():
                self.db_path = PROJECT_ROOT / self.db_path

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_tables()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA busy_timeout = 5000;")
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def _init_tables(self) -> None:
        with self._get_connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS monthly_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    statement_date TEXT NOT NULL,
                    reference TEXT,
                    statement_number TEXT,
                    gross_income TEXT NOT NULL,
                    total_expenditure TEXT NOT NULL,
                    net_payout TEXT NOT NULL,
                    mortgage_debit TEXT NOT NULL,
                    outstanding_balance TEXT NOT NULL,
                    file_hash TEXT UNIQUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS expenditures (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    monthly_record_id INTEGER NOT NULL REFERENCES monthly_records(id) ON DELETE CASCADE,
                    description TEXT NOT NULL,
                    net TEXT NOT NULL,
                    vat TEXT NOT NULL,
                    gross TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS contractor_invoices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    contractor_name TEXT NOT NULL,
                    invoice_date TEXT NOT NULL,
                    invoice_number TEXT NOT NULL,
                    gross_amount TEXT NOT NULL,
                    job_description TEXT,
                    file_hash TEXT UNIQUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_monthly_records_ref_stmt
                    ON monthly_records(reference, statement_number);

                CREATE INDEX IF NOT EXISTS idx_monthly_records_hash
                    ON monthly_records(file_hash);

                CREATE INDEX IF NOT EXISTS idx_contractor_invoices_lookup
                    ON contractor_invoices(contractor_name, invoice_number);

                CREATE INDEX IF NOT EXISTS idx_contractor_invoices_hash
                    ON contractor_invoices(file_hash);

                CREATE INDEX IF NOT EXISTS idx_expenditures_record_id
                    ON expenditures(monthly_record_id);

                CREATE TABLE IF NOT EXISTS maintenance_issues (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT 'General',
                    status TEXT NOT NULL DEFAULT 'Open',
                    priority TEXT NOT NULL DEFAULT 'Normal',
                    contractor_name TEXT,
                    total_cost TEXT NOT NULL DEFAULT '0.00',
                    reported_date TEXT NOT NULL,
                    resolved_date TEXT,
                    resolution_note TEXT,
                    is_suggested INTEGER NOT NULL DEFAULT 0,
                    source_invoice_id INTEGER REFERENCES contractor_invoices(id) ON DELETE SET NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS maintenance_issue_notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    issue_id INTEGER NOT NULL REFERENCES maintenance_issues(id) ON DELETE CASCADE,
                    author TEXT NOT NULL DEFAULT 'Landlord',
                    comment TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS maintenance_issue_invoices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    issue_id INTEGER NOT NULL REFERENCES maintenance_issues(id) ON DELETE CASCADE,
                    invoice_id INTEGER NOT NULL REFERENCES contractor_invoices(id) ON DELETE CASCADE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(issue_id, invoice_id)
                );

                CREATE INDEX IF NOT EXISTS idx_maintenance_issues_status
                    ON maintenance_issues(status);

                CREATE INDEX IF NOT EXISTS idx_maintenance_notes_issue_id
                    ON maintenance_issue_notes(issue_id);

                CREATE INDEX IF NOT EXISTS idx_maintenance_invoices_issue
                    ON maintenance_issue_invoices(issue_id);

                CREATE TABLE IF NOT EXISTS compliance_certificates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    certificate_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    provider TEXT,
                    reference_number TEXT,
                    issue_date TEXT NOT NULL,
                    expiry_date TEXT NOT NULL,
                    cost TEXT NOT NULL DEFAULT '0.00',
                    epc_rating TEXT,
                    file_path TEXT,
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_compliance_certificates_expiry
                    ON compliance_certificates(expiry_date);

                CREATE INDEX IF NOT EXISTS idx_compliance_certificates_type
                    ON compliance_certificates(certificate_type);
                """
            )

            # Auto-migrate existing contractor invoice dates to DD/MM/YYYY format if needed
            cursor = conn.cursor()
            cursor.execute("SELECT id, invoice_date FROM contractor_invoices")
            existing_rows = cursor.fetchall()
            for row in existing_rows:
                old_date = row["invoice_date"]
                normalized = normalize_date_to_dmy(old_date)
                if normalized and normalized != old_date:
                    cursor.execute(
                        "UPDATE contractor_invoices SET invoice_date = ? WHERE id = ?",
                        (normalized, row["id"]),
                    )

            conn.commit()

    # [spec: MORT-001]
    def save_monthly_statement(
        self,
        statement: RentalStatement,
        mortgage_debit: Decimal,
        outstanding_balance: Decimal,
    ) -> int:
        """Save a monthly statement along with its mortgage debit and month-end loan balance."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO monthly_records (
                    statement_date, reference, statement_number,
                    gross_income, total_expenditure, net_payout,
                    mortgage_debit, outstanding_balance, file_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    statement.statement_date,
                    statement.reference,
                    statement.statement_number,
                    str(statement.gross_income),
                    str(statement.total_expenditure),
                    str(statement.net_payout),
                    str(mortgage_debit),
                    str(outstanding_balance),
                    statement.file_hash,
                ),
            )
            record_id = cursor.lastrowid
            if record_id is None:
                raise RuntimeError("Failed to retrieve record_id after inserting monthly_record.")

            for exp in statement.expenditures:
                cursor.execute(
                    """
                    INSERT INTO expenditures (monthly_record_id, description, net, vat, gross)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (record_id, exp.description, str(exp.net), str(exp.vat), str(exp.gross)),
                )
            conn.commit()
            return record_id

    # [spec: INGEST-001]
    def save_contractor_invoice(self, invoice: ContractorInvoice) -> int:
        """Save a contractor invoice to the database, ensuring DD/MM/YYYY date format."""
        normalized_date = normalize_date_to_dmy(invoice.invoice_date)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO contractor_invoices (
                    contractor_name, invoice_date, invoice_number,
                    gross_amount, job_description, file_hash
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    invoice.contractor_name,
                    normalized_date,
                    invoice.invoice_number,
                    str(invoice.gross_amount),
                    invoice.job_description,
                    invoice.file_hash,
                ),
            )
            record_id = cursor.lastrowid
            if record_id is None:
                raise RuntimeError("Failed to retrieve record_id after inserting monthly_record.")
            conn.commit()
            return record_id

    # [spec: MORT-001]
    def get_latest_mortgage_balance(self) -> Decimal | None:
        """Retrieve the most recent outstanding mortgage balance recorded in the database."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT statement_date, statement_number, outstanding_balance FROM monthly_records")
            rows = cursor.fetchall()
            if not rows:
                return None
            sorted_rows = sorted(
                rows,
                key=lambda r: (
                    parse_date_sort_key(r["statement_date"]),
                    int(r["statement_number"]) if str(r["statement_number"]).isdigit() else 0,
                ),
            )
            return Decimal(sorted_rows[-1]["outstanding_balance"])

    # [spec: INGEST-002]
    def has_file_hash(self, file_hash: str) -> bool:
        """Check if a file SHA-256 hash has already been stored."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM monthly_records WHERE file_hash = ?", (file_hash,))
            if cursor.fetchone():
                return True
            cursor.execute("SELECT 1 FROM contractor_invoices WHERE file_hash = ?", (file_hash,))
            return cursor.fetchone() is not None

    # [spec: INGEST-002]
    def has_semantic_statement(self, reference: str, statement_number: str) -> bool:
        """Check if a statement with the given reference and statement number exists."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM monthly_records WHERE reference = ? AND statement_number = ?",
                (reference, statement_number),
            )
            return cursor.fetchone() is not None

    # [spec: INGEST-002]
    def has_statement_in_month(self, statement_date: str) -> bool:
        """Check if any statement has already been recorded in the same calendar month (MM/YYYY)."""
        sort_key = parse_date_sort_key(statement_date)
        if sort_key == (0, 0, 0):
            return False
        year, month = sort_key[0], sort_key[1]
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT statement_date FROM monthly_records")
            rows = cursor.fetchall()
            for r in rows:
                k = parse_date_sort_key(r["statement_date"])
                if (k[0], k[1]) == (year, month):
                    return True
            return False

    # [spec: INGEST-002]
    def get_statement_by_semantic_id(self, reference: str, statement_number: str) -> dict | None:
        """Retrieve statement record by reference and statement number."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM monthly_records WHERE reference = ? AND statement_number = ?",
                (reference, statement_number),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    # [spec: INGEST-002]
    def overwrite_monthly_statement(
        self,
        statement: RentalStatement,
        mortgage_debit: Decimal,
        outstanding_balance: Decimal,
    ) -> int:
        """Atomically replace an existing monthly statement and its expenditures."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Delete existing matching record (cascades to expenditures)
            cursor.execute(
                "DELETE FROM monthly_records WHERE reference = ? AND statement_number = ?",
                (statement.reference, statement.statement_number),
            )
            cursor.execute(
                """
                INSERT INTO monthly_records (
                    statement_date, reference, statement_number,
                    gross_income, total_expenditure, net_payout,
                    mortgage_debit, outstanding_balance, file_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    statement.statement_date,
                    statement.reference,
                    statement.statement_number,
                    str(statement.gross_income),
                    str(statement.total_expenditure),
                    str(statement.net_payout),
                    str(mortgage_debit),
                    str(outstanding_balance),
                    statement.file_hash,
                ),
            )
            record_id = cursor.lastrowid
            if record_id is None:
                raise RuntimeError("Failed to retrieve record_id after inserting monthly_record.")

            for exp in statement.expenditures:
                cursor.execute(
                    """
                    INSERT INTO expenditures (monthly_record_id, description, net, vat, gross)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (record_id, exp.description, str(exp.net), str(exp.vat), str(exp.gross)),
                )
            conn.commit()
            return record_id

    # [spec: INGEST-002]
    def has_semantic_invoice(self, contractor_name: str, invoice_number: str) -> bool:
        """Check if an invoice with identical contractor name and invoice number exists."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM contractor_invoices WHERE contractor_name = ? AND invoice_number = ?",
                (contractor_name, invoice_number),
            )
            return cursor.fetchone() is not None

    # [spec: UI-001]
    def get_all_monthly_statements(self) -> list[dict]:
        """Retrieve all monthly statements ordered chronologically with nested expenditures."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM monthly_records")
            records = [dict(row) for row in cursor.fetchall()]

            cursor.execute(
                "SELECT monthly_record_id, id, description, net, vat, gross FROM expenditures ORDER BY id ASC"
            )
            expenditures_by_record = defaultdict(list)
            for exp in cursor.fetchall():
                exp_dict = dict(exp)
                rec_id = exp_dict.pop("monthly_record_id")
                expenditures_by_record[rec_id].append(exp_dict)

            for rec in records:
                rec["expenditures"] = expenditures_by_record.get(rec["id"], [])

                payout = Decimal(rec["net_payout"])
                debit = Decimal(rec["mortgage_debit"])
                # Calculate shortfall: max(0, debit - payout)
                shortfall = max(Decimal("0.00"), debit - payout)
                surplus = max(Decimal("0.00"), payout - debit)
                rec["calculated_shortfall"] = str(shortfall)
                rec["calculated_surplus"] = str(surplus)

            records.sort(
                key=lambda r: (
                    parse_date_sort_key(r.get("statement_date", "")),
                    int(r.get("statement_number") or 0) if str(r.get("statement_number", "")).isdigit() else 0,
                    r.get("id", 0),
                )
            )
            return records

    # [spec: UI-001]
    def get_monthly_statement_by_id(self, statement_id: int) -> dict | None:
        """Retrieve a specific monthly statement by primary key ID with nested expenditures and calculated cashflows."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM monthly_records WHERE id = ?", (statement_id,))
            row = cursor.fetchone()
            if not row:
                return None
            rec = dict(row)
            cursor.execute(
                "SELECT id, description, net, vat, gross FROM expenditures WHERE monthly_record_id = ? ORDER BY id ASC",
                (rec["id"],),
            )
            rec["expenditures"] = [dict(exp) for exp in cursor.fetchall()]

            payout = Decimal(rec["net_payout"])
            debit = Decimal(rec["mortgage_debit"])
            rec["calculated_shortfall"] = str(max(Decimal("0.00"), debit - payout))
            rec["calculated_surplus"] = str(max(Decimal("0.00"), payout - debit))
            return rec

    # [spec: UI-001]
    def update_monthly_statement(
        self,
        statement_id: int,
        statement_date: str,
        reference: str,
        statement_number: str,
        gross_income: Decimal | str,
        mortgage_debit: Decimal | str,
        expenditures: list[dict[str, Any]],
    ) -> None:
        """Update an existing monthly statement and replace its itemized expenditures atomically.

        Recalculates total_expenditure and net_payout deterministically using Python Decimal.
        """
        gross_dec = Decimal(str(gross_income))
        debit_dec = Decimal(str(mortgage_debit))

        # Calculate expenditures sum deterministically
        total_exp_dec = Decimal("0.00")
        processed_expenditures = []
        for exp in expenditures:
            desc = str(exp.get("description", "")).strip()
            net_val = Decimal(str(exp.get("net", "0.00")))
            vat_val = Decimal(str(exp.get("vat", "0.00")))
            # If gross is missing or zero, gross = net + vat
            gross_val = Decimal(str(exp.get("gross", "0.00")))
            if gross_val == Decimal("0.00") and (net_val > 0 or vat_val > 0):
                gross_val = net_val + vat_val
            total_exp_dec += gross_val
            processed_expenditures.append(
                {
                    "description": desc,
                    "net": str(net_val),
                    "vat": str(vat_val),
                    "gross": str(gross_val),
                }
            )

        net_payout_dec = gross_dec - total_exp_dec

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE monthly_records
                SET statement_date = ?, reference = ?, statement_number = ?,
                    gross_income = ?, total_expenditure = ?, net_payout = ?,
                    mortgage_debit = ?
                WHERE id = ?
                """,
                (
                    statement_date,
                    reference,
                    statement_number,
                    str(gross_dec),
                    str(total_exp_dec),
                    str(net_payout_dec),
                    str(debit_dec),
                    statement_id,
                ),
            )

            # Replace itemized expenditures
            cursor.execute("DELETE FROM expenditures WHERE monthly_record_id = ?", (statement_id,))
            for exp in processed_expenditures:
                cursor.execute(
                    """
                    INSERT INTO expenditures (monthly_record_id, description, net, vat, gross)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (statement_id, exp["description"], exp["net"], exp["vat"], exp["gross"]),
                )
            conn.commit()

    # [spec: UI-002]
    def get_all_contractor_invoices(self) -> list[dict]:
        """Retrieve all contractor invoices with matched status to statement expenditures."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM contractor_invoices ORDER BY id DESC")
            invoices = [dict(row) for row in cursor.fetchall()]

            cursor.execute("SELECT description, gross FROM expenditures")
            expenditure_items = cursor.fetchall()

            for inv in invoices:
                inv_gross = Decimal(inv["gross_amount"])
                matched = False
                for exp in expenditure_items:
                    exp_gross = Decimal(exp["gross"])
                    desc = exp["description"].lower()
                    cname = inv["contractor_name"].lower()
                    inv_no = inv["invoice_number"].lower()
                    if inv_gross == exp_gross and (cname in desc or inv_no in desc):
                        matched = True
                        break
                inv["is_deduction_matched"] = matched

            return invoices

    # [spec: UI-001]
    def get_kpi_summary(self, default_mortgage_debit: Decimal) -> dict:
        """Calculate executive KPI summary figures for the latest calendar month, aggregating multiple statements in the same month."""
        from collections import defaultdict

        statements = self.get_all_monthly_statements()

        if statements:
            # Group statements chronologically by calendar month (YYYY-MM)
            by_month = defaultdict(list)
            for s in statements:
                parts = parse_date_sort_key(s.get("statement_date", ""))
                # (YYYY, MM, DD) -> (YYYY, MM)
                m_key = (parts[0], parts[1])
                by_month[m_key].append(s)

            latest_month_key = sorted(by_month.keys())[-1]
            month_stmts = by_month[latest_month_key]

            # Aggregate figures across all statements in the latest calendar month
            gross_rent = sum((Decimal(s["gross_income"]) for s in month_stmts), Decimal("0.00"))
            total_deductions = sum((Decimal(s["total_expenditure"]) for s in month_stmts), Decimal("0.00"))
            net_payout = sum((Decimal(s["net_payout"]) for s in month_stmts), Decimal("0.00"))

            # Mortgage debit is paid once per calendar month
            # Use positive mortgage debit from the month's statements if present, otherwise default
            nonzero_debits = [
                Decimal(s["mortgage_debit"]) for s in month_stmts if Decimal(s["mortgage_debit"]) > Decimal("0.00")
            ]
            mortgage_debit = nonzero_debits[0] if nonzero_debits else default_mortgage_debit

            shortfall = max(Decimal("0.00"), mortgage_debit - net_payout)
            surplus = max(Decimal("0.00"), net_payout - mortgage_debit)

            latest_stmt = month_stmts[-1]
            latest_date = latest_stmt["statement_date"]

            if len(month_stmts) > 1:
                stmt_numbers = ", #".join(str(s["statement_number"]) for s in month_stmts)
                latest_stmt_no = f"{stmt_numbers} ({len(month_stmts)} statements in {latest_date[3:]})"
            else:
                latest_stmt_no = latest_stmt["statement_number"]
        else:
            gross_rent = Decimal("0.00")
            total_deductions = Decimal("0.00")
            net_payout = Decimal("0.00")
            mortgage_debit = default_mortgage_debit
            shortfall = default_mortgage_debit
            surplus = Decimal("0.00")
            latest_date = "N/A"
            latest_stmt_no = "N/A"

        return {
            "latest_date": latest_date,
            "latest_statement_number": latest_stmt_no,
            "gross_rent": gross_rent,
            "total_deductions": total_deductions,
            "net_payout": net_payout,
            "mortgage_debit": mortgage_debit,
            "shortfall": shortfall,
            "surplus": surplus,
        }

    # [spec: MORT-001]
    def recalculate_statement_balances(
        self,
        initial_principal: Decimal,
        monthly_direct_debit: Decimal,
        interest_rate: Decimal,
    ) -> None:
        """Recalculate and persist amortized balances across all statements grouped by calendar month.

        Ensures mortgage is amortized and debited exactly once per calendar month, even when multiple statements exist.
        """
        from collections import defaultdict

        from src.domain.mortgage import amortize_single_month

        statements = self.get_all_monthly_statements()
        if not statements:
            return

        # Group statements chronologically by calendar month (YYYY, MM)
        by_month = defaultdict(list)
        for s in statements:
            parts = parse_date_sort_key(s.get("statement_date", ""))
            m_key = (parts[0], parts[1])
            by_month[m_key].append(s)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            current_bal = initial_principal

            # Sort calendar months chronologically
            for m_key in sorted(by_month.keys()):
                month_stmts = by_month[m_key]
                # Amortize exactly once for this calendar month
                current_bal = amortize_single_month(current_bal, monthly_direct_debit, interest_rate)

                # For the month's statements:
                # The first statement records the monthly mortgage debit; subsequent ones record 0.00 debit.
                # All statements in the month share the month-end amortized balance.
                for idx, stmt in enumerate(month_stmts):
                    debit = monthly_direct_debit if idx == 0 else Decimal("0.00")
                    cursor.execute(
                        "UPDATE monthly_records SET mortgage_debit = ?, outstanding_balance = ? WHERE id = ?",
                        (str(debit), str(current_bal), stmt["id"]),
                    )
            conn.commit()

    # [spec: UI-003]
    def get_portfolio_cumulative_summary(self) -> dict:
        """Calculate cumulative portfolio totals across all ingested monthly statements using Decimal."""
        records = self.get_all_monthly_statements()
        if not records:
            return {
                "total_statements": 0,
                "gross_rent": Decimal("0.00"),
                "total_deductions": Decimal("0.00"),
                "net_earnings": Decimal("0.00"),
                "mortgage_due": Decimal("0.00"),
                "shortfall": Decimal("0.00"),
                "surplus": Decimal("0.00"),
                "earning_retention_pct": Decimal("0.00"),
                "expense_ratio_pct": Decimal("0.00"),
            }

        total_gross = sum((Decimal(str(r["gross_income"])) for r in records), Decimal("0.00"))
        total_deductions = sum((Decimal(str(r["total_expenditure"])) for r in records), Decimal("0.00"))
        total_earnings = sum((Decimal(str(r["net_payout"])) for r in records), Decimal("0.00"))
        total_mortgage = sum((Decimal(str(r["mortgage_debit"])) for r in records), Decimal("0.00"))
        total_shortfall = sum((Decimal(str(r["calculated_shortfall"])) for r in records), Decimal("0.00"))
        total_surplus = sum((Decimal(str(r["calculated_surplus"])) for r in records), Decimal("0.00"))

        if total_gross > Decimal("0.00"):
            retention = (total_earnings / total_gross) * Decimal("100.00")
            expense_ratio = (total_deductions / total_gross) * Decimal("100.00")
        else:
            retention = Decimal("0.00")
            expense_ratio = Decimal("0.00")

        return {
            "total_statements": len(records),
            "gross_rent": total_gross.quantize(Decimal("0.01")),
            "total_deductions": total_deductions.quantize(Decimal("0.01")),
            "net_earnings": total_earnings.quantize(Decimal("0.01")),
            "mortgage_due": total_mortgage.quantize(Decimal("0.01")),
            "shortfall": total_shortfall.quantize(Decimal("0.01")),
            "surplus": total_surplus.quantize(Decimal("0.01")),
            "earning_retention_pct": retention.quantize(Decimal("0.1")),
            "expense_ratio_pct": expense_ratio.quantize(Decimal("0.1")),
        }

    # [spec: ISSUE-002]
    def create_maintenance_issue(
        self,
        title: str,
        category: str = "General",
        status: str = "Open",
        priority: str = "Normal",
        contractor_name: str | None = None,
        total_cost: Decimal | str = Decimal("0.00"),
        reported_date: str = "",
        resolved_date: str | None = None,
        resolution_note: str | None = None,
        is_suggested: bool = False,
        source_invoice_id: int | None = None,
        initial_note: str | None = None,
    ) -> int:
        """Create a maintenance issue record in the database."""
        cost_str = str(Decimal(str(total_cost)))
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO maintenance_issues (
                    title, category, status, priority, contractor_name,
                    total_cost, reported_date, resolved_date, resolution_note,
                    is_suggested, source_invoice_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    title,
                    category,
                    status,
                    priority,
                    contractor_name,
                    cost_str,
                    reported_date,
                    resolved_date,
                    resolution_note,
                    1 if is_suggested else 0,
                    source_invoice_id,
                ),
            )
            issue_id = cursor.lastrowid
            if issue_id is None:
                raise RuntimeError("Failed to retrieve issue_id after inserting maintenance_issue.")

            if initial_note:
                cursor.execute(
                    """
                    INSERT INTO maintenance_issue_notes (issue_id, author, comment)
                    VALUES (?, 'Landlord', ?)
                    """,
                    (issue_id, initial_note),
                )

            # If created from a source invoice, also pin it
            if source_invoice_id:
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO maintenance_issue_invoices (issue_id, invoice_id)
                    VALUES (?, ?)
                    """,
                    (issue_id, source_invoice_id),
                )

            conn.commit()
            return issue_id

    # [spec: ISSUE-002]
    def add_issue_note(self, issue_id: int, comment: str, author: str = "Landlord") -> int:
        """Append a timestamped free-text note to a maintenance issue."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO maintenance_issue_notes (issue_id, author, comment)
                VALUES (?, ?, ?)
                """,
                (issue_id, author, comment),
            )
            note_id = cursor.lastrowid
            if note_id is None:
                raise RuntimeError("Failed to retrieve note_id after inserting maintenance_issue_note.")
            conn.commit()
            return note_id

    # [spec: ISSUE-002]
    def update_issue_status(
        self,
        issue_id: int,
        status: str,
        resolved_date: str | None = None,
        resolution_note: str | None = None,
    ) -> None:
        """Update issue lifecycle state (Open, In Progress, Resolved)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if status == "Resolved":
                cursor.execute(
                    """
                    UPDATE maintenance_issues
                    SET status = ?, resolved_date = COALESCE(?, resolved_date), resolution_note = COALESCE(?, resolution_note)
                    WHERE id = ?
                    """,
                    (status, resolved_date, resolution_note, issue_id),
                )
                if resolution_note:
                    cursor.execute(
                        """
                        INSERT INTO maintenance_issue_notes (issue_id, author, comment)
                        VALUES (?, 'System', ?)
                        """,
                        (issue_id, f"Resolved closeout note: {resolution_note}"),
                    )
            else:
                cursor.execute(
                    """
                    UPDATE maintenance_issues
                    SET status = ?
                    WHERE id = ?
                    """,
                    (status, issue_id),
                )
            conn.commit()

    # [spec: ISSUE-001]
    def pin_invoice_to_issue(self, issue_id: int, invoice_id: int) -> None:
        """Pin a contractor invoice to a maintenance issue and update total cost deterministically."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR IGNORE INTO maintenance_issue_invoices (issue_id, invoice_id)
                VALUES (?, ?)
                """,
                (issue_id, invoice_id),
            )
            # Recalculate total cost from pinned invoices
            cursor.execute(
                """
                SELECT COALESCE(SUM(CAST(ci.gross_amount AS NUMERIC)), 0)
                FROM maintenance_issue_invoices mii
                JOIN contractor_invoices ci ON mii.invoice_id = ci.id
                WHERE mii.issue_id = ?
                """,
                (issue_id,),
            )
            sum_row = cursor.fetchone()
            if sum_row and sum_row[0] is not None:
                # Update total cost with exact Decimal representation
                cursor.execute(
                    """
                    SELECT gross_amount FROM contractor_invoices
                    WHERE id IN (SELECT invoice_id FROM maintenance_issue_invoices WHERE issue_id = ?)
                    """,
                    (issue_id,),
                )
                gross_rows = cursor.fetchall()
                total = sum((Decimal(r["gross_amount"]) for r in gross_rows), Decimal("0.00"))
                cursor.execute(
                    "UPDATE maintenance_issues SET total_cost = ? WHERE id = ?",
                    (str(total), issue_id),
                )
            conn.commit()

    # [spec: ISSUE-001]
    def unpin_invoice_from_issue(self, issue_id: int, invoice_id: int) -> None:
        """Unpin an invoice from a maintenance issue and update total cost."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM maintenance_issue_invoices WHERE issue_id = ? AND invoice_id = ?",
                (issue_id, invoice_id),
            )
            cursor.execute(
                """
                SELECT gross_amount FROM contractor_invoices
                WHERE id IN (SELECT invoice_id FROM maintenance_issue_invoices WHERE issue_id = ?)
                """,
                (issue_id,),
            )
            gross_rows = cursor.fetchall()
            total = sum((Decimal(r["gross_amount"]) for r in gross_rows), Decimal("0.00"))
            cursor.execute(
                "UPDATE maintenance_issues SET total_cost = ? WHERE id = ?",
                (str(total), issue_id),
            )
            conn.commit()

    # [spec: ISSUE-001]
    def confirm_suggested_issue(self, issue_id: int) -> None:
        """Confirm a suggested maintenance issue into active status."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE maintenance_issues SET is_suggested = 0 WHERE id = ?",
                (issue_id,),
            )
            conn.commit()

    # [spec: ISSUE-001]
    def dismiss_suggested_issue(self, issue_id: int) -> None:
        """Dismiss (delete) a suggested maintenance issue."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM maintenance_issues WHERE id = ? AND is_suggested = 1",
                (issue_id,),
            )
            conn.commit()

    # [spec: ISSUE-001]
    # [spec: ISSUE-002]
    def get_all_maintenance_issues(self, include_suggested: bool = True) -> list[dict[str, Any]]:
        """Retrieve maintenance issues with pinned invoices and comment notes."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if include_suggested:
                cursor.execute("SELECT * FROM maintenance_issues ORDER BY id DESC")
            else:
                cursor.execute("SELECT * FROM maintenance_issues WHERE is_suggested = 0 ORDER BY id DESC")
            issue_rows = [dict(r) for r in cursor.fetchall()]
            if not issue_rows:
                return []

            cursor.execute(
                """
                SELECT id, issue_id, author, comment, created_at
                FROM maintenance_issue_notes
                ORDER BY id ASC
                """
            )
            notes_by_issue = defaultdict(list)
            for n in cursor.fetchall():
                n_dict = dict(n)
                notes_by_issue[n_dict["issue_id"]].append(n_dict)

            cursor.execute(
                """
                SELECT mii.issue_id, ci.id, ci.contractor_name, ci.invoice_date, ci.invoice_number,
                       ci.gross_amount, ci.job_description, ci.file_hash
                FROM maintenance_issue_invoices mii
                JOIN contractor_invoices ci ON mii.invoice_id = ci.id
                ORDER BY ci.id ASC
                """
            )
            invoices_by_issue = defaultdict(list)
            for inv in cursor.fetchall():
                inv_dict = dict(inv)
                i_id = inv_dict.pop("issue_id")
                invoices_by_issue[i_id].append(inv_dict)

            for issue in issue_rows:
                issue["notes"] = notes_by_issue.get(issue["id"], [])
                issue["pinned_invoices"] = invoices_by_issue.get(issue["id"], [])

            return issue_rows

    # [spec: ISSUE-001]
    # [spec: ISSUE-002]
    def get_maintenance_issue_by_id(self, issue_id: int) -> dict[str, Any] | None:
        """Retrieve a single maintenance issue with notes and pinned invoices."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM maintenance_issues WHERE id = ?", (issue_id,))
            row = cursor.fetchone()
            if not row:
                return None
            issue = dict(row)

            cursor.execute(
                """
                SELECT id, issue_id, author, comment, created_at
                FROM maintenance_issue_notes
                WHERE issue_id = ?
                ORDER BY id ASC
                """,
                (issue["id"],),
            )
            issue["notes"] = [dict(n) for n in cursor.fetchall()]

            cursor.execute(
                """
                SELECT ci.id, ci.contractor_name, ci.invoice_date, ci.invoice_number,
                       ci.gross_amount, ci.job_description, ci.file_hash
                FROM maintenance_issue_invoices mii
                JOIN contractor_invoices ci ON mii.invoice_id = ci.id
                WHERE mii.issue_id = ?
                ORDER BY ci.id ASC
                """,
                (issue["id"],),
            )
            issue["pinned_invoices"] = [dict(inv) for inv in cursor.fetchall()]
            return issue

    # [spec: ISSUE-001]
    def suggest_issue_from_invoice(self, invoice_id: int) -> int | None:
        """Create a suggested maintenance issue from an ingested contractor invoice."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM contractor_invoices WHERE id = ?", (invoice_id,))
            inv_row = cursor.fetchone()
            if not inv_row:
                return None
            inv = dict(inv_row)

            # Check if a suggestion already exists for this invoice
            cursor.execute(
                "SELECT id FROM maintenance_issues WHERE source_invoice_id = ?",
                (invoice_id,),
            )
            existing = cursor.fetchone()
            if existing:
                return existing["id"]

            title = f"{inv['contractor_name']}: {inv.get('job_description') or 'Contractor repair'}"
            cost = inv["gross_amount"]
            reported_date = inv["invoice_date"]
            contractor_name = inv["contractor_name"]

            return self.create_maintenance_issue(
                title=title,
                category="Repair / Maintenance",
                status="Open",
                priority="Normal",
                contractor_name=contractor_name,
                total_cost=cost,
                reported_date=reported_date,
                is_suggested=True,
                source_invoice_id=invoice_id,
                initial_note=f"Auto-suggested from Invoice #{inv['invoice_number']}",
            )

    # [spec: ISSUE-003]
    def sync_issues_from_invoices(self) -> list[int]:
        """Scan historical contractor invoices and extract unmapped invoices into suggested maintenance issues.

        Implements AC-ISSUE-003.1 and AC-ISSUE-003.2.
        Returns list of newly created issue IDs.
        """
        new_issue_ids: list[int] = []
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # AC-ISSUE-003.1: Find all contractor invoices not linked to any maintenance issue
            cursor.execute(
                """
                SELECT ci.id
                FROM contractor_invoices ci
                WHERE ci.id NOT IN (
                    SELECT DISTINCT source_invoice_id FROM maintenance_issues WHERE source_invoice_id IS NOT NULL
                )
                AND ci.id NOT IN (
                    SELECT DISTINCT invoice_id FROM maintenance_issue_invoices
                )
                ORDER BY ci.id ASC
                """
            )
            rows = cursor.fetchall()

        # AC-ISSUE-003.2: Create candidate suggested maintenance issues
        for row in rows:
            inv_id = row["id"]
            created_id = self.suggest_issue_from_invoice(inv_id)
            if created_id is not None:
                new_issue_ids.append(created_id)

        return new_issue_ids

    # [spec: COMP-001]
    def create_compliance_certificate(
        self,
        certificate_type: str,
        title: str,
        issue_date: str,
        expiry_date: str,
        provider: str | None = None,
        reference_number: str | None = None,
        cost: Decimal | str = Decimal("0.00"),
        epc_rating: str | None = None,
        file_path: str | None = None,
        notes: str | None = None,
    ) -> int:
        """Create a new compliance certificate record in the database."""
        cost_str = str(Decimal(str(cost)))
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO compliance_certificates (
                    certificate_type, title, provider, reference_number,
                    issue_date, expiry_date, cost, epc_rating, file_path, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    certificate_type,
                    title,
                    provider,
                    reference_number,
                    issue_date,
                    expiry_date,
                    cost_str,
                    epc_rating,
                    file_path,
                    notes,
                ),
            )
            cert_id = cursor.lastrowid
            if cert_id is None:
                raise RuntimeError("Failed to retrieve cert_id after inserting compliance_certificate.")
            conn.commit()
            return cert_id

    # [spec: COMP-001]
    def update_compliance_certificate(
        self,
        cert_id: int,
        certificate_type: str | None = None,
        title: str | None = None,
        provider: str | None = None,
        reference_number: str | None = None,
        issue_date: str | None = None,
        expiry_date: str | None = None,
        cost: Decimal | str | None = None,
        epc_rating: str | None = None,
        file_path: str | None = None,
        notes: str | None = None,
    ) -> None:
        """Update an existing compliance certificate record."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM compliance_certificates WHERE id = ?", (cert_id,))
            row = cursor.fetchone()
            if not row:
                return

            current = dict(row)
            new_type = certificate_type if certificate_type is not None else current["certificate_type"]
            new_title = title if title is not None else current["title"]
            new_provider = provider if provider is not None else current["provider"]
            new_ref = reference_number if reference_number is not None else current["reference_number"]
            new_issue_date = issue_date if issue_date is not None else current["issue_date"]
            new_expiry_date = expiry_date if expiry_date is not None else current["expiry_date"]
            new_cost = str(Decimal(str(cost))) if cost is not None else current["cost"]
            new_epc = epc_rating if epc_rating is not None else current["epc_rating"]
            new_file_path = file_path if file_path is not None else current["file_path"]
            new_notes = notes if notes is not None else current["notes"]

            cursor.execute(
                """
                UPDATE compliance_certificates
                SET certificate_type = ?, title = ?, provider = ?, reference_number = ?,
                    issue_date = ?, expiry_date = ?, cost = ?, epc_rating = ?,
                    file_path = ?, notes = ?
                WHERE id = ?
                """,
                (
                    new_type,
                    new_title,
                    new_provider,
                    new_ref,
                    new_issue_date,
                    new_expiry_date,
                    new_cost,
                    new_epc,
                    new_file_path,
                    new_notes,
                    cert_id,
                ),
            )
            conn.commit()

    # [spec: COMP-001]
    def delete_compliance_certificate(self, cert_id: int) -> None:
        """Delete a compliance certificate record."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM compliance_certificates WHERE id = ?", (cert_id,))
            conn.commit()

    # [spec: COMP-001]
    def get_all_compliance_certificates(self) -> list[dict[str, Any]]:
        """Retrieve all compliance certificates ordered by expiry date."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM compliance_certificates ORDER BY id ASC")
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    # [spec: COMP-001]
    def get_compliance_certificate_by_id(self, cert_id: int) -> dict[str, Any] | None:
        """Retrieve a specific compliance certificate by ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM compliance_certificates WHERE id = ?", (cert_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

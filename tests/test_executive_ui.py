"""Unit and integration tests for UI-001, UI-002, and UI-003.
Verifies:
- UI-001: Monthly Statements Ledger & Trend Graphs
- UI-002: Contractor Invoices Ledger & Maintenance Items
- UI-003: Executive Multi-Theme Layout & Loan Payoff Progress
"""

from decimal import Decimal
from pathlib import Path

import pytest

from src.config import AppConfig, MortgageSettings, OllamaSettings
from src.domain.models import ContractorInvoice, ExpenditureLine, RentalStatement
from src.storage.database import Database
from src.ui.app import ExecutiveDashboardApp
from src.ui.components import (
    build_mortgage_progress_bar_props,
    format_kpi_card_data,
    prepare_chart_series,
    prepare_invoices_table_rows,
    prepare_statements_table_rows,
)
from src.ui.theme import DEFAULT_THEME, THEMES, get_theme_css


@pytest.fixture
def test_config():
    return AppConfig(
        ollama=OllamaSettings(base_url="http://localhost:11434", model="llama3.2:3b"),
        mortgage=MortgageSettings(
            monthly_direct_debit=Decimal("1997.00"),
            interest_rate=Decimal("4.30"),
            fixed_deal_end_date="30-11-2027",
            effective_from="01-11-2025",
            initial_principal=Decimal("68735.81"),
        ),
    )


# [verifies: UI-001/AC-UI-001.1]
def test_monthly_statements_ledger_rows_and_shortfall(tmp_path: Path, test_config):
    """Verify that monthly statement ledger table lists statement date, ref, number, income, deductions, payout, mortgage, and shortfall."""
    db = Database(db_path=tmp_path / "test.db")
    stmt = RentalStatement(
        statement_date="16/10/2026",
        reference="WGL230032",
        statement_number="13",
        gross_income=Decimal("1750.00"),
        expenditures=[
            ExpenditureLine(
                description="Agency fee", net=Decimal("150.00"), vat=Decimal("30.00"), gross=Decimal("180.00")
            )
        ],
        net_payout=Decimal("1570.00"),
    )
    db.save_monthly_statement(stmt, test_config.mortgage.monthly_direct_debit, Decimal("67000.00"))

    records = db.get_all_monthly_statements()
    assert len(records) == 1
    row_data = prepare_statements_table_rows(records)

    assert row_data[0]["statement_date"] == "16/10/2026"
    assert row_data[0]["statement_number"] == "#13"
    assert row_data[0]["reference"] == "WGL230032"
    assert row_data[0]["gross_income"] == "£1,750.00"
    assert row_data[0]["total_expenditure"] == "£180.00"
    assert row_data[0]["net_payout"] == "£1,570.00"
    assert row_data[0]["mortgage_debit"] == "£1,997.00"
    # Shortfall: 1997 - 1570 = 427.00
    assert row_data[0]["shortfall"] == "£427.00"


# [verifies: UI-001/AC-UI-001.1]
def test_monthly_statements_ledger_multi_statement_consolidation(tmp_path: Path, test_config):
    """Verify that multiple statements in the same calendar month are consolidated into a single row with combined sums and multi-statement metadata."""
    db = Database(db_path=tmp_path / "test.db")
    stmt1 = RentalStatement(
        statement_date="05/11/2026",
        reference="REF-NOV-1",
        statement_number="14",
        gross_income=Decimal("1750.00"),
        expenditures=[
            ExpenditureLine(
                description="Management Fee", net=Decimal("100.00"), vat=Decimal("20.00"), gross=Decimal("120.00")
            )
        ],
        net_payout=Decimal("1630.00"),
    )
    stmt2 = RentalStatement(
        statement_date="20/11/2026",
        reference="REF-NOV-2",
        statement_number="15",
        gross_income=Decimal("250.00"),
        expenditures=[
            ExpenditureLine(
                description="Plumbing repair", net=Decimal("50.00"), vat=Decimal("10.00"), gross=Decimal("60.00")
            )
        ],
        net_payout=Decimal("190.00"),
    )
    db.save_monthly_statement(stmt1, test_config.mortgage.monthly_direct_debit, Decimal("67000.00"))
    db.save_monthly_statement(stmt2, test_config.mortgage.monthly_direct_debit, Decimal("67000.00"))

    records = db.get_all_monthly_statements()
    assert len(records) == 2

    table_rows = prepare_statements_table_rows(records)
    # Both statements are in Nov 2026, so they should be consolidated into 1 row
    assert len(table_rows) == 1
    row = table_rows[0]
    assert row["is_consolidated"] is True
    assert row["statement_count"] == 2
    assert row["statement_number"] == "2 Statements (#14, #15)"
    assert row["statement_date"] == "Nov 2026"
    assert row["gross_income"] == "£2,000.00"  # 1750 + 250
    assert row["total_expenditure"] == "£180.00"  # 120 + 60
    assert row["net_payout"] == "£1,820.00"  # 1630 + 190
    assert row["mortgage_debit"] == "£1,997.00"
    # Combined shortfall: 1997 - 1820 = 177.00
    assert row["shortfall"] == "£177.00"
    assert len(row["sub_statements"]) == 2
    assert len(row["expenditures"]) == 2
    assert row["expenditures"][0]["source_statement"] == "#14"
    assert row["expenditures"][1]["source_statement"] == "#15"


# [verifies: UI-001/AC-UI-001.2]
def test_monthly_statement_itemized_expenditures(tmp_path: Path, test_config):
    """Verify that monthly records include itemized expenditure lines with net, vat, and gross amounts, and partition into management and expenses."""
    from src.ui.components import partition_statement_expenditures

    db = Database(db_path=tmp_path / "test.db")
    stmt = RentalStatement(
        statement_date="16/10/2026",
        reference="WGL230032",
        statement_number="13",
        gross_income=Decimal("1750.00"),
        expenditures=[
            ExpenditureLine(
                description="Letting fee at 10%", net=Decimal("70.00"), vat=Decimal("14.00"), gross=Decimal("84.00")
            ),
            ExpenditureLine(
                description="Tenancy Deposit Scheme Monthly Fee",
                net=Decimal("9.00"),
                vat=Decimal("1.80"),
                gross=Decimal("10.80"),
            ),
            ExpenditureLine(
                description="Boiler repair", net=Decimal("100.00"), vat=Decimal("20.00"), gross=Decimal("120.00")
            ),
        ],
        net_payout=Decimal("1535.20"),
    )
    db.save_monthly_statement(stmt, test_config.mortgage.monthly_direct_debit, Decimal("67000.00"))

    records = db.get_all_monthly_statements()
    exp_lines = records[0]["expenditures"]
    assert len(exp_lines) == 3
    assert exp_lines[0]["description"] == "Letting fee at 10%"
    assert exp_lines[0]["net"] == "70.00"
    assert exp_lines[0]["vat"] == "14.00"
    assert exp_lines[0]["gross"] == "84.00"

    # Partition test: Letting fee and Tenancy Deposit Scheme in management costs, Boiler repair in direct expenses
    partition = partition_statement_expenditures(exp_lines)
    assert len(partition["management_costs"]) == 2
    assert len(partition["direct_expenses"]) == 1
    assert partition["total_management_costs"] == Decimal("94.80")
    assert partition["total_direct_expenses"] == Decimal("120.00")
    assert partition["total_deductions"] == Decimal("214.80")


# [verifies: UI-001/AC-UI-001.3]
def test_executive_kpi_summary_cards(tmp_path: Path, test_config):
    """Verify that KPI summary calculates latest gross rent, net payout, expenses, and shortfall."""
    db = Database(db_path=tmp_path / "test.db")
    stmt = RentalStatement(
        statement_date="16/10/2026",
        reference="WGL230032",
        statement_number="13",
        gross_income=Decimal("1750.00"),
        expenditures=[
            ExpenditureLine(
                description="Agency fee", net=Decimal("150.00"), vat=Decimal("30.00"), gross=Decimal("180.00")
            )
        ],
        net_payout=Decimal("1570.00"),
    )
    db.save_monthly_statement(stmt, test_config.mortgage.monthly_direct_debit, Decimal("67000.00"))

    kpis = db.get_kpi_summary(default_mortgage_debit=test_config.mortgage.monthly_direct_debit)
    cards = format_kpi_card_data(kpis)

    card_map = {c["id"]: c for c in cards}
    assert card_map["gross_rent"]["value"] == "£1,750.00"
    assert card_map["expenses"]["value"] == "£180.00"
    assert card_map["net_payout"]["value"] == "£1,570.00"
    assert card_map["net_payout"]["title"] == "Net Landlord Earning"
    # Shortfall: 1997 - 1570 = 427.00
    assert card_map["cashflow_balance"]["value"] == "£427.00"

    # Verify order: Gross -> Expenses -> Earning -> Shortfall
    assert cards[0]["id"] == "gross_rent"
    assert cards[1]["id"] == "expenses"
    assert cards[2]["id"] == "net_payout"
    assert cards[3]["id"] == "cashflow_balance"


# [verifies: UI-001/AC-UI-001.4]
def test_interactive_monthly_trend_chart_series(tmp_path: Path, test_config):
    """Verify time-series preparation for monthly trend graphs plotting gross rent, deductions, payout, and shortfall."""
    db = Database(db_path=tmp_path / "test.db")
    stmt1 = RentalStatement(
        statement_date="16/09/2026",
        reference="REF1",
        statement_number="1",
        gross_income=Decimal("1750.00"),
        expenditures=[],
        net_payout=Decimal("1750.00"),
    )
    stmt2 = RentalStatement(
        statement_date="16/10/2026",
        reference="REF2",
        statement_number="2",
        gross_income=Decimal("1750.00"),
        expenditures=[
            ExpenditureLine(description="Fee", net=Decimal("100.00"), vat=Decimal("20.00"), gross=Decimal("120.00"))
        ],
        net_payout=Decimal("1630.00"),
    )
    db.save_monthly_statement(stmt1, test_config.mortgage.monthly_direct_debit, Decimal("68000.00"))
    db.save_monthly_statement(stmt2, test_config.mortgage.monthly_direct_debit, Decimal("67500.00"))

    records = db.get_all_monthly_statements()
    series = prepare_chart_series(records)

    assert series["categories"] == ["Sep 2026", "Oct 2026"]
    assert series["gross"] == [1750.0, 1750.0]
    assert series["deductions"] == [0.0, 120.0]
    assert series["payout"] == [1750.0, 1630.0]
    assert series["shortfall"] == [247.0, 367.0]


# [verifies: UI-001/AC-UI-001.5]
def test_monthly_statement_manual_edit_details(tmp_path: Path, test_config):
    """AC-UI-001.5: In the statement breakdown popup dialog, the user shall have an Edit option

    to modify statement date, reference, statement number, gross rent, mortgage debit, and itemized
    expenditure lines, recalculating total deductions, net earnings, shortfall, and amortized mortgage balances upon saving.
    """
    db = Database(db_path=tmp_path / "test.db")
    stmt = RentalStatement(
        statement_date="16/10/2026",
        reference="WGL230032",
        statement_number="13",
        gross_income=Decimal("1750.00"),
        expenditures=[
            ExpenditureLine(
                description="Agency fee", net=Decimal("150.00"), vat=Decimal("30.00"), gross=Decimal("180.00")
            )
        ],
        net_payout=Decimal("1570.00"),
    )
    stmt_id = db.save_monthly_statement(stmt, test_config.mortgage.monthly_direct_debit, Decimal("67000.00"))

    # Verify initial record
    original = db.get_monthly_statement_by_id(stmt_id)
    assert original is not None
    assert original["statement_number"] == "13"
    assert Decimal(original["gross_income"]) == Decimal("1750.00")
    assert Decimal(original["total_expenditure"]) == Decimal("180.00")
    assert Decimal(original["net_payout"]) == Decimal("1570.00")

    # Perform update (e.g. adjust gross rent to 1800, add a plumbing repair line)
    updated_expenditures = [
        {"description": "Agency fee", "net": "150.00", "vat": "30.00", "gross": "180.00"},
        {"description": "Plumbing Washer Replacement", "net": "50.00", "vat": "10.00", "gross": "60.00"},
    ]
    db.update_monthly_statement(
        statement_id=stmt_id,
        statement_date="18/10/2026",
        reference="WGL230032-REV",
        statement_number="13A",
        gross_income=Decimal("1800.00"),
        mortgage_debit=Decimal("1997.00"),
        expenditures=updated_expenditures,
    )

    # Recalculate balances
    db.recalculate_statement_balances(
        initial_principal=test_config.mortgage.initial_principal,
        monthly_direct_debit=test_config.mortgage.monthly_direct_debit,
        interest_rate=test_config.mortgage.interest_rate,
    )

    # Verify retrieved updated record
    updated = db.get_monthly_statement_by_id(stmt_id)
    assert updated is not None
    assert updated["statement_date"] == "18/10/2026"
    assert updated["reference"] == "WGL230032-REV"
    assert updated["statement_number"] == "13A"
    assert Decimal(updated["gross_income"]) == Decimal("1800.00")
    # Total expenditures = 180.00 + 60.00 = 240.00
    assert Decimal(updated["total_expenditure"]) == Decimal("240.00")
    # Net payout = 1800.00 - 240.00 = 1560.00
    assert Decimal(updated["net_payout"]) == Decimal("1560.00")
    # Shortfall = 1997.00 - 1560.00 = 437.00
    assert Decimal(updated["calculated_shortfall"]) == Decimal("437.00")
    assert len(updated["expenditures"]) == 2
    assert updated["expenditures"][1]["description"] == "Plumbing Washer Replacement"
    assert Decimal(updated["expenditures"][1]["gross"]) == Decimal("60.00")


# [verifies: UI-002/AC-UI-002.1]
def test_contractor_invoices_table_rendering(tmp_path: Path):
    """Verify that contractor invoices table lists contractor name, date, invoice number, gross amount, and description."""
    db = Database(db_path=tmp_path / "test.db")
    invoice = ContractorInvoice(
        contractor_name="Herts Electrical Services Ltd",
        invoice_date="14/07/2026",
        invoice_number="INV-35",
        gross_amount=Decimal("105.60"),
        job_description="Electrical underfloor heating fix",
    )
    db.save_contractor_invoice(invoice)

    invoices = db.get_all_contractor_invoices()
    assert len(invoices) == 1
    rows = prepare_invoices_table_rows(invoices)

    assert rows[0]["contractor_name"] == "Herts Electrical Services Ltd"
    assert rows[0]["invoice_date"] == "14/07/2026"
    assert rows[0]["invoice_number"] == "INV-35"
    assert rows[0]["gross_amount"] == "£105.60"
    assert rows[0]["job_description"] == "Electrical underfloor heating fix"


# [verifies: UI-002/AC-UI-002.2]
def test_contractor_invoice_deduction_matching(tmp_path: Path, test_config):
    """Verify highlighting of contractor invoices that correspond to deduction lines in rental statements."""
    db = Database(db_path=tmp_path / "test.db")
    # Save rental statement with a matching deduction
    stmt = RentalStatement(
        statement_date="16/08/2026",
        reference="WGL230032",
        statement_number="11",
        gross_income=Decimal("1750.00"),
        expenditures=[
            ExpenditureLine(
                description="Herts Electrical Services Ltd repair INV-35",
                net=Decimal("88.00"),
                vat=Decimal("17.60"),
                gross=Decimal("105.60"),
            )
        ],
        net_payout=Decimal("1644.40"),
    )
    db.save_monthly_statement(stmt, test_config.mortgage.monthly_direct_debit, Decimal("67000.00"))

    # Matching invoice
    inv1 = ContractorInvoice(
        contractor_name="Herts Electrical Services Ltd",
        invoice_date="14/07/2026",
        invoice_number="INV-35",
        gross_amount=Decimal("105.60"),
    )
    # Unmatched invoice
    inv2 = ContractorInvoice(
        contractor_name="Roofing Experts",
        invoice_date="20/08/2026",
        invoice_number="ROOF-99",
        gross_amount=Decimal("500.00"),
    )
    db.save_contractor_invoice(inv1)
    db.save_contractor_invoice(inv2)

    invoices = db.get_all_contractor_invoices()
    rows = prepare_invoices_table_rows(invoices)

    row_map = {r["invoice_number"]: r for r in rows}
    assert row_map["INV-35"]["is_deduction_matched"] is True
    assert row_map["ROOF-99"]["is_deduction_matched"] is False


# [verifies: UI-002/AC-UI-002.1]
def test_contractor_invoices_date_normalization_to_dmy(tmp_path: Path):
    """Verify that contractor invoices with written or ISO dates are saved and displayed as DD/MM/YYYY."""
    db = Database(db_path=tmp_path / "test.db")
    invoice1 = ContractorInvoice(
        contractor_name="Gas Flow Heating Ltd",
        invoice_date="10th December 2025",
        invoice_number="26307",
        gross_amount=Decimal("512.40"),
    )
    invoice2 = ContractorInvoice(
        contractor_name="Gas Flow Heating Ltd",
        invoice_date="2025-11-28",
        invoice_number="26093",
        gross_amount=Decimal("84.00"),
    )
    db.save_contractor_invoice(invoice1)
    db.save_contractor_invoice(invoice2)

    invoices = db.get_all_contractor_invoices()
    rows = prepare_invoices_table_rows(invoices)
    date_map = {r["invoice_number"]: r["invoice_date"] for r in rows}

    assert date_map["26307"] == "10/12/2025"
    assert date_map["26093"] == "28/11/2025"


# [verifies: UI-003/AC-UI-003.1]
def test_loan_payoff_progress_bar_props(tmp_path: Path, test_config):
    """Verify that loan payoff progress bar renders initial principal, balance, paid amount, interest paid, and remaining term."""
    db = Database(db_path=tmp_path / "test.db")
    # Add statement with current balance £60,000 against initial £68,735.81
    stmt = RentalStatement(
        statement_date="16/10/2026",
        reference="WGL230032",
        statement_number="12",
        gross_income=Decimal("1750.00"),
        expenditures=[],
        net_payout=Decimal("1750.00"),
    )
    db.save_monthly_statement(stmt, test_config.mortgage.monthly_direct_debit, Decimal("60000.00"))

    app = ExecutiveDashboardApp(db=db, config=test_config)
    progress = app.calculate_current_mortgage_progress()
    summary = db.get_portfolio_cumulative_summary()
    props = build_mortgage_progress_bar_props(
        progress,
        fixed_deal_end_date=test_config.mortgage.fixed_deal_end_date,
        reference_date="17-10-2026",
        cumulative_summary=summary,
    )

    assert props["initial_principal"] == "£68,735.81"
    assert props["current_balance"] == "£60,000.00"
    assert props["paid_off_amount"] == "£8,735.81"
    assert props["paid_off_percentage"] == "12.7%"
    assert props["interest_paid"] == "£246.30"
    assert "1 yr 1 mo (13 mos)" in props["remaining_term"]
    assert "days" in props["days_remaining"]
    assert "equity" not in props
    assert "UK capital repayment mortgage" in props["explanation_text"]
    assert "split between Interest" in props["explanation_text"]
    assert "%" in props["explanation_text"]
    # Cumulative payment funding split: rental vs shortfall
    assert props["total_mortgage_funded"] == "£1,997.00"
    assert props["rental_income_funded"] == "£1,750.00"
    assert props["shortfall_funded"] == "£247.00"
    assert props["rental_funding_pct"] == "87.6%"
    assert props["shortfall_funding_pct"] == "12.4%"


# [verifies: UI-003/AC-UI-003.1]
def test_format_remaining_term_and_interest_calculation():
    """Verify formatting of remaining deal time and deterministic interest accumulation."""
    from src.domain.mortgage import calculate_amortized_interest_paid
    from src.ui.components import format_remaining_term

    # >= 6 months
    term_over_6 = format_remaining_term(
        end_date_str="30-11-2027",
        reference_date="17-10-2026",
    )
    assert term_over_6 == "1 yr 1 mo (13 mos)"

    # < 6 months
    term_under_6 = format_remaining_term(
        end_date_str="17-03-2027",
        reference_date="17-10-2026",
    )
    assert "5 months" in term_under_6
    assert "days" in term_under_6

    # Expired
    term_expired = format_remaining_term(
        end_date_str="01-01-2025",
        reference_date="17-10-2026",
    )
    assert term_expired == "Expired"

    # Cumulative interest over 11 repayments on £68,735.81 at 4.30%
    interest = calculate_amortized_interest_paid(
        initial_principal=Decimal("68735.81"),
        monthly_direct_debit=Decimal("1997.00"),
        annual_interest_rate_percent=Decimal("4.30"),
        num_repayments=11,
    )
    assert interest == Decimal("2360.56")


# [verifies: UI-003/AC-UI-003.2]
def test_quiet_luxury_palette_and_no_theme_dropdown(tmp_path: Path, test_config):
    """Verify that the unified Quiet Luxury dark palette is applied and theme selector dropdown is omitted."""
    assert DEFAULT_THEME == "Quiet Luxury"
    assert "Quiet Luxury" in THEMES

    tokens = THEMES["Quiet Luxury"]
    assert tokens.bg_main.lower() == "#0e1015"
    assert tokens.bg_card.lower() == "#141720"
    assert tokens.accent_cyan.lower() == "#e5c07b"  # Champagne Gold
    assert tokens.accent_emerald.lower() == "#86efac"  # Soft Mint
    assert tokens.accent_amber.lower() == "#d97706"  # Warm Amber
    assert tokens.accent_coral.lower() == "#9f1239"  # Muted Burgundy
    assert "229, 192, 123" in tokens.border_color

    css = get_theme_css("Quiet Luxury")
    assert "--bg-main: #0e1015" in css
    assert "--accent-cyan: #e5c07b" in css
    assert "--accent-emerald: #86efac" in css
    assert "--accent-coral: #9f1239" in css
    assert "--border-color: rgba(229, 192, 123, 0.22)" in css

    # Verify that app initializes with Quiet Luxury as default theme
    db = Database(db_path=tmp_path / "test.db")
    app = ExecutiveDashboardApp(db=db, config=test_config)
    assert app.current_theme == "Quiet Luxury"


# [verifies: UI-003/AC-UI-003.3]
def test_batch_folder_ingestion_and_inplace_refresh(tmp_path: Path, test_config):
    """Verify that batch ingestion integrates with the dashboard and updates data structures in-place."""
    db = Database(db_path=tmp_path / "test.db")
    app = ExecutiveDashboardApp(db=db, config=test_config)

    # Empty initial state
    assert len(db.get_all_monthly_statements()) == 0

    # Ingest a statement
    stmt = RentalStatement(
        statement_date="16/10/2026",
        reference="WGL230032",
        statement_number="1",
        gross_income=Decimal("1750.00"),
        expenditures=[],
        net_payout=Decimal("1750.00"),
    )
    db.save_monthly_statement(stmt, test_config.mortgage.monthly_direct_debit, Decimal("67000.00"))

    # Verify single-file, folder ingestion dialog entrypoints, tab switcher, and edit dialog are present
    assert hasattr(app, "open_single_file_ingest_dialog")
    assert hasattr(app, "open_ingest_dialog")
    assert hasattr(app, "switch_to_ledger_tab")
    assert hasattr(app, "open_edit_statement_dialog")

    # Mock tabs to test switch_to_ledger_tab for statements and invoices
    class DummyTab:
        def __init__(self, name):
            self.name = name

    class DummyTabs:
        def __init__(self):
            self.current_value = None

        def set_value(self, val):
            self.current_value = val

    app.main_tabs = DummyTabs()
    app.rent_tab = DummyTab("Rent Management")
    app.ledger_tabs = DummyTabs()
    app.stmt_tab = DummyTab("Monthly Statements")
    app.inv_tab = DummyTab("Contractor Invoices")

    # Test switching to statement tab
    app.switch_to_ledger_tab("statement")
    assert app.main_tabs.current_value == app.rent_tab
    assert app.ledger_tabs.current_value == app.stmt_tab

    # Test switching to invoice tab
    app.switch_to_ledger_tab("invoice")
    assert app.main_tabs.current_value == app.rent_tab
    assert app.ledger_tabs.current_value == app.inv_tab

    # In-place refresh updates data retrieval
    app.refresh_all()
    records = db.get_all_monthly_statements()
    assert len(records) == 1
    assert records[0]["statement_number"] == "1"


# [verifies: UI-003/AC-UI-003.4]
def test_current_month_progress_props(tmp_path: Path, test_config):
    """Verify formatting and calculations for current month financial performance box."""
    from src.ui.components import build_current_month_progress_props

    db = Database(db_path=tmp_path / "test.db")
    stmt = RentalStatement(
        statement_date="16/10/2026",
        reference="WGL230032",
        statement_number="13",
        gross_income=Decimal("1750.00"),
        expenditures=[
            ExpenditureLine(
                description="Agent fee", net=Decimal("150.00"), vat=Decimal("30.00"), gross=Decimal("180.00")
            )
        ],
        net_payout=Decimal("1570.00"),
    )
    db.save_monthly_statement(stmt, test_config.mortgage.monthly_direct_debit, Decimal("67000.00"))

    kpis = db.get_kpi_summary(default_mortgage_debit=test_config.mortgage.monthly_direct_debit)
    props = build_current_month_progress_props(kpis)

    assert props["gross_rent"] == "£1,750.00"
    assert props["expenses"] == "£180.00"
    assert props["net_earnings"] == "£1,570.00"
    assert props["shortfall"] == "£427.00"
    assert props["retention_percentage"] == "89.7%"
    assert props["expense_percentage"] == "10.3%"
    assert "89.7% Net Earning Retention" in props["bar_label"]


# [verifies: UI-003/AC-UI-003.4]
def test_current_month_multiple_statements_aggregated(tmp_path: Path, test_config):
    """Verify that current month section aggregates multiple statements occurring in the same calendar month."""
    from src.ui.components import build_current_month_progress_props

    db = Database(db_path=tmp_path / "test.db")
    # Statement 1 in October 2026: £1,750 rent, £1,178.10 expenses, £571.90 payout
    stmt1 = RentalStatement(
        statement_date="16/10/2026",
        reference="WGL230032",
        statement_number="13",
        gross_income=Decimal("1750.00"),
        total_expenditure=Decimal("1178.10"),
        expenditures=[
            ExpenditureLine(
                description="Agency fee", net=Decimal("175.00"), vat=Decimal("35.00"), gross=Decimal("210.00")
            ),
            ExpenditureLine(description="Repairs", net=Decimal("968.10"), vat=Decimal("0.00"), gross=Decimal("968.10")),
        ],
        net_payout=Decimal("571.90"),
    )
    # Statement 2 in October 2026 (adjustment): £426.87 rent, £71.60 expenses, £355.27 payout
    stmt2 = RentalStatement(
        statement_date="22/10/2026",
        reference="WGL230032",
        statement_number="14",
        gross_income=Decimal("426.87"),
        total_expenditure=Decimal("71.60"),
        expenditures=[
            ExpenditureLine(
                description="Adjustment fee", net=Decimal("59.67"), vat=Decimal("11.93"), gross=Decimal("71.60")
            ),
        ],
        net_payout=Decimal("355.27"),
    )
    db.save_monthly_statement(stmt1, test_config.mortgage.monthly_direct_debit, Decimal("47308.42"))
    db.save_monthly_statement(stmt2, Decimal("0.00"), Decimal("47308.42"))

    kpis = db.get_kpi_summary(default_mortgage_debit=test_config.mortgage.monthly_direct_debit)
    # Aggregated Gross: 1750.00 + 426.87 = 2176.87
    assert kpis["gross_rent"] == Decimal("2176.87")
    # Aggregated Expenses: 1178.10 + 71.60 = 1249.70
    assert kpis["total_deductions"] == Decimal("1249.70")
    # Aggregated Payout: 571.90 + 355.27 = 927.17
    assert kpis["net_payout"] == Decimal("927.17")
    # Monthly mortgage debit: 1997.00 exactly once
    assert kpis["mortgage_debit"] == Decimal("1997.00")
    # Shortfall: 1997.00 - 927.17 = 1069.83
    assert kpis["shortfall"] == Decimal("1069.83")

    props = build_current_month_progress_props(kpis)
    assert props["gross_rent"] == "£2,176.87"
    assert props["expenses"] == "£1,249.70"
    assert props["net_earnings"] == "£927.17"
    assert props["shortfall"] == "£1,069.83"
    assert "13, #14 (2 statements in 10/2026)" in props["statement_title"]


# [verifies: UI-003/AC-UI-003.5]
def test_portfolio_cumulative_summary_props(tmp_path: Path, test_config):
    """Verify cumulative calculations and formatting for all-time portfolio summary box."""
    from src.ui.components import build_portfolio_summary_progress_props

    db = Database(db_path=tmp_path / "test.db")
    stmt1 = RentalStatement(
        statement_date="16/09/2026",
        reference="WGL1",
        statement_number="1",
        gross_income=Decimal("1750.00"),
        expenditures=[
            ExpenditureLine(description="Fee", net=Decimal("100.00"), vat=Decimal("20.00"), gross=Decimal("120.00"))
        ],
        net_payout=Decimal("1630.00"),
    )
    stmt2 = RentalStatement(
        statement_date="16/10/2026",
        reference="WGL2",
        statement_number="2",
        gross_income=Decimal("1750.00"),
        expenditures=[
            ExpenditureLine(description="Fee", net=Decimal("200.00"), vat=Decimal("40.00"), gross=Decimal("240.00"))
        ],
        net_payout=Decimal("1510.00"),
    )
    db.save_monthly_statement(stmt1, test_config.mortgage.monthly_direct_debit, Decimal("68000.00"))
    db.save_monthly_statement(stmt2, test_config.mortgage.monthly_direct_debit, Decimal("67000.00"))

    summary = db.get_portfolio_cumulative_summary()
    assert summary["total_statements"] == 2
    assert summary["gross_rent"] == Decimal("3500.00")
    assert summary["total_deductions"] == Decimal("360.00")
    assert summary["net_earnings"] == Decimal("3140.00")

    props = build_portfolio_summary_progress_props(summary)
    assert props["gross_rent"] == "£3,500.00"
    assert props["expenses"] == "£360.00"
    assert props["net_earnings"] == "£3,140.00"
    assert props["shortfall"] == "£854.00"
    assert props["retention_percentage"] == "89.7%"
    assert props["expense_percentage"] == "10.3%"
    assert "89.7% Cumulative Earning Retention" in props["bar_label"]

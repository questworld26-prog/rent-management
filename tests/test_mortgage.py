"""TDD Test Suite for MORT-001 (Mortgage Terms Configuration & Progress Bar).
Bound to specifications in specs/finance/mortgage.md.
"""

from decimal import Decimal
from pathlib import Path

import pytest

from src.domain.models import (
    MortgageProgressBarState,
    MortgageTerms,
    RentalStatement,
)
from src.domain.mortgage import MortgageSchedule, calculate_mortgage_progress
from src.storage.database import Database


# [verifies: MORT-001/AC-MORT-001.1]
def test_calculate_mortgage_principal_payoff_percentage():
    """Verify principal repaid and percentage relative to deal initial principal without equity."""
    terms = MortgageTerms(
        monthly_direct_debit=Decimal("1997.00"),
        interest_rate=Decimal("4.25"),
        initial_principal=Decimal("203000.00"),
        remaining_principal=Decimal("195000.00"),
        fixed_deal_end_date="31-10-2028",
        effective_from="01-01-2026",
    )

    state: MortgageProgressBarState = calculate_mortgage_progress(terms)

    # Repaid = 203,000 - 195,000 = 8,000.00
    assert state.repaid_principal == Decimal("8000.00")
    # Repaid % = (8,000 / 203,000) * 100 = 3.94%
    assert state.repaid_percentage == Decimal("3.94")
    # Remaining Loan % = (195,000 / 203,000) * 100 = 96.06%
    assert state.remaining_loan_percentage == Decimal("96.06")
    assert state.remaining_principal == Decimal("195000.00")
    assert state.initial_principal == Decimal("203000.00")


# [verifies: MORT-001/AC-MORT-001.2]
def test_progress_bar_state_rendering_attributes():
    """Verify state provides exact values required to render the loan payoff progress bar without equity."""
    terms = MortgageTerms(
        monthly_direct_debit=Decimal("1997.00"),
        interest_rate=Decimal("4.25"),
        initial_principal=Decimal("200000.00"),
        remaining_principal=Decimal("180000.00"),
        fixed_deal_end_date="31-12-2027",
        effective_from="01-01-2026",
    )

    state: MortgageProgressBarState = calculate_mortgage_progress(terms, reference_date="17-10-2026")

    # Repaid = 200,000 - 180,000 = 20,000.00 (10.00%)
    assert state.repaid_percentage == Decimal("10.00")
    assert state.repaid_principal == Decimal("20000.00")
    assert state.remaining_loan_percentage == Decimal("90.00")
    assert state.remaining_principal == Decimal("180000.00")
    assert state.fixed_deal_days_remaining is not None
    assert state.fixed_deal_days_remaining > 0


# [verifies: MORT-001/AC-MORT-001.3]
def test_mortgage_terms_effective_date_versioning():
    """Where mortgage terms change over time, effective start dates ensure historical calculations remain unmodified."""
    schedule = MortgageSchedule()

    deal_2025 = MortgageTerms(
        monthly_direct_debit=Decimal("850.00"),
        interest_rate=Decimal("2.19"),
        initial_principal=Decimal("220000.00"),
        remaining_principal=Decimal("215000.00"),
        fixed_deal_end_date="31-12-2025",
        effective_from="01-01-2025",
        effective_to="31-12-2025",
    )
    schedule.add_terms(deal_2025)

    deal_2026 = MortgageTerms(
        monthly_direct_debit=Decimal("1997.00"),
        interest_rate=Decimal("4.25"),
        initial_principal=Decimal("203000.00"),
        remaining_principal=Decimal("203000.00"),
        fixed_deal_end_date="31-10-2028",
        effective_from="01-01-2026",
        effective_to=None,
    )
    schedule.add_terms(deal_2026)

    # When querying for a historical 2025 date:
    terms_in_2025 = schedule.get_terms_for_date("15-06-2025")
    assert terms_in_2025.monthly_direct_debit == Decimal("850.00")
    assert terms_in_2025.interest_rate == Decimal("2.19")

    # When querying for a 2026 date:
    terms_in_2026 = schedule.get_terms_for_date("15-06-2026")
    assert terms_in_2026.monthly_direct_debit == Decimal("1997.00")
    assert terms_in_2026.interest_rate == Decimal("4.25")


# [verifies: MORT-001/AC-MORT-001.4]
def test_sqlite_persistence_and_latest_balance_tracking(tmp_path: Path):
    """Verify recording monthly statement and loan balance in SQLite, and querying latest balance."""
    db_file = tmp_path / "test_rent.db"
    db = Database(db_file)

    statement = RentalStatement(
        statement_date="16-10-2026",
        reference="WGL230032",
        statement_number="13",
        gross_income=Decimal("1750.00"),
        expenditures=[],
        net_payout=Decimal("571.90"),
        file_hash="hash123",
    )

    # Initially, no balance recorded
    assert db.get_latest_mortgage_balance() is None

    # Save month 1
    db.save_monthly_statement(statement, mortgage_debit=Decimal("1997.00"), outstanding_balance=Decimal("202450.00"))
    assert db.get_latest_mortgage_balance() == Decimal("202450.00")

    # Save month 2
    statement2 = RentalStatement(
        statement_date="16-11-2026",
        reference="WGL230032",
        statement_number="14",
        gross_income=Decimal("1750.00"),
        expenditures=[],
        net_payout=Decimal("1435.00"),
        file_hash="hash456",
    )
    db.save_monthly_statement(statement2, mortgage_debit=Decimal("1997.00"), outstanding_balance=Decimal("201900.00"))
    assert db.get_latest_mortgage_balance() == Decimal("201900.00")


# [verifies: MORT-002/AC-MORT-002.1]
def test_mortgage_declining_balance_timeline():
    """AC-MORT-002.1: The system shall render an interactive timeline chart showing declining mortgage loan balance over time against initial balance."""
    from src.ui.components import prepare_mortgage_timeline_series

    records = [
        {"statement_date": "16-10-2026", "statement_number": "13", "outstanding_balance": "68000.00"},
        {"statement_date": "16-11-2026", "statement_number": "14", "outstanding_balance": "66250.00"},
    ]

    # 1. Historical-only timeline (project_to_zero=False)
    series_hist = prepare_mortgage_timeline_series(
        records=records,
        initial_principal=Decimal("70000.00"),
        monthly_direct_debit=Decimal("1997.00"),
        interest_rate=Decimal("4.30"),
        project_to_zero=False,
    )
    assert series_hist["categories"] == ["Initial", "Oct 2026", "Nov 2026"]
    assert series_hist["balance"] == [70000.0, 68000.0, 66250.0]
    assert series_hist["initial_benchmark"] == [70000.0, 70000.0, 70000.0]
    assert series_hist["principal_repaid"] == [0.0, 2000.0, 3750.0]

    # 2. Timeline with projection descending to £0.00 (project_to_zero=True)
    series_proj = prepare_mortgage_timeline_series(
        records=records,
        initial_principal=Decimal("70000.00"),
        monthly_direct_debit=Decimal("1997.00"),
        interest_rate=Decimal("4.30"),
        project_to_zero=True,
    )
    assert series_proj["categories"][:3] == ["Initial", "Oct 2026", "Nov 2026"]
    assert len(series_proj["categories"]) > 3
    assert series_proj["projected_balance"][-1] == 0.0
    assert series_proj["projected_balance"][0] == 70000.0


# [verifies: MORT-002/AC-MORT-002.2]
def test_mortgage_stacked_repayment_series():
    """AC-MORT-002.2: The system shall render a monthly stacked bar chart showing principal repayment vs interest charge vs landlord out-of-pocket cash paid."""
    from src.ui.components import prepare_mortgage_stacked_repayment_series

    records = [
        {
            "statement_date": "16-10-2026",
            "statement_number": "13",
            "mortgage_debit": "1997.00",
            "outstanding_balance": "68000.00",
            "calculated_shortfall": "427.00",
        }
    ]

    series = prepare_mortgage_stacked_repayment_series(
        records=records,
        interest_rate=Decimal("4.30"),
    )

    assert series["categories"] == ["Oct 2026"]
    assert len(series["principal"]) == 1
    assert len(series["interest"]) == 1
    assert len(series["out_of_pocket"]) == 1
    assert series["out_of_pocket"][0] == 427.00
    # Interest for 68,000 at 4.3% is ~243.67
    assert series["interest"][0] == pytest.approx(243.67, 0.05)
    # Principal is debit - interest: 1997 - 243.67 = 1753.33
    assert series["principal"][0] == pytest.approx(1753.33, 0.05)


# [verifies: MORT-002/AC-MORT-002.3]
def test_cumulative_comparison_series():
    """AC-MORT-002.3: The system shall render a cumulative comparison chart tracking cumulative gross rent collected vs cumulative mortgage payments and expenses."""
    from src.ui.components import prepare_cumulative_comparison_series

    records = [
        {
            "statement_date": "16-10-2026",
            "statement_number": "13",
            "gross_income": "1750.00",
            "total_expenditure": "180.00",
            "mortgage_debit": "1997.00",
        },
        {
            "statement_date": "16-11-2026",
            "statement_number": "14",
            "gross_income": "1750.00",
            "total_expenditure": "50.00",
            "mortgage_debit": "1997.00",
        },
    ]

    series = prepare_cumulative_comparison_series(records)
    assert series["categories"] == ["Oct 2026", "Nov 2026"]
    assert series["cumulative_rent"] == [1750.0, 3500.0]
    assert series["cumulative_mortgage"] == [1997.0, 3994.0]
    assert series["cumulative_expenses"] == [180.0, 230.0]
    assert series["cumulative_total_costs"] == [2177.0, 4224.0]


# [verifies: MORT-002/AC-MORT-002.4]
def test_consent_to_let_tracking_and_alert_status():
    """AC-MORT-002.4: Where Consent to Let is granted by the lender, the system shall track its start date, expiry date, days remaining, fee, and active compliance status."""
    from src.domain.mortgage import calculate_consent_to_let_status

    # Case 1: Active CTL with > 60 days
    ctl_active = calculate_consent_to_let_status(
        granted=True,
        start_date="01-11-2025",
        end_date="30-11-2026",
        fee=Decimal("150.00"),
        lender="Santander",
        reference_date="15-08-2026",
    )
    assert ctl_active.granted is True
    assert ctl_active.status == "ACTIVE"
    assert ctl_active.days_remaining is not None
    assert ctl_active.days_remaining > 60
    assert ctl_active.fee == Decimal("150.00")
    assert ctl_active.lender == "Santander"

    # Case 2: Expiring soon (within 60 days)
    ctl_expiring = calculate_consent_to_let_status(
        granted=True,
        start_date="01-11-2025",
        end_date="30-11-2026",
        reference_date="15-10-2026",
    )
    assert ctl_expiring.status == "EXPIRING_SOON"
    assert 0 <= ctl_expiring.days_remaining <= 60

    # Case 3: Expired
    ctl_expired = calculate_consent_to_let_status(
        granted=True,
        start_date="01-11-2024",
        end_date="01-11-2025",
        reference_date="15-10-2026",
    )
    assert ctl_expired.status == "EXPIRED"
    assert ctl_expired.days_remaining < 0

    # Case 4: Not configured
    ctl_none = calculate_consent_to_let_status(granted=False, start_date=None, end_date=None)
    assert ctl_none.status == "NOT_CONFIGURED"

    # Test format_countdown_years_months helper
    from src.ui.components import format_countdown_years_months

    # > 100 days should display years and months
    res_long = format_countdown_years_months(
        days_remaining=450,
        end_date_str="30-11-2027",
        reference_date="15-08-2026",
    )
    assert "year" in res_long or "month" in res_long
    assert "remaining" in res_long

    # <= 100 days should display days remaining
    res_short = format_countdown_years_months(days_remaining=45)
    assert res_short == "45 days remaining"

    # <= 0 days should display Expired
    assert format_countdown_years_months(days_remaining=0) == "Expired"

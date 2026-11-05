"""TDD Test Suite for CASH-001 (Monthly Mortgage Excess Calculation).
Bound to specifications in specs/finance/cashflow.md.
"""

from decimal import Decimal

from src.domain.cashflow import calculate_monthly_cashflow
from src.domain.models import (
    ExpenditureLine,
    MonthlyCashflowResult,
    MortgageTerms,
    RentalStatement,
)


# [verifies: CASH-001/AC-CASH-001.1]
def test_out_of_pocket_excess_when_net_rent_is_insufficient():
    """If net rental payment < mortgage direct debit, record positive shortfall as out_of_pocket_excess."""
    statement = RentalStatement(
        statement_date="16-10-2026",
        reference="WGL230032",
        statement_number="13",
        gross_income=Decimal("1750.00"),
        expenditures=[
            ExpenditureLine(description="Agency & Maintenance", net=Decimal("1178.10"), gross=Decimal("1178.10")),
        ],
        net_payout=Decimal("571.90"),
    )

    mortgage = MortgageTerms(
        monthly_direct_debit=Decimal("1000.00"),
        interest_rate=Decimal("4.25"),
        initial_principal=Decimal("203000.00"),
        remaining_principal=Decimal("203000.00"),
        fixed_deal_end_date="31-10-2028",
        effective_from="01-01-2026",
    )

    result: MonthlyCashflowResult = calculate_monthly_cashflow(statement=statement, mortgage=mortgage)

    assert result.net_rent_received == Decimal("571.90")
    assert result.mortgage_direct_debit == Decimal("1000.00")
    # Shortfall = 1000.00 - 571.90 = 428.10
    assert result.out_of_pocket_excess == Decimal("428.10")
    assert result.surplus_cashflow == Decimal("0.00")
    assert result.is_void_month is False


# [verifies: CASH-001/AC-CASH-001.2]
def test_surplus_cashflow_when_net_rent_exceeds_mortgage():
    """If net rental payment >= mortgage direct debit, out_of_pocket_excess is 0.00 and surplus is positive."""
    statement = RentalStatement(
        statement_date="16-11-2026",
        reference="WGL230032",
        statement_number="14",
        gross_income=Decimal("1750.00"),
        expenditures=[
            ExpenditureLine(description="Standard Agency Fee", net=Decimal("315.00"), gross=Decimal("315.00")),
        ],
        net_payout=Decimal("1435.00"),
    )

    mortgage = MortgageTerms(
        monthly_direct_debit=Decimal("1000.00"),
        interest_rate=Decimal("4.25"),
        initial_principal=Decimal("203000.00"),
        remaining_principal=Decimal("203000.00"),
        fixed_deal_end_date="31-10-2028",
        effective_from="01-01-2026",
    )

    result: MonthlyCashflowResult = calculate_monthly_cashflow(statement=statement, mortgage=mortgage)

    assert result.net_rent_received == Decimal("1435.00")
    assert result.mortgage_direct_debit == Decimal("1000.00")
    # Surplus = 1435.00 - 1000.00 = 435.00
    assert result.out_of_pocket_excess == Decimal("0.00")
    assert result.surplus_cashflow == Decimal("435.00")
    assert result.is_void_month is False


# [verifies: CASH-001/AC-CASH-001.3]
def test_void_month_full_mortgage_paid_out_of_pocket():
    """If no rental statement exists or net rent is zero, out_of_pocket_excess equals the full mortgage direct debit."""
    mortgage = MortgageTerms(
        monthly_direct_debit=Decimal("1000.00"),
        interest_rate=Decimal("4.25"),
        initial_principal=Decimal("203000.00"),
        remaining_principal=Decimal("203000.00"),
        fixed_deal_end_date="31-10-2028",
        effective_from="01-01-2026",
    )

    # Test Case A: statement is None (untenanted / void month)
    result_none: MonthlyCashflowResult = calculate_monthly_cashflow(statement=None, mortgage=mortgage, month="10-2026")
    assert result_none.net_rent_received == Decimal("0.00")
    assert result_none.out_of_pocket_excess == Decimal("1000.00")
    assert result_none.surplus_cashflow == Decimal("0.00")
    assert result_none.is_void_month is True

    # Test Case B: statement net payout is zero
    zero_stmt = RentalStatement(
        statement_date="16-12-2026",
        reference="WGL230032",
        statement_number="15",
        gross_income=Decimal("0.00"),
        expenditures=[],
        net_payout=Decimal("0.00"),
    )
    result_zero: MonthlyCashflowResult = calculate_monthly_cashflow(statement=zero_stmt, mortgage=mortgage)
    assert result_zero.out_of_pocket_excess == Decimal("1000.00")
    assert result_zero.surplus_cashflow == Decimal("0.00")
    assert result_zero.is_void_month is True


# [verifies: CASH-001/AC-CASH-001.4]
def test_decimal_penny_exact_precision():
    """All arithmetic operations must preserve penny precision using Python Decimal."""
    statement = RentalStatement(
        statement_date="16-10-2026",
        reference="WGL230032",
        statement_number="13",
        gross_income=Decimal("1750.33"),
        expenditures=[
            ExpenditureLine(description="Fee", net=Decimal("571.22"), gross=Decimal("571.22")),
        ],
        net_payout=Decimal("1179.11"),
    )

    mortgage = MortgageTerms(
        monthly_direct_debit=Decimal("1234.56"),
        interest_rate=Decimal("4.25"),
        initial_principal=Decimal("203000.00"),
        remaining_principal=Decimal("203000.00"),
        fixed_deal_end_date="31-10-2028",
        effective_from="01-01-2026",
    )

    result = calculate_monthly_cashflow(statement=statement, mortgage=mortgage)
    # Expected: 1234.56 - 1179.11 = 55.45
    assert result.out_of_pocket_excess == Decimal("55.45")
    assert isinstance(result.out_of_pocket_excess, Decimal)
    assert isinstance(result.surplus_cashflow, Decimal)

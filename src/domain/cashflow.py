"""Monthly cashflow and out-of-pocket shortfall calculation engine."""

from decimal import Decimal

from src.domain.models import MonthlyCashflowResult, MortgageTerms, RentalStatement


# [spec: CASH-001]
def calculate_monthly_cashflow(
    statement: RentalStatement | None,
    mortgage: MortgageTerms,
    month: str | None = None,
) -> MonthlyCashflowResult:
    """Calculate monthly landlord out-of-pocket excess or surplus cashflow.

    Implements CASH-001:
    - If net_payout < mortgage_direct_debit: positive shortfall as out_of_pocket_excess (AC-CASH-001.1).
    - If net_payout >= mortgage_direct_debit: out_of_pocket_excess is 0.00 and surplus is positive (AC-CASH-001.2).
    - If statement is None or net rent is 0: full mortgage direct debit is out_of_pocket_excess (AC-CASH-001.3).
    - All math preserves penny-exact Decimal precision (AC-CASH-001.4).
    """
    # Check if void / untenanted month
    if statement is None or statement.net_payout == Decimal("0.00"):
        return MonthlyCashflowResult(
            month=month or (statement.statement_date if statement else ""),
            gross_income=statement.gross_income if statement else Decimal("0.00"),
            total_deductions=statement.total_expenditure if statement else Decimal("0.00"),
            net_rent_received=Decimal("0.00"),
            mortgage_direct_debit=mortgage.monthly_direct_debit,
            out_of_pocket_excess=mortgage.monthly_direct_debit,
            surplus_cashflow=Decimal("0.00"),
            is_void_month=True,
        )

    net_rent = statement.net_payout
    mortgage_debit = mortgage.monthly_direct_debit

    if net_rent < mortgage_debit:
        out_of_pocket = mortgage_debit - net_rent
        surplus = Decimal("0.00")
    else:
        out_of_pocket = Decimal("0.00")
        surplus = net_rent - mortgage_debit

    return MonthlyCashflowResult(
        month=month or statement.statement_date,
        gross_income=statement.gross_income,
        total_deductions=statement.total_expenditure,
        net_rent_received=net_rent,
        mortgage_direct_debit=mortgage_debit,
        out_of_pocket_excess=out_of_pocket,
        surplus_cashflow=surplus,
        is_void_month=False,
    )

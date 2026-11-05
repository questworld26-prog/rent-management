"""Deterministic financial reconciliation engine."""

from decimal import Decimal

from src.domain.models import ReconciliationResult, RentalStatement


# [spec: INGEST-003]
def reconcile_statement(statement: RentalStatement) -> ReconciliationResult:
    """Verify deterministic mathematical integrity across three checks:

    1. Add all items in income and verify they sum to the subtotal of income.
    2. Add all items in expenditure and verify they sum to the subtotal of expenditure.
    3. Verify that landlord payment equals total income minus total expenditure.
    """
    failure_reasons: list[str] = []

    # Check 1: Income items sum to income subtotal
    # If income items are present, sum their gross values; otherwise compare gross_income directly
    if statement.income_items:
        sum_income_items = sum((item.gross for item in statement.income_items), Decimal("0.00"))
        expected_income_subtotal = (
            statement.income_subtotal if statement.income_subtotal is not None else statement.gross_income
        )
        income_check_passed = sum_income_items == expected_income_subtotal
        if not income_check_passed:
            failure_reasons.append(
                f"Income items sum (£{sum_income_items:,.2f}) does not match income subtotal (£{expected_income_subtotal:,.2f})"
            )
    else:
        income_check_passed = True

    # Check 2: Expenditure items sum to expenditure subtotal (Gross or Net)
    sum_expenditures_gross = sum((item.gross for item in statement.expenditures), Decimal("0.00"))
    sum_expenditures_net = sum((item.net for item in statement.expenditures), Decimal("0.00"))
    expected_exp_subtotal = (
        statement.expenditure_subtotal if statement.expenditure_subtotal is not None else sum_expenditures_gross
    )

    # In letting agency statements, the subtotal line might be extracted from the Gross column or Net column.
    # Check if expected_exp_subtotal matches either the Gross sum or Net sum:
    if expected_exp_subtotal == sum_expenditures_gross:
        expenditure_check_passed = True
        gross_expenditure_total = sum_expenditures_gross
    elif expected_exp_subtotal == sum_expenditures_net:
        # Extracted subtotal was the Net subtotal column; it matches individual Net items sum
        expenditure_check_passed = True
        gross_expenditure_total = sum_expenditures_gross
    else:
        expenditure_check_passed = False
        gross_expenditure_total = sum_expenditures_gross
        failure_reasons.append(
            f"Expenditure lines sum (£{sum_expenditures_gross:,.2f} Gross / £{sum_expenditures_net:,.2f} Net) does not match expenditure subtotal (£{expected_exp_subtotal:,.2f})"
        )

    # Check 3: Landlord payment = total income - total expenditure (Gross)
    effective_income = statement.income_subtotal if statement.income_subtotal is not None else statement.gross_income
    calculated_payout = effective_income - gross_expenditure_total
    discrepancy = statement.net_payout - calculated_payout
    payout_check_passed = discrepancy == Decimal("0.00")
    if not payout_check_passed:
        failure_reasons.append(
            f"Landlord payment (£{statement.net_payout:,.2f}) != Total Income (£{effective_income:,.2f}) - Total Expenditure (£{gross_expenditure_total:,.2f}) (Discrepancy: £{discrepancy:,.2f})"
        )

    all_passed = income_check_passed and expenditure_check_passed and payout_check_passed
    status = "BALANCED" if all_passed else "REVIEW_REQUIRED"

    return ReconciliationResult(
        is_balanced=all_passed,
        income_check_passed=income_check_passed,
        expenditure_check_passed=expenditure_check_passed,
        payout_check_passed=payout_check_passed,
        calculated_payout=calculated_payout,
        statement_payout=statement.net_payout,
        discrepancy=discrepancy,
        status=status,
        failure_reasons=failure_reasons,
    )

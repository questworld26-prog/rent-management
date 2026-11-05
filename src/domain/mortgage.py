"""Mortgage terms configuration, equity calculation, and progress bar engine."""

from datetime import datetime
from decimal import Decimal

from src.domain.models import MortgageProgressBarState, MortgageTerms

DATE_FORMAT = "%d-%m-%Y"


# [spec: MORT-001]
def parse_date(date_str: str) -> datetime:
    """Parse date string strictly in DD-MM-YYYY format."""
    return datetime.strptime(date_str, DATE_FORMAT)


# [spec: MORT-001]
def calculate_mortgage_progress(
    terms: MortgageTerms,
    reference_date: str | None = None,
    num_repayments: int = 0,
    interest_paid: Decimal | None = None,
) -> MortgageProgressBarState:
    """Calculate mortgage principal reduction, loan payoff percentage, and days remaining on fixed deal.

    Implements MORT-001:
    - Principal repaid = max(0, initial_principal - remaining_principal) (AC-MORT-001.1).
    - Repaid % = (repaid_principal / initial_principal) * 100 (AC-MORT-001.1).
    - Remaining loan % = (remaining_principal / initial_principal) * 100 (AC-MORT-001.2).
    - Fixed deal remaining days computed with DD-MM-YYYY date arithmetic.
    - Cumulative interest paid across repayments.
    """
    repaid_pounds = max(Decimal("0.00"), terms.initial_principal - terms.remaining_principal)

    if terms.initial_principal > Decimal("0.00"):
        repaid_pct = (repaid_pounds / terms.initial_principal) * Decimal("100.00")
        loan_pct = (terms.remaining_principal / terms.initial_principal) * Decimal("100.00")
    else:
        repaid_pct = Decimal("0.00")
        loan_pct = Decimal("0.00")

    days_remaining = None
    if terms.fixed_deal_end_date:
        ref_dt = parse_date(reference_date) if reference_date else datetime.now()
        end_dt = parse_date(terms.fixed_deal_end_date)
        delta = (end_dt - ref_dt).days
        days_remaining = max(0, delta)

    if interest_paid is None:
        if num_repayments > 0:
            interest_paid = calculate_amortized_interest_paid(
                terms.initial_principal, terms.monthly_direct_debit, terms.interest_rate, num_repayments
            )
        else:
            interest_paid = Decimal("0.00")

    return MortgageProgressBarState(
        initial_principal=terms.initial_principal.quantize(Decimal("0.01")),
        remaining_principal=terms.remaining_principal.quantize(Decimal("0.01")),
        repaid_principal=repaid_pounds.quantize(Decimal("0.01")),
        repaid_percentage=repaid_pct.quantize(Decimal("0.01")),
        remaining_loan_percentage=loan_pct.quantize(Decimal("0.01")),
        fixed_deal_days_remaining=days_remaining,
        interest_paid=interest_paid.quantize(Decimal("0.01")),
    )


# [spec: MORT-001]
def amortize_single_month(
    current_balance: Decimal,
    monthly_direct_debit: Decimal,
    annual_interest_rate_percent: Decimal,
) -> Decimal:
    """Calculate remaining mortgage principal balance after one month of direct debit repayment.

    Applies standard UK repayment mortgage amortization:
    - Monthly interest = current_balance * (annual_rate / 12)
    - Principal repaid = monthly_direct_debit - monthly_interest
    - New balance = max(0, current_balance - principal_repaid)
    """
    if current_balance <= Decimal("0.00"):
        return Decimal("0.00")

    monthly_rate = (annual_interest_rate_percent / Decimal("100.0")) / Decimal("12.0")
    monthly_interest = (current_balance * monthly_rate).quantize(Decimal("0.01"), rounding="ROUND_HALF_UP")
    principal_paid = monthly_direct_debit - monthly_interest
    new_balance = max(Decimal("0.00"), current_balance - principal_paid)
    return new_balance.quantize(Decimal("0.01"))


# [spec: MORT-001]
def calculate_amortized_monthly_balance(
    initial_principal: Decimal,
    monthly_direct_debit: Decimal,
    annual_interest_rate_percent: Decimal,
    num_repayments: int,
) -> Decimal:
    """Calculate remaining principal balance after a specified number of consecutive monthly repayments."""
    if num_repayments <= 0:
        return initial_principal

    balance = initial_principal
    for _ in range(num_repayments):
        balance = amortize_single_month(balance, monthly_direct_debit, annual_interest_rate_percent)
        if balance <= Decimal("0.00"):
            break

    return balance.quantize(Decimal("0.01"))


# [spec: MORT-001]
def calculate_amortized_interest_paid(
    initial_principal: Decimal,
    monthly_direct_debit: Decimal,
    annual_interest_rate_percent: Decimal,
    num_repayments: int,
) -> Decimal:
    """Calculate cumulative interest paid across a specified number of consecutive monthly repayments."""
    if num_repayments <= 0 or initial_principal <= Decimal("0.00"):
        return Decimal("0.00")

    balance = initial_principal
    monthly_rate = (annual_interest_rate_percent / Decimal("100.0")) / Decimal("12.0")
    total_interest = Decimal("0.00")

    for _ in range(num_repayments):
        if balance <= Decimal("0.00"):
            break
        interest = (balance * monthly_rate).quantize(Decimal("0.01"), rounding="ROUND_HALF_UP")
        principal = monthly_direct_debit - interest
        total_interest += interest
        balance = max(Decimal("0.00"), balance - principal)

    return total_interest.quantize(Decimal("0.01"))


# [spec: MORT-001]
class MortgageSchedule:
    """Registry maintaining historical mortgage terms with effective DD-MM-YYYY date windows."""

    def __init__(self):
        self.terms_list: list[MortgageTerms] = []

    def add_terms(self, terms: MortgageTerms) -> None:
        """Add a mortgage terms period to the schedule."""
        self.terms_list.append(terms)

    def get_terms_for_date(self, query_date: str) -> MortgageTerms:
        """Find the active mortgage terms for a specific DD-MM-YYYY date."""
        target_dt = parse_date(query_date)

        for terms in self.terms_list:
            start_dt = parse_date(terms.effective_from)
            end_dt = parse_date(terms.effective_to) if terms.effective_to else None

            if end_dt:
                if start_dt <= target_dt <= end_dt:
                    return terms
            else:
                if start_dt <= target_dt:
                    return terms

        if not self.terms_list:
            raise ValueError(f"No mortgage terms registered in schedule for date {query_date}")

        return self.terms_list[-1]


# [spec: MORT-002]
class ConsentToLetState:
    """Consent to Let compliance and expiration state."""

    def __init__(
        self,
        granted: bool,
        start_date: str | None = None,
        end_date: str | None = None,
        days_remaining: int | None = None,
        status: str = "NOT_CONFIGURED",  # ACTIVE | EXPIRING_SOON | EXPIRED | NOT_CONFIGURED
        fee: Decimal = Decimal("0.00"),
        lender: str | None = None,
    ):
        self.granted = granted
        self.start_date = start_date
        self.end_date = end_date
        self.days_remaining = days_remaining
        self.status = status
        self.fee = fee
        self.lender = lender


# [spec: MORT-002]
def calculate_consent_to_let_status(
    granted: bool,
    start_date: str | None,
    end_date: str | None,
    fee: Decimal = Decimal("0.00"),
    lender: str | None = None,
    reference_date: str | None = None,
) -> ConsentToLetState:
    """Compute Consent to Let compliance status, days remaining, and alert states.

    Implements AC-MORT-002.4:
    - If not granted: status = "NOT_CONFIGURED" or "NOT_GRANTED"
    - If granted and end_date provided:
        - If days_remaining < 0: status = "EXPIRED"
        - If 0 <= days_remaining <= 60: status = "EXPIRING_SOON"
        - If days_remaining > 60: status = "ACTIVE"
    """
    if not granted:
        return ConsentToLetState(
            granted=False,
            start_date=start_date,
            end_date=end_date,
            days_remaining=None,
            status="NOT_CONFIGURED",
            fee=fee,
            lender=lender,
        )

    if not end_date:
        return ConsentToLetState(
            granted=True,
            start_date=start_date,
            end_date=None,
            days_remaining=None,
            status="ACTIVE",
            fee=fee,
            lender=lender,
        )

    ref_dt = parse_date(reference_date) if reference_date else datetime.now()
    end_dt = parse_date(end_date)
    delta_days = (end_dt - ref_dt).days

    if delta_days < 0:
        status = "EXPIRED"
    elif delta_days <= 60:
        status = "EXPIRING_SOON"
    else:
        status = "ACTIVE"

    return ConsentToLetState(
        granted=True,
        start_date=start_date,
        end_date=end_date,
        days_remaining=delta_days,
        status=status,
        fee=fee,
        lender=lender,
    )

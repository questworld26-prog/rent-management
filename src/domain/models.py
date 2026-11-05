"""Domain data models for rental management."""

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field


# [spec: INGEST-001]
class IncomeLine(BaseModel):
    description: str
    net: Decimal
    vat: Decimal = Decimal("0.00")
    gross: Decimal

    @classmethod
    def from_raw(
        cls,
        description: str,
        net: str | float | Decimal,
        vat: str | float | Decimal = 0,
        gross: str | float | Decimal | None = None,
    ):
        net_dec = Decimal(str(net))
        vat_dec = Decimal(str(vat))
        gross_dec = Decimal(str(gross)) if gross is not None else net_dec + vat_dec
        return cls(description=description, net=net_dec, vat=vat_dec, gross=gross_dec)


# [spec: INGEST-001]
class ExpenditureLine(BaseModel):
    description: str
    net: Decimal
    vat: Decimal = Decimal("0.00")
    gross: Decimal

    @classmethod
    def from_raw(
        cls,
        description: str,
        net: str | float | Decimal,
        vat: str | float | Decimal = 0,
        gross: str | float | Decimal | None = None,
    ):
        net_dec = Decimal(str(net))
        vat_dec = Decimal(str(vat))
        gross_dec = Decimal(str(gross)) if gross is not None else net_dec + vat_dec
        return cls(description=description, net=net_dec, vat=vat_dec, gross=gross_dec)


# [spec: INGEST-001]
class RentalStatement(BaseModel):
    statement_date: str
    reference: str
    statement_number: str
    gross_income: Decimal
    income_subtotal: Decimal | None = None
    income_items: list[IncomeLine] = Field(default_factory=list)
    expenditures: list[ExpenditureLine] = Field(default_factory=list)
    expenditure_subtotal: Decimal | None = None
    net_payout: Decimal
    file_hash: str | None = None

    @property
    def total_expenditure(self) -> Decimal:
        return sum((item.gross for item in self.expenditures), Decimal("0.00"))

    @property
    def total_income_items(self) -> Decimal:
        if not self.income_items:
            return self.gross_income
        return sum((item.gross for item in self.income_items), Decimal("0.00"))


# [spec: INGEST-001]
class ContractorInvoice(BaseModel):
    contractor_name: str
    invoice_date: str
    invoice_number: str
    gross_amount: Decimal
    job_description: str | None = None
    line_items: list[str] = Field(default_factory=list)
    file_hash: str | None = None


# [spec: INGEST-006]
class DocumentCategory(StrEnum):
    RENTAL_STATEMENT = "RENTAL_STATEMENT"
    CONTRACTOR_INVOICE = "CONTRACTOR_INVOICE"
    COMPLIANCE_CERTIFICATE = "COMPLIANCE_CERTIFICATE"
    UNRECOGNIZED_DOCUMENT = "UNRECOGNIZED_DOCUMENT"


# [spec: INGEST-006]
class DocumentClassification(BaseModel):
    category: DocumentCategory
    confidence: float = 1.0
    reason: str = ""
    property_match: bool = True
    detected_reference: str | None = None
    detected_postcode: str | None = None


# [spec: INGEST-002]
class DuplicateType(StrEnum):
    EXACT_FILE_HASH = "EXACT_FILE_HASH"
    SEMANTIC_STATEMENT = "SEMANTIC_STATEMENT"
    SEMANTIC_INVOICE = "SEMANTIC_INVOICE"


# [spec: INGEST-002]
class DuplicateCheckResult(BaseModel):
    is_duplicate: bool
    duplicate_type: DuplicateType | None = None
    file_hash: str
    message: str = ""
    requires_user_confirmation: bool = False


# [spec: INGEST-003]
class ReconciliationResult(BaseModel):
    is_balanced: bool
    income_check_passed: bool = True
    expenditure_check_passed: bool = True
    payout_check_passed: bool = True
    calculated_payout: Decimal
    statement_payout: Decimal
    discrepancy: Decimal
    status: str  # BALANCED | REVIEW_REQUIRED
    failure_reasons: list[str] = Field(default_factory=list)


# [spec: MORT-001]
class MortgageTerms(BaseModel):
    monthly_direct_debit: Decimal
    interest_rate: Decimal
    remaining_principal: Decimal
    initial_principal: Decimal
    fixed_deal_end_date: str | None = None  # DD-MM-YYYY format
    effective_from: str  # DD-MM-YYYY format
    effective_to: str | None = None  # None for current active term


# [spec: MORT-001]
class MortgageProgressBarState(BaseModel):
    initial_principal: Decimal
    remaining_principal: Decimal
    repaid_principal: Decimal
    repaid_percentage: Decimal
    remaining_loan_percentage: Decimal
    fixed_deal_days_remaining: int | None = None
    interest_paid: Decimal = Decimal("0.00")


# [spec: CASH-001]
class MonthlyCashflowResult(BaseModel):
    month: str  # MM-YYYY or DD-MM-YYYY format
    gross_income: Decimal
    total_deductions: Decimal
    net_rent_received: Decimal
    mortgage_direct_debit: Decimal
    out_of_pocket_excess: Decimal
    surplus_cashflow: Decimal
    is_void_month: bool = False

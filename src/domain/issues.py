"""Domain models and business logic for property maintenance and repairs.
Bound to specifications in specs/operations/issues_maintenance.md:
- ISSUE-001: Auto-Detect & Suggest Maintenance Issues
- ISSUE-002: Maintenance Issue Lifecycle & Notes
"""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel
from pydantic import Field as PydanticField


# [spec: ISSUE-001]
# [spec: ISSUE-002]
class IssueStatus(StrEnum):
    OPEN = "Open"
    IN_PROGRESS = "In Progress"
    RESOLVED = "Resolved"


# [spec: ISSUE-001]
# [spec: ISSUE-002]
class IssuePriority(StrEnum):
    LOW = "Low"
    NORMAL = "Normal"
    URGENT = "Urgent"


# [spec: ISSUE-002]
class MaintenanceNote(BaseModel):
    id: int | None = None
    issue_id: int
    author: str = "Landlord"
    comment: str
    created_at: str = ""  # ISO formatted string or DD-MM-YYYY HH:MM:SS


# [spec: ISSUE-001]
# [spec: ISSUE-002]
class MaintenanceIssue(BaseModel):
    id: int | None = None
    title: str
    category: str = "General"
    status: IssueStatus = IssueStatus.OPEN
    priority: IssuePriority = IssuePriority.NORMAL
    contractor_name: str | None = None
    total_cost: Decimal = Decimal("0.00")
    reported_date: str = ""  # DD-MM-YYYY or DD/MM/YYYY
    resolved_date: str | None = None  # DD-MM-YYYY or DD/MM/YYYY
    resolution_note: str | None = None
    is_suggested: bool = False
    source_invoice_id: int | None = None
    pinned_invoices: list[dict[str, Any]] = PydanticField(default_factory=list)
    notes: list[MaintenanceNote] = PydanticField(default_factory=list)
    created_at: str = ""


# [spec: ISSUE-002]
def get_uk_financial_year_for_date(dt: datetime) -> tuple[datetime, datetime]:
    """Return the (start_date, end_date) for the UK financial year containing dt.

    In the UK, the tax year runs from 6 April of year Y to 5 April of year Y+1.
    """
    if (dt.month > 4) or (dt.month == 4 and dt.day >= 6):
        start_date = datetime(dt.year, 4, 6, 0, 0, 0)
        end_date = datetime(dt.year + 1, 4, 5, 23, 59, 59)
    else:
        start_date = datetime(dt.year - 1, 4, 6, 0, 0, 0)
        end_date = datetime(dt.year, 4, 5, 23, 59, 59)
    return start_date, end_date


# [spec: ISSUE-002]
def calculate_financial_year_maintenance_costs(
    issues: list[dict[str, Any]],
    reference_date: datetime | None = None,
) -> Decimal:
    """Calculate total incurred maintenance costs across all confirmed issues for the active UK financial year.

    Uses exact decimal.Decimal arithmetic.
    """
    ref_dt = reference_date or datetime.now()
    fy_start, fy_end = get_uk_financial_year_for_date(ref_dt)

    total = Decimal("0.00")
    for issue in issues:
        # Ignore unconfirmed suggestions
        if issue.get("is_suggested", False):
            continue

        date_str = issue.get("reported_date") or ""
        cleaned = date_str.strip().replace("/", "-")
        dt = None
        for fmt in ("%d-%m-%Y", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(cleaned, fmt)
                break
            except ValueError:
                pass

        # If date falls within active financial year, include cost
        if dt and fy_start <= dt <= fy_end:
            cost = Decimal(str(issue.get("total_cost", "0.00")))
            total += cost
        elif not dt:
            # If no date parseable, fallback include if non-empty
            cost = Decimal(str(issue.get("total_cost", "0.00")))
            total += cost

    return total.quantize(Decimal("0.01"))

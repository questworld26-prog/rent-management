"""Compliance & Certificates Domain Models and Business Logic.
Tracks statutory landlord compliance:
- Gas Safety (CP12)
- Electrical Installation Condition Report (EICR)
- Energy Performance Certificate (EPC)
- Landlord Insurance
- Annual Boiler Service
- Custom certificates

Enforces AC-COMP-001.1 through AC-COMP-001.5.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from src.domain.mortgage import parse_date


# [spec: COMP-001]
@dataclass
class ComplianceStatusResult:
    """Calculated compliance expiry and alert state."""

    days_remaining: int
    status: str  # 'VALID' | 'EXPIRING_SOON' | 'EXPIRED'
    status_label: str  # 'Valid' | 'Expiring Soon' | 'Expired'
    countdown_text: str  # e.g. '1 year 2 months remaining' or '48 days remaining'
    color_class: str


# [spec: COMP-001]
def calculate_compliance_status(
    expiry_date_str: str,
    reference_date: str | datetime | None = None,
) -> ComplianceStatusResult:
    """Calculate the compliance status for a certificate relative to a reference date.

    Implements AC-COMP-001.2, AC-COMP-001.3, AC-COMP-001.4:
    - If days_remaining < 0: status = 'EXPIRED' (Urgent red badge)
    - If 0 <= days_remaining <= 90: status = 'EXPIRING_SOON' (Flashing amber pill, within 3 months / 90 days)
    - If days_remaining > 90: status = 'VALID' (Calm green badge, more than 3 months remaining)
    """
    if isinstance(reference_date, datetime):
        ref_dt = reference_date
    elif isinstance(reference_date, str) and reference_date:
        ref_dt = parse_date(reference_date)
    else:
        ref_dt = datetime.now()

    expiry_dt = parse_date(expiry_date_str)
    delta_days = (expiry_dt - ref_dt).days

    if delta_days < 0:
        return ComplianceStatusResult(
            days_remaining=delta_days,
            status="EXPIRED",
            status_label="Expired",
            countdown_text=f"Expired ({abs(delta_days)} days overdue)",
            color_class="rose",
        )

    if delta_days <= 90:
        return ComplianceStatusResult(
            days_remaining=delta_days,
            status="EXPIRING_SOON",
            status_label="Expiring Soon",
            countdown_text=f"{delta_days} days remaining",
            color_class="amber",
        )

    # More than 90 days: VALID
    years = delta_days // 365
    rem_months = (delta_days % 365) // 30
    parts = []
    if years > 0:
        parts.append(f"{years} year" if years == 1 else f"{years} years")
    if rem_months > 0:
        parts.append(f"{rem_months} month" if rem_months == 1 else f"{rem_months} months")

    time_str = " ".join(parts) if parts else f"{delta_days} days"
    return ComplianceStatusResult(
        days_remaining=delta_days,
        status="VALID",
        status_label="Valid",
        countdown_text=f"{time_str} remaining ({delta_days} days)",
        color_class="emerald",
    )


# [spec: COMP-001]
def format_compliance_box_data(
    cert: dict[str, Any],
    reference_date: str | datetime | None = None,
) -> dict[str, Any]:
    """Format a certificate record for rendering in the dashboard grid box."""
    status_info = calculate_compliance_status(
        expiry_date_str=cert.get("expiry_date", ""),
        reference_date=reference_date,
    )
    cost_val = Decimal(str(cert.get("cost", "0.00")))

    return {
        "id": cert.get("id"),
        "certificate_type": cert.get("certificate_type", "General"),
        "title": cert.get("title", ""),
        "provider": cert.get("provider") or "Not Specified",
        "reference_number": cert.get("reference_number") or "N/A",
        "issue_date": cert.get("issue_date", ""),
        "expiry_date": cert.get("expiry_date", ""),
        "cost": cost_val,
        "cost_formatted": f"£{cost_val:,.2f}",
        "epc_rating": cert.get("epc_rating"),
        "file_path": cert.get("file_path"),
        "notes": cert.get("notes") or "",
        "days_remaining": status_info.days_remaining,
        "status": status_info.status,
        "status_label": status_info.status_label,
        "countdown_text": status_info.countdown_text,
        "color_class": status_info.color_class,
    }

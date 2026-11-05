from datetime import datetime
from decimal import Decimal
from typing import Any

from src.domain.models import MortgageProgressBarState


# [spec: UI-003]
def format_countdown_years_months(
    days_remaining: int | None,
    end_date_str: str | None = None,
    reference_date: str | None = None,
) -> str:
    """Format a countdown period into years and months if days > 100, otherwise days.

    Used for Fixed Deal Period and Consent to Let tracking countdowns.
    Examples:
    - 400 days -> '1 year 1 month remaining'
    - 730 days -> '2 years remaining'
    - 85 days -> '85 days remaining'
    - <= 0 days -> 'Expired / Overdue'
    """
    if days_remaining is None:
        return "N/A"
    if days_remaining <= 0:
        return "Expired"

    if days_remaining <= 100:
        return f"{days_remaining} days remaining"

    # For > 100 days, calculate years and months from dates if available or approx from days
    years = 0
    months = 0
    if end_date_str:
        try:
            sep = "/" if "/" in end_date_str else "-"
            parts = end_date_str.split(sep)
            if len(parts) == 3 and len(parts[0]) == 4:
                end_dt = datetime.strptime(end_date_str, f"%Y{sep}%m{sep}%d")
            else:
                end_dt = datetime.strptime(end_date_str, f"%d{sep}%m{sep}%Y")

            ref_dt = datetime.strptime(reference_date, "%d-%m-%Y") if reference_date else datetime.now()
            total_months = (end_dt.year - ref_dt.year) * 12 + (end_dt.month - ref_dt.month)
            if end_dt.day < ref_dt.day:
                total_months -= 1
            total_months = max(0, total_months)
            years = total_months // 12
            months = total_months % 12
        except Exception:
            years = days_remaining // 365
            months = (days_remaining % 365) // 30
    else:
        years = days_remaining // 365
        months = (days_remaining % 365) // 30

    parts_list = []
    if years > 0:
        parts_list.append(f"{years} year" if years == 1 else f"{years} years")
    if months > 0:
        parts_list.append(f"{months} month" if months == 1 else f"{months} months")

    if not parts_list:
        return f"{days_remaining} days remaining"

    return f"{' '.join(parts_list)} remaining"


# [spec: UI-003]
def format_remaining_term(
    end_date_str: str,
    days_remaining: int | None = None,
    reference_date: str | None = None,
) -> str:
    """Format remaining time on fixed rate mortgage deal.

    Rules:
    - If time left is >= 6 months: show number of years and months with total months in brackets,
      e.g. '1 yr 1 mo (13 mos)' or '2 yrs (24 mos)'
    - If time left is < 6 months: show months and days in brackets,
      e.g. '5 months (151 days)' or '1 month (34 days)' or '0 months (10 days)'
    - If expired: 'Expired'
    """
    if not end_date_str:
        return "N/A"
    try:
        end_dt = datetime.strptime(end_date_str, "%d-%m-%Y")
    except ValueError:
        return "N/A"

    ref_dt = datetime.strptime(reference_date, "%d-%m-%Y") if reference_date else datetime.now()
    delta_days = (end_dt - ref_dt).days if days_remaining is None else days_remaining

    if delta_days <= 0:
        return "Expired"

    # Calculate whole calendar months
    total_months = (end_dt.year - ref_dt.year) * 12 + (end_dt.month - ref_dt.month)
    if end_dt.day < ref_dt.day:
        total_months -= 1
    total_months = max(0, total_months)

    if total_months < 6:
        mo_label = "1 month" if total_months == 1 else f"{total_months} months"
        return f"{mo_label} ({delta_days} days)"

    years = total_months // 12
    rem_months = total_months % 12

    parts = []
    if years > 0:
        parts.append(f"{years} yr" if years == 1 else f"{years} yrs")
    if rem_months > 0:
        parts.append(f"{rem_months} mo" if rem_months == 1 else f"{rem_months} mos")

    time_str = " ".join(parts) if parts else "0 mos"
    mo_bracket = f"{total_months} mo" if total_months == 1 else f"{total_months} mos"
    return f"{time_str} ({mo_bracket})"


# [spec: UI-003]
def build_mortgage_progress_bar_props(
    progress: MortgageProgressBarState,
    fixed_deal_end_date: str = "",
    reference_date: str | None = None,
    monthly_direct_debit: Decimal = Decimal("1997.00"),
    interest_rate: Decimal = Decimal("4.30"),
    cumulative_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Calculate and format UI properties for the glowing loan payoff progress bar (zero equity)."""
    remaining_term = format_remaining_term(
        end_date_str=fixed_deal_end_date,
        days_remaining=progress.fixed_deal_days_remaining,
        reference_date=reference_date,
    )

    # Compute current monthly split
    if monthly_direct_debit > Decimal("0.00") and progress.remaining_principal > Decimal("0.00"):
        monthly_rate = (interest_rate / Decimal("100.0")) / Decimal("12.0")
        current_monthly_interest = (progress.remaining_principal * monthly_rate).quantize(
            Decimal("0.01"), rounding="ROUND_HALF_UP"
        )
        current_monthly_principal = max(Decimal("0.00"), monthly_direct_debit - current_monthly_interest)
        principal_split_pct = (current_monthly_principal / monthly_direct_debit) * Decimal("100.0")
        interest_split_pct = (current_monthly_interest / monthly_direct_debit) * Decimal("100.0")
    else:
        current_monthly_interest = Decimal("0.00")
        current_monthly_principal = monthly_direct_debit
        principal_split_pct = Decimal("100.0")
        interest_split_pct = Decimal("0.0")

    explanation_text = (
        f"In a UK capital repayment mortgage, each £{monthly_direct_debit:,.2f} payment is split between "
        f"Interest (lender's fee: {interest_split_pct:.1f}% · £{current_monthly_interest:,.2f}) and "
        f"Principal (loan debt reduction: {principal_split_pct:.1f}% · £{current_monthly_principal:,.2f}). "
        f"Over time, as the balance falls, each month's interest shrinks and the principal portion increases."
    )

    # Cumulative mortgage payment funding split: rental income vs out-of-pocket shortfall
    if cumulative_summary and cumulative_summary.get("mortgage_due", Decimal("0.00")) > Decimal("0.00"):
        total_mortgage = cumulative_summary.get("mortgage_due", Decimal("0.00"))
        total_earnings = cumulative_summary.get("net_earnings", Decimal("0.00"))
        total_shortfall = cumulative_summary.get("shortfall", Decimal("0.00"))
        rental_funding_pct = (total_earnings / total_mortgage) * Decimal("100.0")
        shortfall_funding_pct = (total_shortfall / total_mortgage) * Decimal("100.0")
    else:
        total_mortgage = Decimal("0.00")
        total_earnings = Decimal("0.00")
        total_shortfall = Decimal("0.00")
        rental_funding_pct = Decimal("0.0")
        shortfall_funding_pct = Decimal("0.0")

    return {
        "initial_principal": f"£{progress.initial_principal:,.2f}",
        "interest_paid": f"£{progress.interest_paid:,.2f}",
        "current_balance": f"£{progress.remaining_principal:,.2f}",
        "paid_off_amount": f"£{progress.repaid_principal:,.2f}",
        "paid_off_percentage": f"{progress.repaid_percentage:.1f}%",
        "progress_fraction": float(progress.repaid_percentage / Decimal("100.0")),
        "days_remaining": f"{progress.fixed_deal_days_remaining or 0} days",
        "remaining_term": remaining_term,
        "fixed_deal_end_date": fixed_deal_end_date,
        "monthly_direct_debit": f"£{monthly_direct_debit:,.2f}",
        "current_monthly_interest": f"£{current_monthly_interest:,.2f}",
        "current_monthly_principal": f"£{current_monthly_principal:,.2f}",
        "principal_split_pct": f"{principal_split_pct:.1f}%",
        "interest_split_pct": f"{interest_split_pct:.1f}%",
        "explanation_text": explanation_text,
        "total_mortgage_funded": f"£{total_mortgage:,.2f}",
        "rental_income_funded": f"£{total_earnings:,.2f}",
        "shortfall_funded": f"£{total_shortfall:,.2f}",
        "rental_funding_pct": f"{rental_funding_pct:.1f}%",
        "shortfall_funding_pct": f"{shortfall_funding_pct:.1f}%",
    }


# [spec: UI-001]
def format_kpi_card_data(kpis: dict[str, Any]) -> list[dict[str, Any]]:
    """Format the 4 executive summary cards for the latest month (Gross Rent, Expenses, Net Landlord Earning, Shortfall)."""
    gross = kpis.get("gross_rent", Decimal("0.00"))
    net = kpis.get("net_payout", Decimal("0.00"))
    expenses = kpis.get("total_deductions", Decimal("0.00"))
    shortfall = kpis.get("shortfall", Decimal("0.00"))

    is_shortfall = shortfall > Decimal("0.00")
    cashflow_val = shortfall if is_shortfall else kpis.get("surplus", Decimal("0.00"))
    cashflow_label = "Shortfall (Out-of-Pocket)" if is_shortfall else "Surplus Cashflow"
    cashflow_color = "coral" if is_shortfall else "emerald"

    stmt_num = kpis.get("latest_statement_number")
    stmt_date = kpis.get("latest_date")
    subtitle_stmt = f"Statement #{stmt_num} ({stmt_date})" if stmt_num and stmt_num != "N/A" else "Latest statement"

    return [
        {
            "id": "gross_rent",
            "title": "Gross Rent Received",
            "value": f"£{gross:,.2f}",
            "subtitle": subtitle_stmt,
            "color": "cyan",
            "icon": "payments",
        },
        {
            "id": "expenses",
            "title": "Expenses & Deductions",
            "value": f"£{expenses:,.2f}",
            "subtitle": "Agency fees & maintenance costs",
            "color": "amber",
            "icon": "receipt_long",
        },
        {
            "id": "net_payout",
            "alias_id": "net_earnings",
            "title": "Net Landlord Earning",
            "value": f"£{net:,.2f}",
            "subtitle": "Net income retained by landlord",
            "color": "emerald",
            "icon": "account_balance_wallet",
        },
        {
            "id": "cashflow_balance",
            "title": cashflow_label,
            "value": f"£{cashflow_val:,.2f}",
            "subtitle": f"Mortgage debit: £{kpis.get('mortgage_debit', Decimal('0.00')):,.2f}",
            "color": cashflow_color,
            "icon": "trending_down" if is_shortfall else "trending_up",
        },
    ]


# [spec: UI-003]
def build_current_month_progress_props(kpis: dict[str, Any]) -> dict[str, Any]:
    """Calculate and format UI properties for the current month financial performance box."""
    gross = kpis.get("gross_rent", Decimal("0.00"))
    net = kpis.get("net_payout", Decimal("0.00"))
    expenses = kpis.get("total_deductions", Decimal("0.00"))
    shortfall = kpis.get("shortfall", Decimal("0.00"))
    mortgage = kpis.get("mortgage_debit", Decimal("0.00"))

    stmt_num = kpis.get("latest_statement_number", "N/A")
    stmt_date = kpis.get("latest_date", "N/A")

    if gross > Decimal("0.00"):
        retention_pct = (net / gross) * Decimal("100.00")
        expense_pct = (expenses / gross) * Decimal("100.00")
    else:
        retention_pct = Decimal("0.00")
        expense_pct = Decimal("0.00")

    if stmt_num and stmt_num != "N/A":
        title = f"Statements #{stmt_num}" if "(" in str(stmt_num) else f"Statement #{stmt_num} ({stmt_date})"
    else:
        title = "Latest Statement"

    return {
        "statement_title": title,
        "gross_rent": f"£{gross:,.2f}",
        "expenses": f"£{expenses:,.2f}",
        "net_earnings": f"£{net:,.2f}",
        "shortfall": f"£{shortfall:,.2f}",
        "mortgage_debit": f"£{mortgage:,.2f}",
        "retention_percentage": f"{retention_pct:.1f}%",
        "expense_percentage": f"{expense_pct:.1f}%",
        "progress_fraction": float(min(Decimal("1.0"), max(Decimal("0.0"), retention_pct / Decimal("100.0")))),
        "bar_label": f"{retention_pct:.1f}% Net Earning Retention (£{net:,.2f} of £{gross:,.2f})",
    }


# [spec: UI-003]
def build_portfolio_summary_progress_props(summary: dict[str, Any]) -> dict[str, Any]:
    """Calculate and format UI properties for the all-time portfolio summary box."""
    total_stmts = summary.get("total_statements", 0)
    gross = summary.get("gross_rent", Decimal("0.00"))
    expenses = summary.get("total_deductions", Decimal("0.00"))
    earnings = summary.get("net_earnings", Decimal("0.00"))
    shortfall = summary.get("shortfall", Decimal("0.00"))
    retention_pct = summary.get("earning_retention_pct", Decimal("0.0"))
    expense_pct = summary.get("expense_ratio_pct", Decimal("0.0"))

    return {
        "summary_title": f"Portfolio All-Time Summary ({total_stmts} Statements Ingested)",
        "gross_rent": f"£{gross:,.2f}",
        "expenses": f"£{expenses:,.2f}",
        "net_earnings": f"£{earnings:,.2f}",
        "shortfall": f"£{shortfall:,.2f}",
        "retention_percentage": f"{retention_pct:.1f}%",
        "expense_percentage": f"{expense_pct:.1f}%",
        "progress_fraction": float(min(Decimal("1.0"), max(Decimal("0.0"), retention_pct / Decimal("100.0")))),
        "bar_label": f"{retention_pct:.1f}% Cumulative Earning Retention (£{earnings:,.2f} of £{gross:,.2f})",
    }


# [spec: UI-001]
# [spec: UI-001]
def prepare_statements_table_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Transform monthly record dictionaries into formatted table rows, consolidating multiple statements per calendar month."""
    if not records:
        return []

    # Group records by (YYYY, MM) using parse_date_to_datetime or string splitting
    grouped: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for r in records:
        dt = parse_date_to_datetime(r.get("statement_date", ""))
        key = (dt.year, dt.month) if dt else (0, 0)
        grouped.setdefault(key, []).append(r)

    rows = []
    # Sort groups chronologically
    sorted_keys = sorted(grouped.keys(), reverse=True)

    for key in sorted_keys:
        month_records = grouped[key]
        if len(month_records) == 1:
            r = month_records[0]
            gross = Decimal(str(r["gross_income"]))
            total_exp = Decimal(str(r["total_expenditure"]))
            payout = Decimal(str(r["net_payout"]))
            debit = Decimal(str(r["mortgage_debit"]))
            shortfall = Decimal(str(r.get("calculated_shortfall", "0.00")))
            shortfall_val = shortfall if shortfall > Decimal("0.00") else max(Decimal("0.00"), debit - payout)

            rows.append(
                {
                    "id": r["id"],
                    "statement_date": r["statement_date"],
                    "reference": r.get("reference") or "N/A",
                    "statement_number": f"#{r.get('statement_number', '')}",
                    "is_consolidated": False,
                    "statement_count": 1,
                    "gross_income": f"£{gross:,.2f}",
                    "total_expenditure": f"£{total_exp:,.2f}",
                    "net_payout": f"£{payout:,.2f}",
                    "mortgage_debit": f"£{debit:,.2f}",
                    "shortfall": f"£{shortfall_val:,.2f}" if shortfall_val > Decimal("0.00") else "£0.00 (Balanced)",
                    "raw_gross": float(gross),
                    "raw_exp": float(total_exp),
                    "raw_payout": float(payout),
                    "raw_shortfall": float(shortfall_val),
                    "expenditures": r.get("expenditures", []),
                    "sub_statements": [r],
                }
            )
        else:
            # Consolidated multi-statement month
            # Sort individual statements within month by date and statement_number
            month_records.sort(
                key=lambda rec: (
                    parse_date_to_datetime(rec.get("statement_date", "")) or datetime.min,
                    int(rec.get("statement_number") or 0) if str(rec.get("statement_number", "")).isdigit() else 0,
                    rec.get("id", 0),
                )
            )

            tot_gross = sum((Decimal(str(r["gross_income"])) for r in month_records), Decimal("0.00"))
            tot_exp = sum((Decimal(str(r["total_expenditure"])) for r in month_records), Decimal("0.00"))
            tot_payout = sum((Decimal(str(r["net_payout"])) for r in month_records), Decimal("0.00"))
            # For direct debit in a consolidated calendar month, take the monthly direct debit of the primary statement (or max)
            monthly_debit = max([Decimal(str(r["mortgage_debit"])) for r in month_records], default=Decimal("0.00"))
            consolidated_shortfall = max(Decimal("0.00"), monthly_debit - tot_payout)

            # Format month display e.g. "Oct 2026"
            dt_sample = parse_date_to_datetime(month_records[0].get("statement_date", ""))
            month_label = dt_sample.strftime("%b %Y") if dt_sample else month_records[0].get("statement_date", "")

            # Combined references e.g. "WGL230032"
            refs = sorted(list({r.get("reference") for r in month_records if r.get("reference")}))
            ref_label = ", ".join(refs) if refs else "N/A"

            # All expenditures combined
            all_expenditures = []
            for r in month_records:
                for exp in r.get("expenditures", []):
                    exp_copy = dict(exp)
                    exp_copy["source_statement"] = f"#{r.get('statement_number')}"
                    all_expenditures.append(exp_copy)

            stmt_nums = [f"#{r.get('statement_number')}" for r in month_records]
            stmt_label = f"{len(month_records)} Statements ({', '.join(stmt_nums)})"

            rows.append(
                {
                    "id": month_records[0]["id"],
                    "statement_date": month_label,
                    "reference": ref_label,
                    "statement_number": stmt_label,
                    "is_consolidated": True,
                    "statement_count": len(month_records),
                    "gross_income": f"£{tot_gross:,.2f}",
                    "total_expenditure": f"£{tot_exp:,.2f}",
                    "net_payout": f"£{tot_payout:,.2f}",
                    "mortgage_debit": f"£{monthly_debit:,.2f}",
                    "shortfall": f"£{consolidated_shortfall:,.2f}"
                    if consolidated_shortfall > Decimal("0.00")
                    else "£0.00 (Balanced)",
                    "raw_gross": float(tot_gross),
                    "raw_exp": float(tot_exp),
                    "raw_payout": float(tot_payout),
                    "raw_shortfall": float(consolidated_shortfall),
                    "expenditures": all_expenditures,
                    "sub_statements": month_records,
                }
            )

    return rows


# [spec: UI-001]
def is_management_cost(description: str) -> bool:
    """Determine if an expenditure item is an agency management, letting fee, or deposit scheme cost."""
    desc = description.lower()
    keywords = [
        "letting fee",
        "letting fees",
        "management fee",
        "management fees",
        "tenancy deposit",
        "deposit scheme",
        "tds",
    ]
    return any(kw in desc for kw in keywords)


# [spec: UI-001]
def partition_statement_expenditures(
    expenditures: list[dict[str, Any]],
) -> dict[str, Any]:
    """Partition statement expenditures into Management Costs and Property Maintenance Expenses with totals."""
    mgmt_items: list[dict[str, Any]] = []
    expense_items: list[dict[str, Any]] = []

    for item in expenditures:
        desc = item.get("description", "")
        if is_management_cost(desc):
            mgmt_items.append(item)
        else:
            expense_items.append(item)

    total_mgmt = sum((Decimal(str(i.get("gross", "0.00"))) for i in mgmt_items), Decimal("0.00"))
    total_expenses = sum((Decimal(str(i.get("gross", "0.00"))) for i in expense_items), Decimal("0.00"))
    total_deductions = total_mgmt + total_expenses

    return {
        "management_costs": mgmt_items,
        "direct_expenses": expense_items,
        "total_management_costs": total_mgmt,
        "total_direct_expenses": total_expenses,
        "total_deductions": total_deductions,
    }


# [spec: UI-002]
def prepare_invoices_table_rows(invoices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Transform contractor invoice records into formatted table rows with deduction match status."""
    from src.storage.database import normalize_date_to_dmy

    rows = []
    for inv in invoices:
        gross = Decimal(inv["gross_amount"])
        formatted_date = normalize_date_to_dmy(inv.get("invoice_date", ""))
        rows.append(
            {
                "id": inv["id"],
                "contractor_name": inv["contractor_name"],
                "invoice_date": formatted_date,
                "invoice_number": inv["invoice_number"],
                "gross_amount": f"£{gross:,.2f}",
                "raw_amount": float(gross),
                "job_description": inv.get("job_description") or "Standard contractor repair / maintenance",
                "is_deduction_matched": inv.get("is_deduction_matched", False),
            }
        )
    return rows


# [spec: UI-001]
def parse_date_to_datetime(date_str: str) -> datetime | None:
    """Parse date string in DD/MM/YYYY, DD-MM-YYYY, or YYYY-MM-DD format."""
    if not date_str:
        return None
    cleaned = date_str.strip().replace("/", "-")
    for fmt in ("%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            pass
    return None


# [spec: UI-001]
def prepare_chart_series(
    records: list[dict[str, Any]],
    default_mortgage_debit: Decimal = Decimal("1997.00"),
) -> dict[str, Any]:
    """Generate continuous chronological time-series points without gaps (Month and Year on X-axis)."""
    if not records:
        return {"categories": [], "gross": [], "deductions": [], "payout": [], "shortfall": []}

    parsed_records = []
    for r in records:
        dt = parse_date_to_datetime(r.get("statement_date", ""))
        if dt:
            parsed_records.append((dt, r))

    if not parsed_records:
        return {"categories": [], "gross": [], "deductions": [], "payout": [], "shortfall": []}

    parsed_records.sort(key=lambda x: x[0])
    first_dt = parsed_records[0][0]
    last_dt = parsed_records[-1][0]

    # Generate continuous sequence of (year, month) from first to last without gaps
    year_months: list[tuple[int, int]] = []
    cy, cm = first_dt.year, first_dt.month
    ey, em = last_dt.year, last_dt.month
    while (cy < ey) or (cy == ey and cm <= em):
        year_months.append((cy, cm))
        cm += 1
        if cm > 12:
            cm = 1
            cy += 1

    categories = []
    gross_data = []
    deductions_data = []
    payout_data = []
    shortfall_data = []

    for y, m in year_months:
        dt_label = datetime(y, m, 1).strftime("%b %Y")
        matching = [r for (dt, r) in parsed_records if dt.year == y and dt.month == m]

        if matching:
            month_gross = sum(Decimal(r["gross_income"]) for r in matching)
            month_exp = sum(Decimal(r["total_expenditure"]) for r in matching)
            month_payout = sum(Decimal(r["net_payout"]) for r in matching)
            debit = max(Decimal(r.get("mortgage_debit", default_mortgage_debit)) for r in matching)
            month_shortfall = max(Decimal("0.00"), debit - month_payout)
        else:
            month_gross = Decimal("0.00")
            month_exp = Decimal("0.00")
            month_payout = Decimal("0.00")
            month_shortfall = default_mortgage_debit

        categories.append(dt_label)
        gross_data.append(float(month_gross))
        deductions_data.append(float(month_exp))
        payout_data.append(float(month_payout))
        shortfall_data.append(float(month_shortfall))

    return {
        "categories": categories,
        "gross": gross_data,
        "deductions": deductions_data,
        "payout": payout_data,
        "shortfall": shortfall_data,
    }


# [spec: ISSUE-001]
# [spec: ISSUE-002]
def prepare_maintenance_table_rows(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Format maintenance issues for UI display and data table representation."""
    rows = []
    for issue in issues:
        cost = Decimal(str(issue.get("total_cost", "0.00")))
        pinned = issue.get("pinned_invoices") or []
        notes = issue.get("notes") or []
        rows.append(
            {
                "id": issue["id"],
                "title": issue["title"],
                "category": issue.get("category", "General"),
                "status": issue.get("status", "Open"),
                "priority": issue.get("priority", "Normal"),
                "contractor_name": issue.get("contractor_name") or "None assigned",
                "cost_formatted": f"£{cost:,.2f}",
                "total_cost": float(cost),
                "reported_date": issue.get("reported_date") or "N/A",
                "resolved_date": issue.get("resolved_date") or "—",
                "resolution_note": issue.get("resolution_note") or "",
                "is_suggested": bool(issue.get("is_suggested", 0)),
                "pinned_invoices_count": len(pinned),
                "notes_count": len(notes),
                "pinned_invoices": pinned,
                "notes": notes,
            }
        )
    return rows


# [spec: MORT-002]
def prepare_mortgage_timeline_series(
    records: list[dict[str, Any]],
    initial_principal: Decimal,
    monthly_direct_debit: Decimal,
    interest_rate: Decimal,
    project_to_zero: bool = True,
) -> dict[str, Any]:
    """Prepare interactive timeline data showing declining mortgage balance against initial balance over time,
    with an optional projected amortization trajectory descending down to £0.00.

    Implements AC-MORT-002.1.
    """
    from src.domain.mortgage import amortize_single_month

    if not records:
        return {
            "categories": ["Initial"],
            "balance": [float(initial_principal)],
            "initial_benchmark": [float(initial_principal)],
            "principal_repaid": [0.0],
            "projected_balance": [float(initial_principal)],
        }

    categories = ["Initial"]
    balance_data: list[float | None] = [float(initial_principal)]
    benchmark_data = [float(initial_principal)]
    repaid_data = [0.0]

    last_dt = None
    latest_bal = initial_principal

    for r in records:
        date_str = r.get("statement_date", "")
        dt = parse_date_to_datetime(date_str)
        if dt:
            last_dt = dt
        label = dt.strftime("%b %Y") if dt else f"Stmt #{r.get('statement_number')}"
        categories.append(label)

        bal = Decimal(str(r.get("outstanding_balance") or initial_principal))
        latest_bal = bal
        repaid = max(Decimal("0.00"), initial_principal - bal)

        balance_data.append(float(bal))
        benchmark_data.append(float(initial_principal))
        repaid_data.append(float(repaid))

    projected_balance_data: list[float | None] = list(balance_data)

    # If requested and direct debit > 0, project future months down to £0.00
    if project_to_zero and monthly_direct_debit > Decimal("0.00") and latest_bal > Decimal("0.00"):
        proj_bal = latest_bal
        cur_year = last_dt.year if last_dt else 2026
        cur_month = last_dt.month if last_dt else 1

        # Project month by month until balance hits 0 or max 360 months
        max_proj_months = 360
        count = 0
        while proj_bal > Decimal("0.00") and count < max_proj_months:
            count += 1
            cur_month += 1
            if cur_month > 12:
                cur_month = 1
                cur_year += 1

            proj_bal = amortize_single_month(proj_bal, monthly_direct_debit, interest_rate)
            label = datetime(cur_year, cur_month, 1).strftime("%b %Y")
            categories.append(label)
            balance_data.append(None)  # Actual historical series stops
            benchmark_data.append(float(initial_principal))
            repaid_data.append(float(max(Decimal("0.00"), initial_principal - proj_bal)))
            projected_balance_data.append(float(proj_bal))

        projected_end_date = datetime(cur_year, cur_month, 1).strftime("%b %Y") if proj_bal <= Decimal("0.00") else None
    else:
        projected_end_date = None

    return {
        "categories": categories,
        "balance": balance_data,
        "initial_benchmark": benchmark_data,
        "principal_repaid": repaid_data,
        "projected_balance": projected_balance_data,
        "projected_end_date": projected_end_date,
    }


# [spec: MORT-002]
def prepare_mortgage_stacked_repayment_series(
    records: list[dict[str, Any]],
    interest_rate: Decimal,
) -> dict[str, Any]:
    """Prepare monthly stacked bar series for principal repayment vs interest charge vs landlord out-of-pocket cash paid.

    Implements AC-MORT-002.2.
    """
    categories = []
    principal_data = []
    interest_data = []
    out_of_pocket_data = []

    monthly_rate = (interest_rate / Decimal("100.0")) / Decimal("12.0")

    for r in records:
        date_str = r.get("statement_date", "")
        dt = parse_date_to_datetime(date_str)
        label = dt.strftime("%b %Y") if dt else f"#{r.get('statement_number')}"
        categories.append(label)

        debit = Decimal(str(r.get("mortgage_debit", "0.00")))
        bal = Decimal(str(r.get("outstanding_balance", "0.00")))
        interest = (bal * monthly_rate).quantize(Decimal("0.01"), rounding="ROUND_HALF_UP")
        principal = max(Decimal("0.00"), debit - interest)
        shortfall = Decimal(str(r.get("calculated_shortfall", "0.00")))

        principal_data.append(float(principal))
        interest_data.append(float(interest))
        out_of_pocket_data.append(float(shortfall))

    return {
        "categories": categories,
        "principal": principal_data,
        "interest": interest_data,
        "out_of_pocket": out_of_pocket_data,
    }


# [spec: MORT-002]
def prepare_cumulative_comparison_series(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Prepare cumulative comparison series: cumulative gross rent vs cumulative mortgage payments and expenses.

    Implements AC-MORT-002.3.
    """
    categories = []
    cum_rent = []
    cum_mortgage = []
    cum_expenses = []
    cum_total_costs = []

    running_rent = Decimal("0.00")
    running_mortgage = Decimal("0.00")
    running_expenses = Decimal("0.00")

    for r in records:
        date_str = r.get("statement_date", "")
        dt = parse_date_to_datetime(date_str)
        label = dt.strftime("%b %Y") if dt else f"#{r.get('statement_number')}"
        categories.append(label)

        running_rent += Decimal(str(r.get("gross_income", "0.00")))
        running_mortgage += Decimal(str(r.get("mortgage_debit", "0.00")))
        running_expenses += Decimal(str(r.get("total_expenditure", "0.00")))

        cum_rent.append(float(running_rent))
        cum_mortgage.append(float(running_mortgage))
        cum_expenses.append(float(running_expenses))
        cum_total_costs.append(float(running_mortgage + running_expenses))

    return {
        "categories": categories,
        "cumulative_rent": cum_rent,
        "cumulative_mortgage": cum_mortgage,
        "cumulative_expenses": cum_expenses,
        "cumulative_total_costs": cum_total_costs,
    }

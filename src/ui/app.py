"""NiceGUI Executive Rent Management Dashboard Application.
Bound to specifications:
- UI-001: Monthly Statements Ledger & Trend Graphs
- UI-002: Contractor Invoices Ledger & Maintenance Items
- UI-003: Executive Quiet Luxury Design System & Loan Payoff Progress
"""

import asyncio
import logging
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from nicegui import ui

from src.config import AppConfig, load_config
from src.domain.compliance import (
    format_compliance_box_data,
)
from src.domain.issues import (
    calculate_financial_year_maintenance_costs,
)
from src.domain.models import MortgageTerms
from src.domain.mortgage import (
    calculate_amortized_interest_paid,
    calculate_amortized_monthly_balance,
    calculate_consent_to_let_status,
    calculate_mortgage_progress,
)
from src.ingestion.batch import BatchIngestionService
from src.storage.database import Database
from src.ui.components import (
    build_current_month_progress_props,
    build_mortgage_progress_bar_props,
    build_portfolio_summary_progress_props,
    format_countdown_years_months,
    format_kpi_card_data,
    partition_statement_expenditures,
    prepare_chart_series,
    prepare_cumulative_comparison_series,
    prepare_invoices_table_rows,
    prepare_maintenance_table_rows,
    prepare_mortgage_stacked_repayment_series,
    prepare_mortgage_timeline_series,
    prepare_statements_table_rows,
)
from src.ui.theme import DEFAULT_THEME, THEMES, get_theme_css

logger = logging.getLogger(__name__)


# [spec: UI-003]
class ExecutiveDashboardApp:
    """Single-property Executive Rental Management Dashboard."""

    def __init__(self, db: Database, config: AppConfig):
        self.db = db
        self.config = config
        self.current_theme = DEFAULT_THEME

        # Containers for in-place reactive refreshing
        self.progress_container = None
        self.current_month_container = None
        self.portfolio_summary_container = None
        self.kpi_container = None
        self.chart_container = None
        self.statements_container = None
        self.invoices_container = None
        self.issues_container = None
        self.compliance_container = None
        self.mortgage_container = None
        self.theme_style_tag = None
        # Primary and ledger tab controllers for dynamic navigation
        self.main_tabs = None
        self.rent_tab = None
        self.ledger_tabs = None
        self.stmt_tab = None
        self.inv_tab = None

    # [spec: UI-003]
    def switch_to_ledger_tab(self, doc_type: str = "statement") -> None:
        """Navigate automatically to the Rent Management tab and select the corresponding ledger subtab."""
        try:
            if self.main_tabs and self.rent_tab:
                self.main_tabs.set_value(self.rent_tab)
            if self.ledger_tabs:
                if doc_type == "invoice" and self.inv_tab:
                    self.ledger_tabs.set_value(self.inv_tab)
                elif self.stmt_tab:
                    self.ledger_tabs.set_value(self.stmt_tab)
        except Exception as exc:
            logger.debug("Failed switching to ledger tab: %s", exc)

    # [spec: UI-003]
    def set_theme(self, theme_name: str) -> None:
        """Switch active theme dynamically in-place."""
        self.current_theme = theme_name
        tokens = THEMES.get(theme_name, THEMES[DEFAULT_THEME])
        css = get_theme_css(theme_name)
        if self.theme_style_tag:
            self.theme_style_tag.set_content(f"<style id='theme-styles'>{css}</style>")

        # Inject CSS properties into documentElement so all theme variables update immediately in browser
        js_cmd = "; ".join(
            [
                f"document.documentElement.style.setProperty('--bg-main', '{tokens.bg_main}')",
                f"document.documentElement.style.setProperty('--bg-card', '{tokens.bg_card}')",
                f"document.documentElement.style.setProperty('--bg-card-alt', '{tokens.bg_card_alt}')",
                f"document.documentElement.style.setProperty('--text-primary', '{tokens.text_primary}')",
                f"document.documentElement.style.setProperty('--text-secondary', '{tokens.text_secondary}')",
                f"document.documentElement.style.setProperty('--text-muted', '{tokens.text_muted}')",
                f"document.documentElement.style.setProperty('--accent-emerald', '{tokens.accent_emerald}')",
                f"document.documentElement.style.setProperty('--accent-cyan', '{tokens.accent_cyan}')",
                f"document.documentElement.style.setProperty('--accent-amber', '{tokens.accent_amber}')",
                f"document.documentElement.style.setProperty('--accent-coral', '{tokens.accent_coral}')",
                f"document.documentElement.style.setProperty('--border-color', '{tokens.border_color}')",
                f"document.documentElement.style.setProperty('--glow-color', '{tokens.glow_color}')",
                f"document.body.style.backgroundColor = '{tokens.bg_main}'",
            ]
        )
        ui.run_javascript(js_cmd)
        self.refresh_all()
        ui.notify(f"Theme switched to {theme_name}", type="info", position="top")

    # [spec: UI-003]
    def calculate_current_mortgage_progress(self):
        """Compute loan reduction progress using latest database balance or amortized schedule."""
        statements = self.db.get_all_monthly_statements()
        latest_balance = self.db.get_latest_mortgage_balance()
        num_repayments = len(statements)

        if (latest_balance is None or latest_balance == self.config.mortgage.initial_principal) and statements:
            current_bal = calculate_amortized_monthly_balance(
                initial_principal=self.config.mortgage.initial_principal,
                monthly_direct_debit=self.config.mortgage.monthly_direct_debit,
                annual_interest_rate_percent=self.config.mortgage.interest_rate,
                num_repayments=num_repayments,
            )
        else:
            current_bal = latest_balance if latest_balance is not None else self.config.mortgage.initial_principal

        interest_paid = calculate_amortized_interest_paid(
            initial_principal=self.config.mortgage.initial_principal,
            monthly_direct_debit=self.config.mortgage.monthly_direct_debit,
            annual_interest_rate_percent=self.config.mortgage.interest_rate,
            num_repayments=num_repayments,
        )

        terms = MortgageTerms(
            monthly_direct_debit=self.config.mortgage.monthly_direct_debit,
            interest_rate=self.config.mortgage.interest_rate,
            remaining_principal=current_bal,
            initial_principal=self.config.mortgage.initial_principal,
            fixed_deal_end_date=self.config.mortgage.fixed_deal_end_date,
            effective_from=self.config.mortgage.effective_from,
        )
        return calculate_mortgage_progress(terms, num_repayments=num_repayments, interest_paid=interest_paid)

    # [spec: UI-003]
    def render_top_bar(self) -> None:
        """Render executive top navigation bar with Quiet Luxury styling matching Image 3 and 4."""
        with (
            ui.header()
            .classes(
                "w-full theme-header px-8 py-3.5 items-center justify-between !bg-[#121622]/95 backdrop-blur-md !text-[#fdfbf7] border-b border-[#e5c07b]/25 shadow-md"
            )
            .style(
                "background: rgba(18, 22, 34, 0.95) !important; background-color: rgba(18, 22, 34, 0.95) !important;"
            )
        ):
            with ui.row().classes("items-center gap-3"):
                ui.label("RENTAL MANAGEMENT EXECUTIVE DASHBOARD").classes(
                    "text-xl font-bold tracking-wider text-[#fdfbf7] executive-title"
                )

            with ui.row().classes("items-center gap-3"):
                with ui.element("div").classes(
                    "px-4 py-1.5 rounded-full bg-gradient-to-r from-[#e5c07b] to-[#d4af37] text-[#0e1015] "
                    "text-xs font-black tracking-widest shadow-md flex items-center gap-1.5 cursor-default select-none"
                ):
                    ui.icon("verified_user", size="xs").classes("text-[#0e1015]")
                    ui.label("PRIVATE LOCAL").classes("text-xs font-black tracking-widest text-[#0e1015]")

                # Ingestion Triggers (File & Folder)
                ui.button(
                    "Ingest File",
                    icon="note_add",
                    on_click=self.open_single_file_ingest_dialog,
                ).props("flat dense").classes(
                    "text-xs font-semibold text-[#e5c07b] border border-[#e5c07b]/30 hover:bg-[#e5c07b]/10 px-3 py-1.5 rounded-lg"
                )

                ui.button(
                    "Ingest Folder",
                    icon="folder_open",
                    on_click=self.open_ingest_dialog,
                ).props("flat dense").classes(
                    "text-xs font-semibold text-[#e5c07b] border border-[#e5c07b]/30 hover:bg-[#e5c07b]/10 px-3 py-1.5 rounded-lg"
                )

                ui.button(
                    "Refresh",
                    icon="refresh",
                    on_click=self.refresh_all,
                ).props("flat dense").classes(
                    "text-xs text-[#d1cbbe] border border-[#d1cbbe]/20 hover:bg-white/5 px-3 py-1.5 rounded-lg"
                )

    # [spec: UI-003]
    def render_loan_progress_section(self) -> None:
        """Render mortgage loan amortization section with side-by-side progress bar and funding split matching Image 3."""
        progress = self.calculate_current_mortgage_progress()
        summary = self.db.get_portfolio_cumulative_summary()
        props = build_mortgage_progress_bar_props(
            progress,
            fixed_deal_end_date=self.config.mortgage.fixed_deal_end_date or "N/A",
            monthly_direct_debit=self.config.mortgage.monthly_direct_debit,
            interest_rate=self.config.mortgage.interest_rate,
            cumulative_summary=summary,
        )

        with ui.card().classes(
            "w-full theme-card border theme-border p-6 rounded-xl shadow-lg relative overflow-hidden flex flex-col gap-4"
        ):
            # Card Title & Details Row
            with ui.row().classes("w-full justify-between items-center mb-1"):
                ui.label("MORTGAGE LOAN AMORTIZATION").classes(
                    "text-sm font-bold tracking-wider text-[#e5c07b] uppercase"
                )
                with ui.row().classes("items-center gap-3 text-sm text-[#d1cbbe]"):
                    ui.label(f"Initial: {props['initial_principal']}").classes("font-medium")
                    ui.label("•").classes("text-[#666]")
                    ui.label(f"Interest Paid: {props['interest_paid']}").classes("text-[#fbbf24] font-semibold")
                    ui.label("•").classes("text-[#666]")
                    ui.label(f"Current Balance: {props['current_balance']}").classes(
                        "text-[#e5c07b] font-bold text-base"
                    )
                    ui.label("•").classes("text-[#666]")
                    ui.label(f"{props['remaining_term']} on fixed rate").classes("text-[#e5c07b] font-semibold")

            # Two side-by-side columns matching Image 3
            with ui.grid(columns=2).classes("w-full gap-8 items-start"):
                # Left Column: Loan progress bar
                with ui.column().classes("w-full gap-2"):
                    with ui.row().classes("w-full justify-between items-center"):
                        ui.label("Loan progress bar").classes("text-sm text-[#d1cbbe] font-semibold")
                        ui.label(f"Repaid: {props['paid_off_amount']}").classes("text-sm text-[#86efac] font-bold")

                    repaid_pct_val = max(props["progress_fraction"] * 100.0, 0.0)
                    remaining_pct_val = max(100.0 - repaid_pct_val, 0.0)

                    with ui.row().classes(
                        "w-full h-8 rounded-md overflow-hidden p-0 items-stretch gap-1 bg-black/50 shadow-inner border border-[#e5c07b]/30"
                    ):
                        # Luminous Champagne Gold Repaid Segment
                        with (
                            ui.element("div")
                            .classes(
                                "flex items-center justify-center text-sm font-extrabold text-[#0e1015] px-2 transition-all rounded-l-sm"
                            )
                            .style(
                                f"flex: {max(repaid_pct_val, 14.0):.1f} 1 0%; "
                                "background: linear-gradient(135deg, rgba(250, 219, 140, 1) 0%, rgba(229, 192, 123, 0.95) 50%, rgba(197, 160, 89, 0.95) 100%); "
                                "border: 1px solid rgba(255, 245, 220, 0.85); "
                                "box-shadow: 0 0 16px rgba(229, 192, 123, 0.5), inset 0 1px 2px rgba(255, 255, 255, 0.5);"
                            )
                        ):
                            ui.label(f"{props['paid_off_percentage']} Paid")

                        # Luminous Slate & Gold Architectural Remaining Track
                        with (
                            ui.element("div")
                            .classes(
                                "flex items-center justify-between text-xs font-bold text-[#e5c07b] px-3 transition-all rounded-r-sm"
                            )
                            .style(
                                f"flex: {max(remaining_pct_val, 14.0):.1f} 1 0%; "
                                "background: linear-gradient(135deg, rgba(38, 52, 75, 0.95) 0%, rgba(24, 34, 52, 0.98) 100%); "
                                "border: 1px dashed rgba(229, 192, 123, 0.5); "
                                "box-shadow: inset 0 2px 6px rgba(0, 0, 0, 0.5), 0 0 10px rgba(68, 92, 130, 0.35);"
                            )
                        ):
                            ui.label(f"Balance: {remaining_pct_val:.1f}%")
                            ui.label(f"({props['current_balance']} Remaining)").classes(
                                "font-semibold text-[#fdfbf7]/90"
                            )

                    with ui.row().classes("w-full justify-between items-center text-xs text-[#a8a29e]"):
                        ui.label(f"{props['paid_off_percentage']} of principal paid off")
                        ui.label(f"Balance: {props['current_balance']} remaining").classes("text-[#e5c07b] font-medium")

                # Right Column: Funding split
                with ui.column().classes("w-full gap-2"):
                    with ui.row().classes("w-full justify-between items-center"):
                        ui.label("Funding split").classes("text-sm text-[#d1cbbe] font-semibold")
                        ui.label(f"(Total Invoiced: {props['total_mortgage_funded']})").classes(
                            "text-xs font-semibold text-[#e5c07b]"
                        )

                    try:
                        rent_pct_val = float(props["rental_funding_pct"].rstrip("%"))
                        shortfall_pct_val = float(props["shortfall_funding_pct"].rstrip("%"))
                    except ValueError:
                        rent_pct_val, shortfall_pct_val = 50.0, 50.0

                    total_funding_pct = rent_pct_val + shortfall_pct_val
                    if total_funding_pct > 0:
                        rent_width = (rent_pct_val / total_funding_pct) * 100.0
                        shortfall_width = (shortfall_pct_val / total_funding_pct) * 100.0
                    else:
                        rent_width, shortfall_width = 50.0, 50.0

                    with ui.row().classes(
                        "w-full h-8 rounded-md overflow-hidden p-0 items-stretch gap-1 bg-black/50 shadow-inner border border-[#e5c07b]/30"
                    ):
                        with (
                            ui.element("div")
                            .classes(
                                "flex items-center justify-center text-sm font-extrabold text-[#0e1015] px-2 transition-all rounded-l-sm"
                            )
                            .style(
                                f"flex: {max(rent_width, 14.0):.1f} 1 0%; "
                                "background: linear-gradient(180deg, rgba(167, 243, 208, 0.95) 0%, rgba(134, 239, 172, 0.85) 50%, rgba(74, 222, 128, 0.75) 100%); "
                                "border: 1px solid rgba(187, 247, 208, 0.8); "
                                "box-shadow: 0 0 14px rgba(134, 239, 172, 0.45), inset 0 1px 2px rgba(255, 255, 255, 0.5);"
                            )
                        ):
                            ui.label(props["rental_funding_pct"])

                        with (
                            ui.element("div")
                            .classes(
                                "flex items-center justify-center text-sm font-extrabold text-white px-2 transition-all rounded-r-sm"
                            )
                            .style(
                                f"flex: {max(shortfall_width, 14.0):.1f} 1 0%; "
                                "background: linear-gradient(180deg, rgba(244, 63, 94, 0.92) 0%, rgba(190, 18, 60, 0.85) 50%, rgba(136, 19, 55, 0.8) 100%); "
                                "border: 1px solid rgba(251, 113, 133, 0.75); "
                                "box-shadow: 0 0 14px rgba(244, 63, 94, 0.45), inset 0 1px 2px rgba(255, 255, 255, 0.4);"
                            )
                        ):
                            ui.label(props["shortfall_funding_pct"])

                    with ui.row().classes("w-full items-center justify-between text-xs text-[#d1cbbe]"):
                        with ui.row().classes("items-center gap-1.5"):
                            ui.element("div").classes(
                                "w-2.5 h-2.5 rounded-full bg-[#86efac] shadow-[0_0_8px_rgba(134,239,172,0.8)]"
                            )
                            ui.label(f"Rental Income: {props['rental_income_funded']}").classes(
                                "text-[#86efac] font-bold"
                            )
                        with ui.row().classes("items-center gap-1.5"):
                            ui.element("div").classes(
                                "w-2.5 h-2.5 rounded-full bg-[#f43f5e] shadow-[0_0_8px_rgba(244,63,94,0.8)]"
                            )
                            ui.label(f"Shortfall: {props['shortfall_funded']}").classes("text-[#fda4af] font-bold")

            # Footnote
            with ui.row().classes("w-full items-center gap-2 pt-2 border-t border-[#e5c07b]/10 text-xs text-[#a8a29e]"):
                ui.icon("info_outline", size="xs").classes("text-[#e5c07b]")
                ui.label(props["explanation_text"]).classes("leading-relaxed")

    # [spec: UI-003]
    def render_current_month_progress_section(self) -> None:
        """Render current month financial performance box matching Image 3."""
        kpis = self.db.get_kpi_summary(default_mortgage_debit=self.config.mortgage.monthly_direct_debit)
        props = build_current_month_progress_props(kpis)

        exp_pct_str = props.get("expense_percentage", "0.0%").rstrip("%")
        ret_pct_str = props.get("retention_percentage", "0.0%").rstrip("%")
        try:
            exp_pct = float(exp_pct_str)
        except ValueError:
            exp_pct = 0.0
        try:
            ret_pct = float(ret_pct_str)
        except ValueError:
            ret_pct = 0.0

        total_pct = exp_pct + ret_pct
        if total_pct > 0:
            exp_width = (exp_pct / total_pct) * 100.0
            ret_width = (ret_pct / total_pct) * 100.0
        else:
            exp_width, ret_width = 50.0, 50.0

        with ui.card().classes(
            "w-full theme-card border theme-border p-6 rounded-xl shadow-lg relative overflow-hidden flex flex-col gap-3"
        ):
            # Header
            with ui.row().classes("w-full justify-between items-center"):
                ui.label("CURRENT MONTH").classes("text-sm font-bold tracking-wider text-[#e5c07b] uppercase")
                ui.label(f"({props['statement_title']})").classes("text-xs text-[#d1cbbe] font-semibold")

            ui.label("Refined split bar").classes("text-xs font-medium text-[#a8a29e]")

            # Split Progress Bar: Soft Mint (Earning) | Burgundy (Expenses)
            with ui.row().classes(
                "w-full h-8 rounded-md overflow-hidden p-0 items-stretch gap-1 bg-black/50 shadow-inner border border-[#e5c07b]/30"
            ):
                with (
                    ui.element("div")
                    .classes(
                        "flex items-center justify-center text-sm font-extrabold text-[#0e1015] px-3 transition-all rounded-l-sm"
                    )
                    .style(
                        f"flex: {max(ret_width, 14.0):.1f} 1 0%; "
                        "background: linear-gradient(180deg, rgba(167, 243, 208, 0.95) 0%, rgba(134, 239, 172, 0.85) 50%, rgba(74, 222, 128, 0.75) 100%); "
                        "border: 1px solid rgba(187, 247, 208, 0.8); "
                        "box-shadow: 0 0 14px rgba(134, 239, 172, 0.45), inset 0 1px 2px rgba(255, 255, 255, 0.5);"
                    )
                ):
                    ui.label(f"Earning: {props['retention_percentage']}")

                with (
                    ui.element("div")
                    .classes(
                        "flex items-center justify-center text-sm font-extrabold text-white px-3 transition-all rounded-r-sm"
                    )
                    .style(
                        f"flex: {max(exp_width, 14.0):.1f} 1 0%; "
                        "background: linear-gradient(180deg, rgba(244, 63, 94, 0.92) 0%, rgba(190, 18, 60, 0.85) 50%, rgba(136, 19, 55, 0.8) 100%); "
                        "border: 1px solid rgba(251, 113, 133, 0.75); "
                        "box-shadow: 0 0 14px rgba(244, 63, 94, 0.45), inset 0 1px 2px rgba(255, 255, 255, 0.4);"
                    )
                ):
                    ui.label(f"Expenses: {props['expense_percentage']}")

            # Row of 4 Metric Boxes: Gross Rent | Expenses | Earning | Shortfall
            with ui.grid(columns=4).classes("w-full gap-4 pt-2"):
                # Card 1: Gross Rent
                with ui.card().classes(
                    "theme-card-alt border border-[#e5c07b]/30 p-5 rounded-xl shadow-sm flex flex-col justify-between"
                ):
                    ui.label("Gross Rent").classes("text-sm font-bold text-[#d1cbbe] uppercase tracking-wider")
                    ui.label(props["gross_rent"]).classes("text-3xl font-extrabold text-[#fdfbf7] mt-3")
                    ui.label("Total rent invoiced").classes("text-xs font-medium text-[#a8a29e] mt-1")

                # Card 2: Expenses
                with ui.card().classes(
                    "theme-card-alt border border-[#e5c07b]/30 p-5 rounded-xl shadow-sm flex flex-col justify-between"
                ):
                    ui.label("Expenses").classes("text-sm font-bold text-[#d1cbbe] uppercase tracking-wider")
                    ui.label(props["expenses"]).classes("text-3xl font-extrabold text-[#fdfbf7] mt-3")
                    ui.label(f"{props['expense_percentage']} of gross").classes(
                        "text-xs font-medium text-[#a8a29e] mt-1"
                    )

                # Card 3: Earning
                with ui.card().classes(
                    "theme-card-alt border border-[#e5c07b]/30 p-5 rounded-xl shadow-sm flex flex-col justify-between"
                ):
                    ui.label("Earning").classes("text-sm font-bold text-[#d1cbbe] uppercase tracking-wider")
                    ui.label(props["net_earnings"]).classes("text-3xl font-extrabold text-[#fdfbf7] mt-3")
                    ui.label(f"{props['retention_percentage']} retained").classes(
                        "text-xs font-medium text-[#a8a29e] mt-1"
                    )

                # Card 4: Shortfall
                with ui.card().classes(
                    "theme-card-alt border border-[#e5c07b]/30 p-5 rounded-xl shadow-sm flex flex-col justify-between"
                ):
                    ui.label("Shortfall").classes("text-sm font-bold text-[#d1cbbe] uppercase tracking-wider")
                    ui.label(props["shortfall"]).classes("text-3xl font-extrabold text-[#fdfbf7] mt-3")
                    ui.label("Out-of-pocket cashflow").classes("text-xs font-medium text-[#a8a29e] mt-1")

    # [spec: UI-003]
    def render_portfolio_summary_section(self) -> None:
        """Render all-time portfolio summary box with dual-split progress bar, 4 metric cards and visual summary graphs matching Image 3."""
        summary = self.db.get_portfolio_cumulative_summary()
        props = build_portfolio_summary_progress_props(summary)

        exp_pct_str = props.get("expense_percentage", "0.0%").rstrip("%")
        ret_pct_str = props.get("retention_percentage", "0.0%").rstrip("%")
        try:
            exp_pct = float(exp_pct_str)
        except ValueError:
            exp_pct = 0.0
        try:
            ret_pct = float(ret_pct_str)
        except ValueError:
            ret_pct = 0.0

        total_pct = exp_pct + ret_pct
        if total_pct > 0:
            exp_width = (exp_pct / total_pct) * 100.0
            ret_width = (ret_pct / total_pct) * 100.0
        else:
            exp_width, ret_width = 50.0, 50.0

        with ui.card().classes(
            "w-full theme-card border theme-border p-6 rounded-xl shadow-lg relative overflow-hidden flex flex-col gap-4"
        ):
            # Header
            with ui.row().classes("w-full justify-between items-center"):
                ui.label("PORTFOLIO CUMULATIVE SUMMARY").classes(
                    "text-sm font-bold tracking-widest text-[#e5c07b] uppercase"
                )
                ui.label(f"({summary.get('total_statements', 0)} Statements Ingested)").classes(
                    "text-xs text-[#d1cbbe] font-semibold"
                )

            # Split Progress Bar: Expenses % | Earning %
            with ui.row().classes(
                "w-full h-8 rounded-md overflow-hidden p-0 items-stretch gap-1 bg-black/50 shadow-inner border border-[#e5c07b]/30"
            ):
                with (
                    ui.element("div")
                    .classes(
                        "flex items-center justify-center text-sm font-extrabold text-[#0e1015] px-3 transition-all rounded-l-sm"
                    )
                    .style(
                        f"flex: {max(ret_width, 14.0):.1f} 1 0%; "
                        "background: linear-gradient(180deg, rgba(167, 243, 208, 0.95) 0%, rgba(134, 239, 172, 0.85) 50%, rgba(74, 222, 128, 0.75) 100%); "
                        "border: 1px solid rgba(187, 247, 208, 0.8); "
                        "box-shadow: 0 0 14px rgba(134, 239, 172, 0.45), inset 0 1px 2px rgba(255, 255, 255, 0.5);"
                    )
                ):
                    ui.label(f"Cumulative Earning: {props['retention_percentage']}")

                with (
                    ui.element("div")
                    .classes(
                        "flex items-center justify-center text-sm font-extrabold text-white px-3 transition-all rounded-r-sm"
                    )
                    .style(
                        f"flex: {max(exp_width, 14.0):.1f} 1 0%; "
                        "background: linear-gradient(180deg, rgba(244, 63, 94, 0.92) 0%, rgba(190, 18, 60, 0.85) 50%, rgba(136, 19, 55, 0.8) 100%); "
                        "border: 1px solid rgba(251, 113, 133, 0.75); "
                        "box-shadow: 0 0 14px rgba(244, 63, 94, 0.45), inset 0 1px 2px rgba(255, 255, 255, 0.4);"
                    )
                ):
                    ui.label(f"Cumulative Expenses: {props['expense_percentage']}")

            # Row of 4 Metric Boxes: Gross Rent | Expenses Deduction | Earning | Shortfall
            with ui.grid(columns=4).classes("w-full gap-4 pt-1"):
                # Card 1: Gross Rent
                with ui.card().classes(
                    "theme-card-alt border border-[#e5c07b]/30 p-5 rounded-xl shadow-sm flex flex-col justify-between"
                ):
                    ui.label("Gross Rent").classes("text-sm font-bold text-[#d1cbbe] uppercase tracking-wider")
                    ui.label(props["gross_rent"]).classes("text-3xl font-extrabold text-[#fdfbf7] mt-3")
                    ui.label("Cumulative all statements").classes("text-xs font-medium text-[#a8a29e] mt-1")

                # Card 2: Expenses Deduction
                with ui.card().classes(
                    "theme-card-alt border border-[#e5c07b]/30 p-5 rounded-xl shadow-sm flex flex-col justify-between"
                ):
                    ui.label("Expenses Deduction").classes("text-sm font-bold text-[#d1cbbe] uppercase tracking-wider")
                    ui.label(props["expenses"]).classes("text-3xl font-extrabold text-[#fdfbf7] mt-3")
                    ui.label(f"{props['expense_percentage']} cumulative ratio").classes(
                        "text-xs font-medium text-[#a8a29e] mt-1"
                    )

                # Card 3: Earning
                with ui.card().classes(
                    "theme-card-alt border border-[#e5c07b]/30 p-5 rounded-xl shadow-sm flex flex-col justify-between"
                ):
                    ui.label("Earning").classes("text-sm font-bold text-[#d1cbbe] uppercase tracking-wider")
                    ui.label(props["net_earnings"]).classes("text-3xl font-extrabold text-[#fdfbf7] mt-3")
                    ui.label(f"{props['retention_percentage']} cumulative retention").classes(
                        "text-xs font-medium text-[#a8a29e] mt-1"
                    )

                # Card 4: Shortfall
                with ui.card().classes(
                    "theme-card-alt border border-[#e5c07b]/30 p-5 rounded-xl shadow-sm flex flex-col justify-between"
                ):
                    ui.label("Shortfall").classes("text-sm font-bold text-[#d1cbbe] uppercase tracking-wider")
                    ui.label(props["shortfall"]).classes("text-3xl font-extrabold text-[#fdfbf7] mt-3")
                    ui.label("Total out-of-pocket to date").classes("text-xs font-medium text-[#a8a29e] mt-1")

    # [spec: UI-001]
    def render_kpi_cards(self) -> None:
        """Render 4 executive KPI summary cards."""
        kpis = self.db.get_kpi_summary(default_mortgage_debit=self.config.mortgage.monthly_direct_debit)
        cards = format_kpi_card_data(kpis)

        color_map = {
            "cyan": "border-[#e5c07b]/30 text-[#e5c07b]",
            "emerald": "border-[#86efac]/30 text-[#86efac]",
            "amber": "border-[#d97706]/30 text-[#fbbf24]",
            "coral": "border-[#9f1239]/40 text-[#fda4af]",
        }

        with ui.grid(columns=4).classes("w-full gap-4"):
            for card in cards:
                classes = color_map.get(card["color"], "border-gray-700 text-gray-300")
                with ui.card().classes(f"theme-card border {classes} p-4 rounded-xl shadow-md"):
                    with ui.row().classes("justify-between items-start w-full"):
                        ui.label(card["title"]).classes("text-sm font-bold text-gray-300 uppercase tracking-wide")
                        ui.icon(card["icon"], size="xs").classes("opacity-60")
                    ui.label(card["value"]).classes("text-2xl font-bold mt-2")
                    ui.label(card["subtitle"]).classes("text-xs text-gray-400 mt-1")

    # [spec: UI-001]
    def render_trend_charts(self) -> None:
        """Render interactive trend graphs for monthly rental metrics and shortfall."""
        records = self.db.get_all_monthly_statements()
        if not records:
            with ui.card().classes("w-full theme-card border theme-border p-8 text-center rounded-xl"):
                ui.icon("insert_chart_outlined", size="lg").classes("text-gray-600 mb-2")
                ui.label("No rental statements ingested yet. Ingest statement PDFs to generate trends.").classes(
                    "text-gray-400 text-sm"
                )
            return

        series = prepare_chart_series(records)

        chart_options = {
            "title": {
                "text": "MONTHLY FINANCIAL CASHFLOW & SHORTFALL (13-MONTH TREND)",
                "subtext": "Historical monthly gross income, expenditures, net earnings, and out-of-pocket mortgage shortfall",
                "left": "center",
                "top": "8",
                "textStyle": {"color": "#fdfbf7", "fontSize": 14, "fontWeight": 700, "letterSpacing": 0.5},
                "subtextStyle": {"color": "#a8a29e", "fontSize": 12, "fontWeight": 400},
            },
            "tooltip": {
                "trigger": "axis",
                "axisPointer": {"type": "cross", "lineStyle": {"color": "rgba(229, 192, 123, 0.4)", "type": "dashed"}},
                "backgroundColor": "rgba(20, 28, 42, 0.95)",
                "borderColor": "rgba(229, 192, 123, 0.35)",
                "borderWidth": 1,
                "textStyle": {"color": "#fdfbf7", "fontSize": 12},
                "extraCssText": "backdrop-filter: blur(8px); box-shadow: 0 8px 32px rgba(0,0,0,0.5); border-radius: 8px;",
            },
            "legend": {
                "data": ["Out-of-Pocket Shortfall", "Gross Rent", "Total Deductions", "Earning"],
                "textStyle": {"color": "#d1cbbe", "fontSize": 12, "fontWeight": 500},
                "bottom": "8",
            },
            "grid": {"left": "3%", "right": "4%", "top": "18%", "bottom": "14%", "containLabel": True},
            "xAxis": {
                "type": "category",
                "boundaryGap": True,
                "data": series["categories"],
                "axisLine": {"lineStyle": {"color": "rgba(229, 192, 123, 0.3)"}},
                "axisLabel": {"color": "#d1cbbe", "fontSize": 11, "fontWeight": 600, "rotate": 25},
            },
            "yAxis": {
                "type": "value",
                "axisLine": {"lineStyle": {"color": "rgba(229, 192, 123, 0.3)"}},
                "axisLabel": {"formatter": "£{value}", "color": "#d1cbbe", "fontSize": 11, "fontWeight": 600},
                "splitLine": {"lineStyle": {"color": "rgba(229, 192, 123, 0.12)", "type": "dashed"}},
            },
            "series": [
                {
                    "name": "Out-of-Pocket Shortfall",
                    "type": "bar",
                    "barWidth": "36%",
                    "itemStyle": {
                        "borderRadius": [6, 6, 0, 0],
                        "color": {
                            "type": "linear",
                            "x": 0,
                            "y": 0,
                            "x2": 0,
                            "y2": 1,
                            "colorStops": [
                                {"offset": 0, "color": "rgba(244, 63, 94, 0.85)"},
                                {"offset": 1, "color": "rgba(159, 18, 57, 0.3)"},
                            ],
                        },
                        "borderColor": "rgba(251, 113, 133, 0.6)",
                        "borderWidth": 1.5,
                    },
                    "data": series["shortfall"],
                },
                {
                    "name": "Gross Rent",
                    "type": "line",
                    "smooth": True,
                    "symbol": "circle",
                    "symbolSize": 6,
                    "lineStyle": {
                        "color": "#e5c07b",
                        "width": 3,
                        "shadowColor": "rgba(229, 192, 123, 0.4)",
                        "shadowBlur": 8,
                    },
                    "itemStyle": {"color": "#e5c07b"},
                    "data": series["gross"],
                },
                {
                    "name": "Total Deductions",
                    "type": "line",
                    "smooth": True,
                    "symbol": "circle",
                    "symbolSize": 6,
                    "lineStyle": {"color": "#fbbf24", "width": 2.5},
                    "itemStyle": {"color": "#fbbf24"},
                    "data": series["deductions"],
                },
                {
                    "name": "Earning",
                    "type": "line",
                    "smooth": True,
                    "symbol": "circle",
                    "symbolSize": 6,
                    "lineStyle": {
                        "color": "#86efac",
                        "width": 3,
                        "shadowColor": "rgba(134, 239, 172, 0.4)",
                        "shadowBlur": 8,
                    },
                    "itemStyle": {"color": "#86efac"},
                    "areaStyle": {
                        "color": {
                            "type": "linear",
                            "x": 0,
                            "y": 0,
                            "x2": 0,
                            "y2": 1,
                            "colorStops": [
                                {"offset": 0, "color": "rgba(134, 239, 172, 0.22)"},
                                {"offset": 1, "color": "rgba(134, 239, 172, 0.0)"},
                            ],
                        }
                    },
                    "data": series["payout"],
                },
            ],
        }

        with ui.card().classes("w-full theme-card border theme-border p-6 rounded-xl shadow-lg"):
            ui.echart(chart_options).classes("w-full h-[420px]")

    # [spec: UI-001]
    def show_statement_modal(self, row: dict) -> None:
        """Display itemized expenditure details in an enlarged modal popup with categorized management costs and expenses.

        Supports consolidated multi-statement months with interactive tabs for month summary and individual statements.
        """
        sub_stmts = row.get("sub_statements") or [row]
        is_multi = len(sub_stmts) > 1

        with (
            ui.dialog() as dialog,
            ui.card().classes("theme-card border theme-border p-7 w-[860px] max-w-4xl max-h-[88vh] flex flex-col"),
        ):
            # Modal Top Header
            with ui.row().classes("justify-between items-center w-full mb-3"):
                with ui.row().classes("items-center gap-2"):
                    ui.icon("receipt_long", size="sm").classes("text-[#e5c07b]")
                    title_text = (
                        f"{row.get('statement_date', 'Month')} — Consolidated Statements ({len(sub_stmts)})"
                        if is_multi
                        else f"Statement {row.get('statement_number', '')} — Expenditure Breakdown"
                    )
                    ui.label(title_text).classes("text-xl font-bold text-gray-100")
                with ui.row().classes("items-center gap-2"):
                    if not is_multi and row.get("id"):
                        stmt_id = row.get("id")
                        ui.button(
                            "Edit Details",
                            icon="edit",
                            on_click=lambda sid=stmt_id, d=dialog: (d.close(), self.open_edit_statement_dialog(sid)),
                        ).classes(
                            "bg-[#e5c07b]/15 text-[#e5c07b] border border-[#e5c07b]/30 hover:bg-[#e5c07b]/25 text-xs font-semibold px-3 py-1 rounded-lg"
                        ).props("dense")
                    ui.button(icon="close", on_click=dialog.close).props("flat round dense color=grey")

            def render_statement_content(stmt_data: dict, is_summary_tab: bool = False):
                expenditures = stmt_data.get("expenditures", [])
                partition = partition_statement_expenditures(expenditures)
                mgmt_items = partition["management_costs"]
                expense_items = partition["direct_expenses"]
                total_mgmt = partition["total_management_costs"]
                total_expenses = partition["total_direct_expenses"]

                # Multi-line summary box: splits deductions into management cost and direct expenses
                with ui.card().classes(
                    "w-full theme-card-alt p-4 rounded-xl theme-border border mb-4 text-xs text-gray-300 gap-3"
                ):
                    # Line 1: Statement Reference and Core Cashflow Totals
                    with ui.row().classes("w-full justify-between items-center pb-2 border-b theme-border"):
                        with ui.row().classes("items-center gap-3"):
                            ui.label(f"Date: {stmt_data.get('statement_date')}").classes("text-gray-200 font-semibold")
                            ui.label("•").classes("text-gray-600")
                            ref_label = stmt_data.get("reference") or ("Consolidated" if is_summary_tab else "N/A")
                            ui.label(f"Ref: {ref_label}").classes("text-gray-400")
                        with ui.row().classes("items-center gap-4"):
                            ui.label(f"Gross Rent: {stmt_data.get('gross_income')}").classes(
                                "text-[#e5c07b] font-semibold text-sm"
                            )
                            ui.label(f"Earning: {stmt_data.get('net_payout')}").classes(
                                "text-[#86efac] font-bold text-sm"
                            )
                            shortfall_str = stmt_data.get("shortfall", "£0.00")
                            shortfall_color = (
                                "text-[#86efac]"
                                if "Balanced" in str(shortfall_str) or shortfall_str == "£0.00"
                                else "text-[#fda4af]"
                            )
                            ui.label(f"Shortfall: {shortfall_str}").classes(f"{shortfall_color} font-bold text-sm")

                    # Line 2: Deductions Breakdown into Management Costs and Property Expenses
                    with ui.row().classes("w-full justify-between items-center"):
                        with ui.row().classes("items-center gap-2"):
                            ui.icon("receipt", size="xs").classes("text-[#d97706]")
                            ui.label(f"Total Deductions: {stmt_data.get('total_expenditure')}").classes(
                                "text-[#fbbf24] font-bold text-sm"
                            )
                        with ui.row().classes("items-center gap-3"):
                            ui.badge(f"Property Expenses: £{total_expenses:,.2f}").props("outline").classes(
                                "border-[#d97706]/50 text-[#fbbf24]"
                            )
                            ui.label("+").classes("text-gray-500 font-bold")
                            ui.badge(f"Management Cost: £{total_mgmt:,.2f}").props("outline").classes(
                                "border-[#e5c07b]/50 text-[#e5c07b]"
                            )

                # Categorized Itemized Expenditures List (Property Expenses above Management Cost)
                with ui.column().classes("w-full gap-4 max-h-[46vh] overflow-y-auto pr-1"):
                    # Section 1: Property Expenses & Maintenance
                    if expense_items:
                        with ui.column().classes("w-full gap-2"):
                            with ui.row().classes("justify-between items-center w-full px-1"):
                                with ui.row().classes("items-center gap-2"):
                                    ui.icon("build", size="xs").classes("text-[#d97706]")
                                    ui.label("Property Expenses & Maintenance").classes(
                                        "text-xs font-bold uppercase text-[#fbbf24] tracking-wider"
                                    )
                                ui.badge(f"£{total_expenses:,.2f}").props("dense outline").classes(
                                    "border-[#d97706]/50 text-[#fbbf24]"
                                )

                            for item in expense_items:
                                with ui.card().classes("w-full theme-card-alt p-3 rounded-lg border theme-border"):
                                    with ui.row().classes("justify-between w-full items-start"):
                                        desc = item.get("description", "")
                                        source = item.get("source_statement")
                                        if is_summary_tab and source:
                                            desc = f"[{source}] {desc}"
                                        ui.label(desc).classes("text-sm font-medium text-gray-200")
                                        ui.label(f"£{Decimal(str(item.get('gross', '0.00'))):,.2f}").classes(
                                            "text-sm font-bold text-[#fbbf24]"
                                        )
                                    with ui.row().classes("w-full justify-end gap-3 text-xs text-gray-400 mt-1"):
                                        ui.label(f"Net: £{Decimal(str(item.get('net', '0.00'))):,.2f}")
                                        ui.label(f"VAT: £{Decimal(str(item.get('vat', '0.00'))):,.2f}")

                    # Section 2: Management Cost (Letting fees, Management fees, Tenancy Deposit Scheme)
                    if mgmt_items:
                        with ui.column().classes("w-full gap-2 mt-1"):
                            with ui.row().classes("justify-between items-center w-full px-1"):
                                with ui.row().classes("items-center gap-2"):
                                    ui.icon("domain", size="xs").classes("text-[#e5c07b]")
                                    ui.label("Management Cost").classes(
                                        "text-xs font-bold uppercase text-[#e5c07b] tracking-wider"
                                    )
                                ui.badge(f"£{total_mgmt:,.2f}").props("dense outline").classes(
                                    "border-[#e5c07b]/50 text-[#e5c07b]"
                                )

                            for item in mgmt_items:
                                with ui.card().classes("w-full theme-card-alt p-3 rounded-lg border theme-border"):
                                    with ui.row().classes("justify-between w-full items-start"):
                                        desc = item.get("description", "")
                                        source = item.get("source_statement")
                                        if is_summary_tab and source:
                                            desc = f"[{source}] {desc}"
                                        ui.label(desc).classes("text-sm font-medium text-gray-200")
                                        ui.label(f"£{Decimal(str(item.get('gross', '0.00'))):,.2f}").classes(
                                            "text-sm font-bold text-[#e5c07b]"
                                        )
                                    with ui.row().classes("w-full justify-end gap-3 text-xs text-gray-400 mt-1"):
                                        ui.label(f"Net: £{Decimal(str(item.get('net', '0.00'))):,.2f}")
                                        ui.label(f"VAT: £{Decimal(str(item.get('vat', '0.00'))):,.2f}")

                    if not mgmt_items and not expense_items:
                        ui.label("No expenditure lines recorded for this statement.").classes(
                            "text-xs text-gray-500 italic py-4"
                        )

                # Edit button for individual statements
                stmt_id = stmt_data.get("id")
                if stmt_id and not is_summary_tab:
                    with ui.row().classes("w-full justify-end pt-3 mt-2 border-t theme-border"):
                        ui.button(
                            f"Edit Statement #{stmt_data.get('statement_number')}",
                            icon="edit",
                            on_click=lambda sid=stmt_id, d=dialog: (d.close(), self.open_edit_statement_dialog(sid)),
                        ).classes(
                            "bg-[#e5c07b] text-[#0e1015] hover:bg-[#e5c07b]/90 text-xs font-bold px-4 py-2 rounded-lg"
                        )

            if is_multi:
                with ui.tabs().classes("w-full mb-3") as tabs:
                    tab_summary = ui.tab("summary", label="Consolidated Month Summary", icon="dashboard")
                    sub_tab_refs = []
                    for idx, s in enumerate(sub_stmts, start=1):
                        num = s.get("statement_number", idx)
                        t = ui.tab(
                            f"stmt_{idx}", label=f"Statement #{num} ({s.get('statement_date', '')})", icon="receipt"
                        )
                        sub_tab_refs.append((t, s))

                with ui.tab_panels(tabs, value=tab_summary).classes("w-full bg-transparent p-0"):
                    with ui.tab_panel(tab_summary).classes("p-0"):
                        render_statement_content(row, is_summary_tab=True)
                    for t, s in sub_tab_refs:
                        with ui.tab_panel(t).classes("p-0"):
                            render_statement_content(s, is_summary_tab=False)
            else:
                render_statement_content(row, is_summary_tab=False)

            with ui.row().classes("w-full justify-end items-center mt-3 pt-2 border-t theme-border"):
                ui.button("Close", on_click=dialog.close).props("flat color=grey")

        dialog.open()

    # [spec: UI-001]
    def open_edit_statement_dialog(self, statement_id: int) -> None:
        """Modal dialog to edit monthly statement details and itemized expenditures."""
        record = self.db.get_monthly_statement_by_id(statement_id)
        if not record:
            ui.notify("Monthly statement record not found", type="negative")
            return

        with (
            ui.dialog() as dialog,
            ui.card().classes("theme-card border theme-border p-7 w-[780px] max-w-3xl flex flex-col max-h-[90vh]"),
        ):
            with ui.row().classes("justify-between items-center w-full mb-3"):
                with ui.row().classes("items-center gap-2"):
                    ui.icon("edit_document", size="sm").classes("text-[#e5c07b]")
                    ui.label(
                        f"Edit Statement #{record.get('statement_number', '')} ({record.get('statement_date', '')})"
                    ).classes("text-xl font-bold text-gray-100")
                ui.button(icon="close", on_click=dialog.close).props("flat round dense color=grey")

            with ui.row().classes("w-full gap-4 mb-3"):
                date_input = (
                    ui.input(label="Statement Date (DD-MM-YYYY) *", value=record.get("statement_date", ""))
                    .classes("flex-1")
                    .props("outlined dark dense")
                )
                stmt_num_input = (
                    ui.input(label="Statement Number *", value=record.get("statement_number", ""))
                    .classes("flex-1")
                    .props("outlined dark dense")
                )
                ref_input = (
                    ui.input(label="Reference", value=record.get("reference") or "")
                    .classes("flex-1")
                    .props("outlined dark dense")
                )

            with ui.row().classes("w-full gap-4 mb-4"):
                gross_input = (
                    ui.input(label="Gross Rent (£) *", value=str(record.get("gross_income", "0.00")))
                    .classes("flex-1")
                    .props("outlined dark dense")
                )
                debit_input = (
                    ui.input(label="Mortgage Debit (£) *", value=str(record.get("mortgage_debit", "0.00")))
                    .classes("flex-1")
                    .props("outlined dark dense")
                )

            ui.label("ITEMIZED EXPENDITURE LINES").classes(
                "text-xs font-bold uppercase tracking-wider text-[#e5c07b] mb-1"
            )

            # Scrollable expenditure lines container
            exp_rows_container = ui.column().classes("w-full gap-2 max-h-[38vh] overflow-y-auto pr-1")

            # Local state tracking line inputs
            exp_input_entries: list[dict[str, Any]] = []

            def render_exp_line(exp_data: dict[str, Any] | None = None) -> None:
                exp = exp_data or {"description": "", "net": "0.00", "vat": "0.00", "gross": "0.00"}
                with exp_rows_container:
                    row_card = ui.card().classes("w-full theme-card-alt p-2.5 rounded-lg border theme-border")
                    with row_card, ui.row().classes("w-full items-center gap-2"):
                        desc_inp = (
                            ui.input(
                                label="Description",
                                value=exp.get("description", ""),
                            )
                            .classes("flex-grow")
                            .props("outlined dark dense")
                        )
                        net_inp = (
                            ui.input(
                                label="Net (£)",
                                value=str(exp.get("net", "0.00")),
                            )
                            .classes("w-24")
                            .props("outlined dark dense")
                        )
                        vat_inp = (
                            ui.input(
                                label="VAT (£)",
                                value=str(exp.get("vat", "0.00")),
                            )
                            .classes("w-20")
                            .props("outlined dark dense")
                        )
                        gross_inp = (
                            ui.input(
                                label="Gross (£)",
                                value=str(exp.get("gross", "0.00")),
                            )
                            .classes("w-24")
                            .props("outlined dark dense")
                        )

                        def auto_calc_gross(_=None):
                            try:
                                n = Decimal(net_inp.value or "0.00")
                                v = Decimal(vat_inp.value or "0.00")
                                gross_inp.value = str((n + v).quantize(Decimal("0.01")))
                            except (InvalidOperation, TypeError, ValueError):
                                pass

                        net_inp.on("blur", auto_calc_gross)
                        vat_inp.on("blur", auto_calc_gross)

                        entry_ref = {
                            "card": row_card,
                            "desc": desc_inp,
                            "net": net_inp,
                            "vat": vat_inp,
                            "gross": gross_inp,
                        }
                        exp_input_entries.append(entry_ref)

                        def remove_line(target_entry=entry_ref):
                            if target_entry in exp_input_entries:
                                exp_input_entries.remove(target_entry)
                            target_entry["card"].delete()

                        ui.button(icon="delete", on_click=remove_line).props("flat round dense color=negative")

            for existing_exp in record.get("expenditures", []):
                render_exp_line(existing_exp)

            ui.button(
                "+ Add Expenditure Line",
                on_click=lambda: render_exp_line(None),
            ).classes(
                "bg-transparent text-[#e5c07b] border border-[#e5c07b]/40 hover:bg-[#e5c07b]/10 text-xs font-semibold px-3 py-1.5 rounded-lg mt-2 w-max"
            ).props("dense")

            def do_save():
                s_date = date_input.value.strip() if date_input.value else ""
                s_num = stmt_num_input.value.strip() if stmt_num_input.value else ""
                ref = ref_input.value.strip() if ref_input.value else ""
                if not s_date or not s_num:
                    ui.notify("Statement date and number are required", type="warning")
                    return

                try:
                    g_rent = Decimal(gross_input.value or "0.00")
                    m_debit = Decimal(debit_input.value or "0.00")
                except Exception:
                    ui.notify("Invalid number format for Gross Rent or Mortgage Debit", type="negative")
                    return

                new_exps = []
                for entry in exp_input_entries:
                    desc = entry["desc"].value.strip() if entry["desc"].value else ""
                    if not desc:
                        continue
                    try:
                        n_val = Decimal(entry["net"].value or "0.00")
                        v_val = Decimal(entry["vat"].value or "0.00")
                        g_val = Decimal(entry["gross"].value or "0.00")
                        if g_val == Decimal("0.00") and (n_val > 0 or v_val > 0):
                            g_val = n_val + v_val
                    except Exception:
                        ui.notify(f"Invalid monetary value in item '{desc}'", type="negative")
                        return

                    new_exps.append(
                        {
                            "description": desc,
                            "net": n_val,
                            "vat": v_val,
                            "gross": g_val,
                        }
                    )

                self.db.update_monthly_statement(
                    statement_id=statement_id,
                    statement_date=s_date,
                    reference=ref,
                    statement_number=s_num,
                    gross_income=g_rent,
                    mortgage_debit=m_debit,
                    expenditures=new_exps,
                )

                # Recalculate mortgage balances across statements
                self.db.recalculate_statement_balances(
                    initial_principal=self.config.mortgage.initial_principal,
                    monthly_direct_debit=self.config.mortgage.monthly_direct_debit,
                    interest_rate=self.config.mortgage.interest_rate,
                )

                dialog.close()
                self.refresh_all()
                ui.notify(f"Statement #{s_num} updated successfully", type="positive")

            with ui.row().classes("justify-end gap-3 mt-5 pt-3 border-t theme-border w-full"):
                ui.button("Cancel", on_click=dialog.close).props("flat color=grey")
                ui.button("Save Changes", on_click=do_save).classes(
                    "bg-[#e5c07b] text-[#0e1015] font-bold hover:bg-[#e5c07b]/90 px-5 py-2 rounded-lg"
                )

        dialog.open()

    # [spec: UI-001]
    def render_statements_table(self) -> None:
        """Render monthly statement history table with sortable columns and click-to-view popup dialog."""
        records = self.db.get_all_monthly_statements()
        rows = prepare_statements_table_rows(records)

        columns = [
            {"name": "statement_date", "label": "Date", "field": "statement_date", "sortable": True, "align": "left"},
            {
                "name": "statement_number",
                "label": "Statement #",
                "field": "statement_number",
                "sortable": True,
                "align": "left",
            },
            {"name": "reference", "label": "Reference", "field": "reference", "sortable": True, "align": "left"},
            {
                "name": "gross_income",
                "label": "Gross Rent (£)",
                "field": "gross_income",
                "sortable": True,
                "align": "right",
            },
            {
                "name": "total_expenditure",
                "label": "Deductions (£)",
                "field": "total_expenditure",
                "sortable": True,
                "align": "right",
            },
            {"name": "net_payout", "label": "Earning (£)", "field": "net_payout", "sortable": True, "align": "right"},
            {
                "name": "mortgage_debit",
                "label": "Mortgage Due (£)",
                "field": "mortgage_debit",
                "sortable": True,
                "align": "right",
            },
            {
                "name": "shortfall",
                "label": "Out-of-Pocket Shortfall (£)",
                "field": "shortfall",
                "sortable": True,
                "align": "right",
            },
        ]

        with ui.card().classes("w-full theme-card border theme-border p-5 rounded-xl shadow-lg"):
            with ui.row().classes("w-full justify-between items-center mb-3"):
                with ui.row().classes("items-center gap-2"):
                    ui.label("MONTHLY STATEMENTS LEDGER").classes(
                        "text-xs font-bold tracking-widest text-[#e5c07b] uppercase"
                    )
                    ui.badge(f"{len(rows)} Statements").props("outline").classes("border-[#e5c07b]/40 text-[#e5c07b]")
                ui.label("💡 Click any row to view full itemized expenditures").classes("text-xs text-gray-400 italic")

            if not rows:
                ui.label("No rental statements recorded in database.").classes("text-gray-400 text-sm py-4")
                return

            table = (
                ui.table(
                    columns=columns,
                    rows=rows,
                    row_key="id",
                    pagination={"rowsPerPage": 20},
                )
                .classes("w-full")
                .props("dense dark flat")
            )

            # Render statement number with pill badge for multi-statement months
            table.add_slot(
                "body-cell-statement_number",
                r"""
                <q-td :props="props">
                    <span v-if="props.row.is_consolidated" class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-semibold bg-[#e5c07b]/15 text-[#e5c07b] border border-[#e5c07b]/30">
                        <q-icon name="layers" size="14px" />
                        {{ props.value }}
                    </span>
                    <span v-else class="text-gray-200">
                        {{ props.value }}
                    </span>
                </q-td>
                """,
            )

            # Strip redundant '£' from currency columns and add mint & burgundy cell fills matching Image 4
            table.add_slot(
                "body-cell-gross_income",
                r"""
                <q-td :props="props" class="text-right">
                    {{ props.value.replace('£', '') }}
                </q-td>
                """,
            )
            table.add_slot(
                "body-cell-total_expenditure",
                r"""
                <q-td :props="props" class="text-right">
                    {{ props.value.replace('£', '') }}
                </q-td>
                """,
            )
            table.add_slot(
                "body-cell-mortgage_debit",
                r"""
                <q-td :props="props" class="text-right">
                    {{ props.value.replace('£', '') }}
                </q-td>
                """,
            )
            table.add_slot(
                "body-cell-net_payout",
                r"""
                <q-td :props="props" class="!bg-[#a7f3d0] !text-[#0f172a] !font-bold text-right">
                    {{ props.value.replace('£', '') }}
                </q-td>
                """,
            )
            table.add_slot(
                "body-cell-shortfall",
                r"""
                <q-td :props="props" :class="props.row.raw_shortfall > 0 ? '!bg-[#881337] !text-[#fdfbf7] !font-bold text-right' : '!bg-[#a7f3d0] !text-[#0f172a] !font-bold text-right'">
                    {{ props.value.replace('£', '') }}
                </q-td>
                """,
            )

            # AC-UI-001.2: Row click opens popup dialog with itemized expenditures
            def on_statement_click(e):
                row = e.args[1] if len(e.args) > 1 else e.args[0]
                if isinstance(row, dict):
                    self.show_statement_modal(row)

            table.on("row-click", on_statement_click)

    # [spec: UI-002]
    def render_invoices_table(self) -> None:
        """Render contractor invoice ledger with full sortable columns and deduction match highlighting."""
        invoices = self.db.get_all_contractor_invoices()
        rows = prepare_invoices_table_rows(invoices)

        columns = [
            {"name": "invoice_date", "label": "Date", "field": "invoice_date", "sortable": True, "align": "left"},
            {
                "name": "contractor_name",
                "label": "Contractor",
                "field": "contractor_name",
                "sortable": True,
                "align": "left",
            },
            {
                "name": "invoice_number",
                "label": "Invoice #",
                "field": "invoice_number",
                "sortable": True,
                "align": "left",
            },
            {"name": "gross_amount", "label": "Amount", "field": "gross_amount", "sortable": True, "align": "right"},
            {
                "name": "job_description",
                "label": "Work Description",
                "field": "job_description",
                "sortable": True,
                "align": "left",
            },
        ]

        with ui.card().classes("w-full theme-card border theme-border p-5 rounded-xl shadow-lg"):
            with ui.row().classes("justify-between items-center w-full mb-3"):
                ui.label("CONTRACTOR INVOICES & MAINTENANCE LEDGER").classes(
                    "text-xs font-bold tracking-widest text-[#e5c07b] uppercase"
                )
                ui.badge(f"{len(rows)} Invoices").props("outline").classes("border-[#e5c07b]/40 text-[#e5c07b]")

            if not rows:
                ui.label("No contractor invoices recorded in database.").classes("text-gray-400 text-sm py-4")
                return

            ui.table(
                columns=columns,
                rows=rows,
                row_key="id",
                pagination={"rowsPerPage": 20},
            ).classes("w-full").props("dense dark flat")

    # [spec: UI-003]
    def open_single_file_ingest_dialog(self) -> None:
        """Modal dialog to trigger single PDF file ingestion with progress bar feedback and auto tab navigation."""
        with (
            ui.dialog() as dialog,
            ui.card().classes("theme-card border theme-border p-6 min-w-[500px] max-w-lg"),
        ):
            with ui.row().classes("justify-between items-center w-full mb-2"):
                with ui.row().classes("items-center gap-2"):
                    ui.icon("note_add", size="sm").classes("text-[#e5c07b]")
                    ui.label("Ingest Single PDF File").classes("text-lg font-bold text-[#e5c07b]")
                ui.button(icon="close", on_click=dialog.close).props("flat round dense color=grey")

            ui.label("Enter absolute or relative path to a single statement or invoice PDF:").classes(
                "text-xs text-gray-400 mb-3"
            )

            file_input = (
                ui.input(label="File Path", placeholder="e.g. Resources/Statement_Oct2026.pdf")
                .classes("w-full mb-3")
                .props("outlined dark dense")
            )

            overwrite_checkbox = ui.checkbox(
                "Overwrite existing record if duplicate statement number/reference found"
            ).classes("text-xs text-gray-300 mb-2")

            progress_bar = (
                ui.linear_progress(value=0.0).classes("w-full my-2").props("color=amber track-color=grey-9 stripe")
            )
            progress_bar.set_visibility(False)

            status_label = ui.label("").classes("text-xs text-gray-300 my-2 leading-relaxed")

            def start_single_file_ingest():
                raw_path = file_input.value.strip() if file_input.value else ""
                if not raw_path:
                    status_label.set_text("❌ Please enter a PDF file path")
                    return

                path = Path(raw_path)
                if not path.is_absolute():
                    path = Path.cwd() / path
                path = path.resolve()

                allowed_root = Path.cwd().resolve()
                if not path.is_relative_to(allowed_root):
                    status_label.set_text(
                        f"❌ Security violation: File must be within project root ({allowed_root.name})"
                    )
                    return

                if not path.exists():
                    status_label.set_text(f"❌ File not found: {path}")
                    return
                if not path.is_file() or path.suffix.lower() != ".pdf":
                    status_label.set_text("❌ Selected path is not a .pdf file")
                    return

                # Display progress bar feedback
                progress_bar.set_visibility(True)
                progress_bar.props("indeterminate")
                status_label.set_text(
                    "⏳ Processing single PDF via local Ollama... (reading text & extracting structured data)"
                )

                async def process_async():
                    # Run heavy extraction asynchronously so UI displays the progress bar
                    service = BatchIngestionService(db=self.db, config=self.config)
                    result = await asyncio.to_thread(
                        service.process_file,
                        file_path=path,
                        overwrite=overwrite_checkbox.value,
                    )

                    progress_bar.props(remove="indeterminate")
                    progress_bar.set_value(1.0)

                    if result.status == "ingested":
                        status_label.set_text(
                            f"✅ Successfully ingested as {result.doc_type.upper()}: {result.details} ({result.elapsed_seconds:.2f}s)"
                        )
                        self.refresh_all()
                        ui.notify(f"Ingested {path.name}", type="positive")
                        # Navigate to rent management page with matching tab open
                        self.switch_to_ledger_tab(result.doc_type)
                        # Automatically close modal after brief delay
                        await asyncio.sleep(0.7)
                        dialog.close()

                        # If ingested file is a statement and record_id is present, open the edit statement popup card
                        if result.doc_type == "statement" and result.record_id:
                            self.open_edit_statement_dialog(result.record_id)
                    elif result.status == "duplicate":
                        status_label.set_text(f"⚠️ Skipped duplicate: {result.details}")
                        ui.notify(f"Duplicate file: {path.name}", type="warning")
                    elif result.status == "rejected":
                        status_label.set_text(f"⚠️ Rejected: {result.details}")
                        ui.notify(f"Rejected: {path.name}", type="warning")
                    else:
                        status_label.set_text(f"❌ Status [{result.status}]: {result.details}")
                        ui.notify(f"Failed to ingest: {result.details}", type="negative")

                asyncio.create_task(process_async())

            with ui.row().classes("justify-end gap-3 mt-4"):
                ui.button("Close", on_click=dialog.close).props("flat color=grey")
                ui.button("Start Ingestion", on_click=start_single_file_ingest).classes(
                    "bg-[#e5c07b] text-[#0e1015] font-semibold hover:bg-[#e5c07b]/90 px-4 py-1.5 rounded-lg"
                )

        dialog.open()

    # [spec: UI-003]
    def open_ingest_dialog(self) -> None:
        """Modal dialog to trigger folder ingestion with progress bar feedback and auto tab navigation."""
        with (
            ui.dialog() as dialog,
            ui.card().classes("theme-card border theme-border p-6 min-w-[480px]"),
        ):
            with ui.row().classes("justify-between items-center w-full mb-2"):
                with ui.row().classes("items-center gap-2"):
                    ui.icon("folder_open", size="sm").classes("text-[#e5c07b]")
                    ui.label("Batch Ingest PDF Folder").classes("text-lg font-bold text-[#e5c07b]")
                ui.button(icon="close", on_click=dialog.close).props("flat round dense color=grey")

            ui.label("Enter directory path containing rental statements or invoices:").classes(
                "text-xs text-gray-400 mb-4"
            )

            folder_input = (
                ui.input(label="Folder Path", value="Resources").classes("w-full mb-4").props("outlined dark dense")
            )

            progress_bar = ui.linear_progress(value=0.0).classes("w-full my-2").props("color=amber track-color=grey-9")
            progress_bar.set_visibility(False)

            status_label = ui.label("").classes("text-xs text-gray-300 mt-2")

            def start_ingest():
                raw_folder = folder_input.value.strip() if folder_input.value else ""
                if not raw_folder:
                    status_label.set_text("❌ Please enter a folder path")
                    return

                path = Path(raw_folder)
                if not path.is_absolute():
                    path = Path.cwd() / path
                path = path.resolve()

                allowed_root = Path.cwd().resolve()
                if not path.is_relative_to(allowed_root):
                    status_label.set_text(
                        f"❌ Security violation: Directory must be within project root ({allowed_root.name})"
                    )
                    return

                if not path.exists() or not path.is_dir():
                    status_label.set_text(f"❌ Directory not found: {path}")
                    return

                progress_bar.set_visibility(True)
                progress_bar.set_value(0.0)
                status_label.set_text("⏳ Scanning folder for PDF documents...")

                async def process_batch_async():
                    service = BatchIngestionService(db=self.db, config=self.config)
                    pdf_files = await asyncio.to_thread(service.scan_directory, path)
                    total_files = len(pdf_files)
                    if total_files == 0:
                        status_label.set_text("⚠️ No PDF files found in directory")
                        return

                    def on_progress(current_idx: int, total: int, file_path: Path, result: Any | None):
                        fraction = current_idx / total if total > 0 else 0.0
                        progress_bar.set_value(fraction)
                        if result is None:
                            status_label.set_text(f"⏳ Processing ({current_idx}/{total}): {file_path.name}...")
                        else:
                            status_label.set_text(
                                f"[{current_idx}/{total}] {file_path.name} -> {result.status.upper()} ({result.elapsed_seconds:.1f}s)"
                            )

                    report = await asyncio.to_thread(
                        service.process_directory,
                        folder_path=path,
                        progress_callback=on_progress,
                    )

                    progress_bar.set_value(1.0)
                    status_label.set_text(
                        f"✅ Processed {report.total_files} files: {report.ingested_statements} statements, "
                        f"{report.ingested_invoices} invoices ({report.total_elapsed_seconds:.2f}s)"
                    )
                    self.refresh_all()
                    ui.notify(
                        f"Ingested {report.ingested_statements + report.ingested_invoices} documents", type="positive"
                    )

                    # If statements or invoices were ingested, navigate to rent management tab with appropriate subtab
                    if report.ingested_statements > 0:
                        self.switch_to_ledger_tab("statement")
                    elif report.ingested_invoices > 0:
                        self.switch_to_ledger_tab("invoice")

                    await asyncio.sleep(0.7)
                    dialog.close()

                asyncio.create_task(process_batch_async())

            with ui.row().classes("justify-end gap-3 mt-4"):
                ui.button("Cancel", on_click=dialog.close).props("flat color=grey")
                ui.button("Start Ingestion", on_click=start_ingest).classes(
                    "bg-[#e5c07b] text-[#0e1015] font-semibold hover:bg-[#e5c07b]/90 px-4 py-1.5 rounded-lg"
                )

        dialog.open()

    # [spec: ISSUE-001]
    # [spec: ISSUE-002]
    def open_create_issue_dialog(self) -> None:
        """Modal dialog to manually create a maintenance issue."""
        from datetime import datetime

        today_str = datetime.now().strftime("%d-%m-%Y")

        with ui.dialog() as dialog, ui.card().classes("theme-card border theme-border p-6 min-w-[500px] max-w-xl"):
            ui.label("Add Maintenance Issue").classes("text-lg font-bold text-[#e5c07b] mb-1")
            ui.label("Record a new property maintenance item or repair request.").classes("text-xs text-[#a8a29e] mb-4")

            title_input = (
                ui.input(label="Topic / Issue Title *", placeholder="e.g. Boiler repair / Radiator leaking")
                .classes("w-full mb-3")
                .props("outlined dark")
            )

            with ui.row().classes("w-full gap-4 mb-3"):
                category_select = (
                    ui.select(
                        options=[
                            "General",
                            "Plumbing",
                            "Electrical",
                            "Heating / Boiler",
                            "Roofing",
                            "Appliance",
                            "Exterior",
                        ],
                        value="General",
                        label="Category",
                    )
                    .classes("flex-1")
                    .props("outlined dark dense")
                )
                priority_select = (
                    ui.select(
                        options=["Low", "Normal", "Urgent"],
                        value="Normal",
                        label="Priority",
                    )
                    .classes("flex-1")
                    .props("outlined dark dense")
                )

            with ui.row().classes("w-full gap-4 mb-3"):
                contractor_input = (
                    ui.input(label="Contractor Name", placeholder="e.g. British Gas / Metro Plumbers")
                    .classes("flex-1")
                    .props("outlined dark dense")
                )
                cost_input = (
                    ui.input(label="Initial Cost (£)", value="0.00").classes("flex-1").props("outlined dark dense")
                )

            with ui.row().classes("w-full gap-4 mb-3"):
                date_input = (
                    ui.input(label="Reported Date (DD-MM-YYYY)", value=today_str)
                    .classes("flex-1")
                    .props("outlined dark dense")
                )

            description_input = (
                ui.textarea(
                    label="Initial Description / Details", placeholder="Describe the issue symptoms or agreed work..."
                )
                .classes("w-full mb-4")
                .props("outlined dark rows=3")
            )

            def save_issue():
                t = title_input.value.strip() if title_input.value else ""
                if not t:
                    ui.notify("Please enter an issue topic/title", type="warning")
                    return
                try:
                    c_val = Decimal(str(cost_input.value.strip().replace("£", "") or "0.00"))
                except Exception:
                    c_val = Decimal("0.00")

                self.db.create_maintenance_issue(
                    title=t,
                    category=category_select.value,
                    status="Open",
                    priority=priority_select.value,
                    contractor_name=contractor_input.value.strip() if contractor_input.value else None,
                    total_cost=c_val,
                    reported_date=date_input.value.strip() or today_str,
                    initial_note=description_input.value.strip() if description_input.value else None,
                )
                dialog.close()
                self.refresh_all()
                ui.notify(f"Issue '{t}' created successfully", type="positive")

            with ui.row().classes("justify-end gap-3"):
                ui.button("Cancel", on_click=dialog.close).props("flat color=grey")
                ui.button("Create Issue", on_click=save_issue).classes(
                    "bg-[#e5c07b] text-[#0e1015] font-semibold hover:bg-[#e5c07b]/90 px-4 py-1.5 rounded-lg"
                )

        dialog.open()

    # [spec: ISSUE-001]
    # [spec: ISSUE-002]
    def _render_issue_status_actions(self, issue_id: int, cur_status: str, dialog: Any) -> None:
        """Render status action buttons for issue lifecycle transitions."""
        with ui.row().classes("w-full items-center gap-3 mb-4 bg-black/20 p-2.5 rounded-lg border border-white/5"):
            ui.label("Change Status:").classes("text-xs font-semibold text-[#d1cbbe]")
            for st in ["Open", "In Progress", "Resolved"]:
                if st != cur_status:
                    if st == "Resolved":
                        ui.button(
                            "Mark as Resolved", on_click=lambda: self.open_resolve_dialog(issue_id, dialog)
                        ).props("dense outline").classes(
                            "text-xs px-2.5 py-1 text-[#86efac] border-[#86efac]/40 hover:bg-[#86efac]/10 rounded"
                        )
                    else:

                        def change_st(target_st=st):
                            self.db.update_issue_status(issue_id, target_st)
                            dialog.close()
                            self.open_issue_detail_dialog(issue_id)
                            self.refresh_all()
                            ui.notify(f"Issue moved to {target_st}", type="info")

                        ui.button(f"Mark as {st}", on_click=change_st).props("dense outline").classes(
                            "text-xs px-2.5 py-1 text-[#e5c07b] border-[#e5c07b]/40 hover:bg-[#e5c07b]/10 rounded"
                        )

    # [spec: ISSUE-001]
    def _render_pinned_invoices_section(self, issue_id: int, pinned: list[dict[str, Any]], dialog: Any) -> None:
        """Render pinned invoices and invoice attachment dropdown."""
        ui.label(f"PINNED CONTRACTOR INVOICES ({len(pinned)})").classes(
            "text-xs font-bold text-[#e5c07b] tracking-wider mb-1"
        )
        if pinned:
            with ui.column().classes("w-full gap-2 mb-4"):
                for pin_inv in pinned:
                    inv_amt = Decimal(str(pin_inv.get("gross_amount", "0.00")))
                    with ui.row().classes(
                        "w-full justify-between items-center p-2 rounded bg-[#121622] border border-[#e5c07b]/20 text-xs"
                    ):
                        with ui.row().classes("items-center gap-2"):
                            ui.icon("receipt", size="xs").classes("text-[#e5c07b]")
                            ui.label(
                                f"{pin_inv['contractor_name']} - #{pin_inv['invoice_number']} ({pin_inv['invoice_date']})"
                            ).classes("font-semibold text-white")
                            ui.label(f"£{inv_amt:,.2f}").classes("text-[#86efac] font-bold")

                        def unpin(inv_id=pin_inv["id"]):
                            self.db.unpin_invoice_from_issue(issue_id, inv_id)
                            dialog.close()
                            self.open_issue_detail_dialog(issue_id)
                            self.refresh_all()
                            ui.notify("Invoice unpinned", type="info")

                        ui.button(icon="close", on_click=unpin).props("flat round dense size=xs").classes(
                            "text-red-400 hover:bg-red-500/10"
                        )
        else:
            ui.label("No invoices pinned yet.").classes("text-xs text-[#a8a29e] italic mb-3")

        all_invoices = self.db.get_all_contractor_invoices()
        unpinned = [i for i in all_invoices if i["id"] not in [p["id"] for p in pinned]]
        if unpinned:
            with ui.row().classes("w-full items-center gap-2 mb-4"):
                inv_opts = {
                    i["id"]: f"{i['contractor_name']} #{i['invoice_number']} (£{Decimal(i['gross_amount']):,.2f})"
                    for i in unpinned
                }
                inv_select = (
                    ui.select(options=inv_opts, label="Pin an invoice to this issue")
                    .classes("flex-1")
                    .props("outlined dark dense")
                )

                def do_pin():
                    if inv_select.value:
                        self.db.pin_invoice_to_issue(issue_id, int(inv_select.value))
                        dialog.close()
                        self.open_issue_detail_dialog(issue_id)
                        self.refresh_all()
                        ui.notify("Invoice pinned to issue", type="positive")

                ui.button("Pin Invoice", on_click=do_pin).props("dense").classes(
                    "bg-[#e5c07b] text-[#0e1015] font-semibold text-xs px-3 py-2 rounded"
                )

    # [spec: ISSUE-002]
    def _render_notes_thread_section(self, issue_id: int, notes: list[dict[str, Any]], dialog: Any) -> None:
        """Render notes thread and note entry box."""
        ui.label("PROGRESS NOTES & COMMENT THREAD").classes("text-xs font-bold text-[#e5c07b] tracking-wider mb-1")
        notes_container = ui.column().classes(
            "w-full max-h-56 overflow-y-auto gap-2 p-3 bg-black/30 rounded-lg border border-white/5 mb-3"
        )
        with notes_container:
            if not notes:
                ui.label("No progress notes posted yet.").classes("text-xs text-[#a8a29e] italic")
            else:
                for n in notes:
                    with ui.column().classes("w-full bg-[#181d2a] p-2.5 rounded border border-[#e5c07b]/15 gap-1"):
                        with ui.row().classes("w-full justify-between items-center text-[11px] text-[#a8a29e]"):
                            ui.label(n.get("author", "Landlord")).classes("font-bold text-[#e5c07b]")
                            ui.label(n.get("created_at") or "").classes("text-gray-400")
                        ui.label(n.get("comment", "")).classes("text-xs text-[#fdfbf7] break-words")

        with ui.row().classes("w-full gap-2 items-center"):
            note_input = (
                ui.input(placeholder="Write a progress update or contractor note...")
                .classes("flex-1")
                .props("outlined dark dense")
            )

            def post_note():
                txt = note_input.value.strip() if note_input.value else ""
                if not txt:
                    return
                self.db.add_issue_note(issue_id, txt)
                dialog.close()
                self.open_issue_detail_dialog(issue_id)
                self.refresh_all()
                ui.notify("Note added to thread", type="positive")

            ui.button("Post Note", on_click=post_note).props("dense").classes(
                "bg-[#e5c07b] text-[#0e1015] font-semibold text-xs px-4 py-2 rounded"
            )

    # [spec: ISSUE-001]
    # [spec: ISSUE-002]
    def open_issue_detail_dialog(self, issue_id: int) -> None:
        """Modal dialog displaying issue timeline, comment thread, pinned invoices, and status actions."""
        issue = self.db.get_maintenance_issue_by_id(issue_id)
        if not issue:
            ui.notify("Issue not found", type="negative")
            return

        with ui.dialog() as dialog, ui.card().classes("theme-card border theme-border p-6 min-w-[650px] max-w-3xl"):
            with ui.row().classes("w-full justify-between items-start mb-2"):
                with ui.column().classes("gap-1"):
                    ui.label(issue["title"]).classes("text-lg font-bold text-[#e5c07b]")
                    with ui.row().classes("items-center gap-2 text-xs text-[#a8a29e]"):
                        ui.label(f"Category: {issue.get('category', 'General')}")
                        ui.label("•")
                        ui.label(f"Reported: {issue.get('reported_date', 'N/A')}")
                        if issue.get("resolved_date"):
                            ui.label("•")
                            ui.label(f"Resolved: {issue.get('resolved_date')}")

                cur_status = issue.get("status", "Open")
                status_color_map = {
                    "Open": "bg-amber-500/20 text-amber-300 border-amber-500/40",
                    "In Progress": "bg-cyan-500/20 text-cyan-300 border-cyan-500/40",
                    "Resolved": "bg-emerald-500/20 text-emerald-300 border-emerald-500/40",
                }
                badge_cls = status_color_map.get(cur_status, "bg-gray-500/20 text-gray-300 border-gray-500/40")
                ui.badge(cur_status).classes(f"text-xs px-3 py-1 font-bold border {badge_cls}")

            cost_val = Decimal(str(issue.get("total_cost", "0.00")))
            with ui.row().classes(
                "w-full bg-[#181d2a]/80 border border-[#e5c07b]/20 p-3 rounded-lg justify-between items-center mb-4"
            ):
                with ui.column().classes("gap-0"):
                    ui.label("TOTAL COST SO FAR").classes("text-[10px] text-[#a8a29e] font-bold tracking-wider")
                    ui.label(f"£{cost_val:,.2f}").classes("text-base font-bold text-[#86efac]")
                with ui.column().classes("gap-0 items-end"):
                    ui.label("ASSIGNED CONTRACTOR").classes("text-[10px] text-[#a8a29e] font-bold tracking-wider")
                    ui.label(issue.get("contractor_name") or "None").classes("text-sm font-semibold text-[#fdfbf7]")

            self._render_issue_status_actions(issue_id, cur_status, dialog)
            self._render_pinned_invoices_section(issue_id, issue.get("pinned_invoices") or [], dialog)
            self._render_notes_thread_section(issue_id, issue.get("notes") or [], dialog)

            with ui.row().classes("w-full justify-end mt-4"):
                ui.button("Close", on_click=dialog.close).props("flat color=grey")

        dialog.open()

    # [spec: ISSUE-002]
    def open_resolve_dialog(self, issue_id: int, parent_dialog: Any = None) -> None:
        """Prompt for final closeout note and resolution date when moving to Resolved."""
        from datetime import datetime

        today_str = datetime.now().strftime("%d-%m-%Y")

        with ui.dialog() as res_dialog, ui.card().classes("theme-card border theme-border p-6 min-w-[450px]"):
            ui.label("Resolve Maintenance Issue").classes("text-lg font-bold text-[#86efac] mb-1")
            ui.label("Record final resolution details and close out the maintenance issue.").classes(
                "text-xs text-[#a8a29e] mb-4"
            )

            res_date_input = (
                ui.input(label="Resolution Date (DD-MM-YYYY)", value=today_str)
                .classes("w-full mb-3")
                .props("outlined dark dense")
            )

            res_note_input = (
                ui.textarea(
                    label="Final Closeout Note *",
                    placeholder="e.g. British Gas engineer replaced valve and tested system. Boiler operational.",
                )
                .classes("w-full mb-4")
                .props("outlined dark rows=3")
            )

            def finalize_resolve():
                note_txt = res_note_input.value.strip() if res_note_input.value else ""
                r_date = res_date_input.value.strip() or today_str
                self.db.update_issue_status(issue_id, "Resolved", resolved_date=r_date, resolution_note=note_txt)
                res_dialog.close()
                if parent_dialog:
                    parent_dialog.close()
                self.open_issue_detail_dialog(issue_id)
                self.refresh_all()
                ui.notify("Issue marked as Resolved with closeout note", type="positive")

            with ui.row().classes("w-full justify-end gap-3"):
                ui.button("Cancel", on_click=res_dialog.close).props("flat color=grey")
                ui.button("Confirm Resolution", on_click=finalize_resolve).classes(
                    "bg-[#86efac] text-[#0e1015] font-semibold px-4 py-1.5 rounded-lg"
                )

        res_dialog.open()

    # [spec: ISSUE-001]
    # [spec: ISSUE-002]
    def render_issues_board(self) -> None:
        """Render the complete Issues & Maintenance Board matching Quiet Luxury styling."""
        issues = self.db.get_all_maintenance_issues(include_suggested=True)
        confirmed_issues = [i for i in issues if not i.get("is_suggested", False)]
        suggested_issues = [i for i in issues if i.get("is_suggested", False)]

        fy_cost = calculate_financial_year_maintenance_costs(confirmed_issues)
        open_count = sum(1 for i in confirmed_issues if i.get("status") in ("Open", "In Progress"))
        resolved_count = sum(1 for i in confirmed_issues if i.get("status") == "Resolved")

        # Top Metric & Actions Row
        with ui.row().classes("w-full justify-between items-center mb-3"):
            with ui.row().classes("items-center gap-4"):
                # Total FY Cost Card
                with ui.card().classes("theme-card border theme-border px-5 py-3 rounded-xl shadow"):
                    ui.label("TOTAL MAINTENANCE COST (ACTIVE FY)").classes(
                        "text-[10px] font-bold text-[#e5c07b] tracking-wider uppercase"
                    )
                    ui.label(f"£{fy_cost:,.2f}").classes("text-xl font-bold text-[#86efac]")

                # Status Badges
                with ui.card().classes(
                    "theme-card border theme-border px-5 py-3 rounded-xl shadow flex-row items-center gap-4"
                ):
                    with ui.column().classes("gap-0"):
                        ui.label("ACTIVE ISSUES").classes(
                            "text-[10px] font-bold text-[#a8a29e] tracking-wider uppercase"
                        )
                        ui.label(str(open_count)).classes("text-xl font-bold text-[#e5c07b]")
                    with ui.column().classes("gap-0"):
                        ui.label("RESOLVED").classes("text-[10px] font-bold text-[#a8a29e] tracking-wider uppercase")
                        ui.label(str(resolved_count)).classes("text-xl font-bold text-[#86efac]")

            # Action Buttons: Sync from Invoices & Create New Issue
            with ui.row().classes("items-center gap-3"):
                # AC-ISSUE-003.3: Dedicated UI action to trigger retrospective invoice synchronization
                def handle_sync_invoices():
                    new_ids = self.db.sync_issues_from_invoices()
                    self.refresh_all()
                    if new_ids:
                        ui.notify(
                            f"Synced {len(new_ids)} suggested issue{'s' if len(new_ids) != 1 else ''} from past invoices",
                            type="positive",
                        )
                    else:
                        ui.notify("All contractor invoices are already mapped to issues", type="info")

                ui.button(
                    "Sync from Invoices",
                    icon="sync",
                    on_click=handle_sync_invoices,
                ).props("outline").classes(
                    "border-[#e5c07b]/50 text-[#e5c07b] font-bold text-xs px-3.5 py-2 rounded-xl hover:bg-[#e5c07b]/10"
                )

                ui.button(
                    "+ Add Maintenance Issue",
                    icon="add_circle",
                    on_click=self.open_create_issue_dialog,
                ).classes(
                    "bg-[#e5c07b] text-[#0e1015] font-bold text-xs px-4 py-2.5 rounded-xl shadow-md hover:bg-[#e5c07b]/90"
                )

        # Suggested Issues Banner (AC-ISSUE-001.1)
        if suggested_issues:
            with ui.card().classes("w-full bg-[#181d2a] border border-amber-500/40 p-4 rounded-xl shadow-md mb-3"):
                with (
                    ui.row().classes("w-full justify-between items-center mb-2"),
                    ui.row().classes("items-center gap-2"),
                ):
                    ui.icon("auto_awesome", size="sm").classes("text-amber-400")
                    ui.label(f"SUGGESTED MAINTENANCE ISSUES ({len(suggested_issues)})").classes(
                        "text-xs font-bold text-amber-300 tracking-wider"
                    )
                    ui.label("Auto-detected from contractor invoices").classes("text-xs text-[#a8a29e]")

                with ui.column().classes("w-full gap-2"):
                    for sug in suggested_issues:
                        sug_id = sug["id"]
                        sug_cost = Decimal(str(sug.get("total_cost", "0.00")))
                        with ui.row().classes(
                            "w-full justify-between items-center bg-[#121622] p-2.5 rounded-lg border border-white/5"
                        ):
                            with ui.row().classes("items-center gap-3"):
                                ui.label(sug["title"]).classes("text-sm font-semibold text-white")
                                ui.label(f"£{sug_cost:,.2f}").classes("text-xs font-bold text-[#86efac]")
                                ui.label(f"Date: {sug.get('reported_date', '')}").classes("text-xs text-[#a8a29e]")

                            with ui.row().classes("items-center gap-2"):

                                def confirm_sug(sid=sug_id):
                                    self.db.confirm_suggested_issue(sid)
                                    self.refresh_all()
                                    ui.notify("Issue confirmed and added to board", type="positive")

                                def dismiss_sug(sid=sug_id):
                                    self.db.dismiss_suggested_issue(sid)
                                    self.refresh_all()
                                    ui.notify("Suggestion dismissed", type="info")

                                ui.button("Confirm Issue", icon="check", on_click=confirm_sug).props("dense").classes(
                                    "bg-[#86efac] text-[#0e1015] font-bold text-xs px-3 py-1 rounded"
                                )
                                ui.button("Dismiss", icon="close", on_click=dismiss_sug).props("dense flat").classes(
                                    "text-red-400 hover:bg-red-500/10 text-xs px-3 py-1 rounded"
                                )

        # Active & Resolved Issues Table / Cards
        table_rows = prepare_maintenance_table_rows(confirmed_issues)

        with ui.card().classes("w-full theme-card border theme-border p-5 rounded-xl shadow-lg"):
            with ui.row().classes("justify-between items-center w-full mb-3"):
                ui.label("MAINTENANCE ISSUES REGISTER").classes(
                    "text-xs font-bold tracking-widest text-[#e5c07b] uppercase"
                )
                ui.badge(f"{len(table_rows)} Total Records").props("outline").classes(
                    "border-[#e5c07b]/40 text-[#e5c07b]"
                )

            if not table_rows:
                ui.label(
                    "No maintenance issues recorded yet. Click '+ Add Maintenance Issue' above to log your first item."
                ).classes("text-gray-400 text-sm py-4")
                return

            columns = [
                {"name": "status", "label": "Status", "field": "status", "sortable": True, "align": "center"},
                {"name": "title", "label": "Topic / Issue", "field": "title", "sortable": True, "align": "left"},
                {"name": "category", "label": "Category", "field": "category", "sortable": True, "align": "left"},
                {
                    "name": "contractor_name",
                    "label": "Contractor",
                    "field": "contractor_name",
                    "sortable": True,
                    "align": "left",
                },
                {
                    "name": "cost_formatted",
                    "label": "Cost Paid",
                    "field": "cost_formatted",
                    "sortable": True,
                    "align": "right",
                },
                {
                    "name": "reported_date",
                    "label": "Reported",
                    "field": "reported_date",
                    "sortable": True,
                    "align": "center",
                },
                {
                    "name": "resolved_date",
                    "label": "Resolved",
                    "field": "resolved_date",
                    "sortable": True,
                    "align": "center",
                },
                {"name": "notes_count", "label": "Notes", "field": "notes_count", "sortable": True, "align": "center"},
                {
                    "name": "pinned_invoices_count",
                    "label": "Invoices",
                    "field": "pinned_invoices_count",
                    "sortable": True,
                    "align": "center",
                },
                {"name": "actions", "label": "Action", "field": "actions", "align": "center"},
            ]

            table = (
                ui.table(
                    columns=columns,
                    rows=table_rows,
                    row_key="id",
                    pagination={"rowsPerPage": 15},
                )
                .classes("w-full")
                .props("dense dark flat")
            )

            # Custom slots for status pill and action button
            table.add_slot(
                "body-cell-status",
                r"""
                <q-td :props="props">
                    <span v-if="props.row.status === 'Resolved'" class="px-2 py-0.5 rounded text-xs font-bold bg-emerald-900/60 text-emerald-300 border border-emerald-500/40">Resolved</span>
                    <span v-else-if="props.row.status === 'In Progress'" class="px-2 py-0.5 rounded text-xs font-bold bg-cyan-900/60 text-cyan-300 border border-cyan-500/40">In Progress</span>
                    <span v-else class="px-2 py-0.5 rounded text-xs font-bold bg-amber-900/60 text-amber-300 border border-amber-500/40">Open</span>
                </q-td>
                """,
            )

            table.add_slot(
                "body-cell-actions",
                r"""
                <q-td :props="props">
                    <q-btn flat dense round icon="visibility" size="xs" color="amber" @click="() => $parent.$emit('view_issue', props.row.id)">
                        <q-tooltip>View Thread & Details</q-tooltip>
                    </q-btn>
                </q-td>
                """,
            )

            table.on("view_issue", lambda e: self.open_issue_detail_dialog(int(e.args)))

    # [spec: COMP-001]
    def open_create_compliance_dialog(self) -> None:
        """Modal dialog to manually enter a new statutory compliance certificate."""
        from datetime import datetime

        today_str = datetime.now().strftime("%d-%m-%Y")

        with (
            ui.dialog() as dialog,
            ui.card().classes("theme-card border theme-border p-7 w-[680px] max-w-2xl flex flex-col"),
        ):
            with ui.row().classes("justify-between items-center w-full mb-3"):
                with ui.row().classes("items-center gap-2"):
                    ui.icon("verified", size="sm").classes("text-[#e5c07b]")
                    ui.label("Add Compliance Certificate").classes("text-xl font-bold text-gray-100")
                ui.button(icon="close", on_click=dialog.close).props("flat round dense color=grey")

            ui.label(
                "Record statutory safety inspections, insurance policies, or custom compliance certificates."
            ).classes("text-xs text-[#a8a29e] mb-4")

            cert_type_select = (
                ui.select(
                    options=[
                        "Gas Safety (CP12)",
                        "EICR (Electrical)",
                        "EPC (Energy Performance)",
                        "Landlord Insurance",
                        "Annual Boiler Service",
                        "Custom Certificate",
                    ],
                    value="Gas Safety (CP12)",
                    label="Certificate Type *",
                )
                .classes("w-full mb-3")
                .props("outlined dark dense")
            )

            title_input = (
                ui.input(
                    label="Certificate Title *",
                    value="Gas Safety Certificate (CP12)",
                )
                .classes("w-full mb-3")
                .props("outlined dark dense")
            )

            def on_type_change():
                val = cert_type_select.value
                if val == "Gas Safety (CP12)":
                    title_input.value = "Gas Safety Certificate (CP12)"
                elif val == "EICR (Electrical)":
                    title_input.value = "Electrical Installation Condition Report (EICR)"
                elif val == "EPC (Energy Performance)":
                    title_input.value = "Energy Performance Certificate (EPC)"
                elif val == "Landlord Insurance":
                    title_input.value = "Landlord Buildings & Contents Insurance"
                elif val == "Annual Boiler Service":
                    title_input.value = "Annual Boiler Service & Inspection"

            cert_type_select.on_value_change(on_type_change)

            with ui.row().classes("w-full gap-4 mb-3"):
                provider_input = (
                    ui.input(label="Provider / Contractor", placeholder="e.g. British Gas, Gas Safe engineer")
                    .classes("flex-1")
                    .props("outlined dark dense")
                )
                ref_input = (
                    ui.input(label="Reference / Certificate #", placeholder="e.g. CP12-99824")
                    .classes("flex-1")
                    .props("outlined dark dense")
                )

            with ui.row().classes("w-full gap-4 mb-3"):
                issue_date_input = (
                    ui.input(label="Issue / Inspection Date (DD-MM-YYYY) *", value=today_str)
                    .classes("flex-1")
                    .props("outlined dark dense")
                )
                expiry_date_input = (
                    ui.input(label="Renewal Due / Expiry Date (DD-MM-YYYY) *", placeholder="DD-MM-YYYY")
                    .classes("flex-1")
                    .props("outlined dark dense")
                )

            with ui.row().classes("w-full gap-4 mb-3"):
                cost_input = (
                    ui.input(label="Inspection / Policy Cost (£)", value="0.00")
                    .classes("flex-1")
                    .props("outlined dark dense")
                )
                epc_rating_select = (
                    ui.select(
                        options=["None", "A", "B", "C", "D", "E", "F", "G"],
                        value="None",
                        label="EPC Rating (If applicable)",
                    )
                    .classes("flex-1")
                    .props("outlined dark dense")
                )

            notes_input = (
                ui.textarea(
                    label="Notes / Recommendations",
                    placeholder="e.g. System tested and passed. No remedial works required.",
                )
                .classes("w-full mb-4")
                .props("outlined dark rows=2")
            )

            def save_cert():
                t = title_input.value.strip() if title_input.value else ""
                i_date = issue_date_input.value.strip() if issue_date_input.value else ""
                e_date = expiry_date_input.value.strip() if expiry_date_input.value else ""
                if not t:
                    ui.notify("Please enter a certificate title", type="warning")
                    return
                if not e_date:
                    ui.notify("Please enter a renewal due / expiry date", type="warning")
                    return

                try:
                    c_val = Decimal(str(cost_input.value.strip().replace("£", "") or "0.00"))
                except Exception:
                    c_val = Decimal("0.00")

                epc_val = epc_rating_select.value if epc_rating_select.value != "None" else None

                self.db.create_compliance_certificate(
                    certificate_type=cert_type_select.value,
                    title=t,
                    issue_date=i_date,
                    expiry_date=e_date,
                    provider=provider_input.value.strip() if provider_input.value else None,
                    reference_number=ref_input.value.strip() if ref_input.value else None,
                    cost=c_val,
                    epc_rating=epc_val,
                    notes=notes_input.value.strip() if notes_input.value else None,
                )
                dialog.close()
                self.refresh_all()
                ui.notify(f"Certificate '{t}' added successfully", type="positive")

            with ui.row().classes("justify-end gap-3"):
                ui.button("Cancel", on_click=dialog.close).props("flat color=grey")
                ui.button("Save Certificate", on_click=save_cert).classes(
                    "bg-[#e5c07b] text-[#0e1015] font-semibold hover:bg-[#e5c07b]/90 px-4 py-1.5 rounded-lg"
                )

        dialog.open()

    # [spec: COMP-001]
    def open_edit_compliance_dialog(self, cert_id: int) -> None:
        """Modal dialog to edit or update an existing statutory compliance certificate."""
        cert = self.db.get_compliance_certificate_by_id(cert_id)
        if not cert:
            ui.notify("Certificate record not found", type="negative")
            return

        with (
            ui.dialog() as dialog,
            ui.card().classes("theme-card border theme-border p-7 w-[680px] max-w-2xl flex flex-col"),
        ):
            with ui.row().classes("justify-between items-center w-full mb-3"):
                with ui.row().classes("items-center gap-2"):
                    ui.icon("edit", size="sm").classes("text-[#e5c07b]")
                    ui.label(f"Edit Certificate: {cert['title']}").classes("text-xl font-bold text-gray-100")
                ui.button(icon="close", on_click=dialog.close).props("flat round dense color=grey")

            cert_type_select = (
                ui.select(
                    options=[
                        "Gas Safety (CP12)",
                        "EICR (Electrical)",
                        "EPC (Energy Performance)",
                        "Landlord Insurance",
                        "Annual Boiler Service",
                        "Custom Certificate",
                    ],
                    value=cert.get("certificate_type", "Gas Safety (CP12)"),
                    label="Certificate Type *",
                )
                .classes("w-full mb-3")
                .props("outlined dark dense")
            )

            title_input = (
                ui.input(
                    label="Certificate Title *",
                    value=cert.get("title", ""),
                )
                .classes("w-full mb-3")
                .props("outlined dark dense")
            )

            with ui.row().classes("w-full gap-4 mb-3"):
                provider_input = (
                    ui.input(label="Provider / Contractor", value=cert.get("provider") or "")
                    .classes("flex-1")
                    .props("outlined dark dense")
                )
                ref_input = (
                    ui.input(label="Reference / Certificate #", value=cert.get("reference_number") or "")
                    .classes("flex-1")
                    .props("outlined dark dense")
                )

            with ui.row().classes("w-full gap-4 mb-3"):
                issue_date_input = (
                    ui.input(label="Issue / Inspection Date (DD-MM-YYYY) *", value=cert.get("issue_date", ""))
                    .classes("flex-1")
                    .props("outlined dark dense")
                )
                expiry_date_input = (
                    ui.input(label="Renewal Due / Expiry Date (DD-MM-YYYY) *", value=cert.get("expiry_date", ""))
                    .classes("flex-1")
                    .props("outlined dark dense")
                )

            with ui.row().classes("w-full gap-4 mb-3"):
                cost_input = (
                    ui.input(label="Inspection / Policy Cost (£)", value=cert.get("cost", "0.00"))
                    .classes("flex-1")
                    .props("outlined dark dense")
                )
                epc_rating_select = (
                    ui.select(
                        options=["None", "A", "B", "C", "D", "E", "F", "G"],
                        value=cert.get("epc_rating") or "None",
                        label="EPC Rating (If applicable)",
                    )
                    .classes("flex-1")
                    .props("outlined dark dense")
                )

            notes_input = (
                ui.textarea(
                    label="Notes / Recommendations",
                    value=cert.get("notes") or "",
                )
                .classes("w-full mb-4")
                .props("outlined dark rows=2")
            )

            def do_update():
                t = title_input.value.strip() if title_input.value else ""
                i_date = issue_date_input.value.strip() if issue_date_input.value else ""
                e_date = expiry_date_input.value.strip() if expiry_date_input.value else ""
                if not t:
                    ui.notify("Please enter a certificate title", type="warning")
                    return
                if not e_date:
                    ui.notify("Please enter a renewal due / expiry date", type="warning")
                    return

                try:
                    c_val = Decimal(str(cost_input.value.strip().replace("£", "") or "0.00"))
                except Exception:
                    c_val = Decimal("0.00")

                epc_val = epc_rating_select.value if epc_rating_select.value != "None" else None

                self.db.update_compliance_certificate(
                    cert_id=cert_id,
                    certificate_type=cert_type_select.value,
                    title=t,
                    issue_date=i_date,
                    expiry_date=e_date,
                    provider=provider_input.value.strip() if provider_input.value else None,
                    reference_number=ref_input.value.strip() if ref_input.value else None,
                    cost=c_val,
                    epc_rating=epc_val,
                    notes=notes_input.value.strip() if notes_input.value else None,
                )
                dialog.close()
                self.refresh_all()
                ui.notify(f"Certificate '{t}' updated successfully", type="positive")

            def do_delete():
                self.db.delete_compliance_certificate(cert_id)
                dialog.close()
                self.refresh_all()
                ui.notify("Certificate deleted", type="info")

            with ui.row().classes("w-full justify-between items-center"):
                ui.button("Delete", icon="delete", on_click=do_delete).props("flat color=negative dense").classes(
                    "text-xs text-rose-400 hover:bg-rose-500/10"
                )
                with ui.row().classes("gap-3"):
                    ui.button("Cancel", on_click=dialog.close).props("flat color=grey")
                    ui.button("Update Certificate", on_click=do_update).classes(
                        "bg-[#e5c07b] text-[#0e1015] font-semibold hover:bg-[#e5c07b]/90 px-4 py-1.5 rounded-lg"
                    )

        dialog.open()

    # [spec: COMP-001]
    def render_compliance_register(self) -> None:
        """Render dedicated Statutory Compliance & Certificates Register matching Quiet Luxury styling.

        Implements AC-COMP-001.1 through AC-COMP-001.5:
        - Box for each certificate
        - Valid (green), Expiring Soon (amber within 90 days), Expired (red) status pills
        - Manual add/edit dialogs
        """
        raw_certs = self.db.get_all_compliance_certificates()

        # Seed standard default statutory certificates if database register is empty
        if not raw_certs:
            self._seed_default_compliance_certificates()
            raw_certs = self.db.get_all_compliance_certificates()

        formatted_certs = [format_compliance_box_data(c) for c in raw_certs]

        total_count = len(formatted_certs)
        valid_count = sum(1 for c in formatted_certs if c["status"] == "VALID")
        expiring_count = sum(1 for c in formatted_certs if c["status"] == "EXPIRING_SOON")
        expired_count = sum(1 for c in formatted_certs if c["status"] == "EXPIRED")

        # Top Metric Header Row
        with ui.row().classes("w-full justify-between items-center mb-4"):
            with ui.row().classes("items-center gap-4"):
                # Total Tracked
                with ui.card().classes("theme-card border theme-border px-5 py-3 rounded-xl shadow"):
                    ui.label("CERTIFICATES TRACKED").classes(
                        "text-[10px] font-bold text-[#e5c07b] tracking-wider uppercase"
                    )
                    ui.label(str(total_count)).classes("text-xl font-bold text-white")

                # Status Metric Badges
                with ui.card().classes(
                    "theme-card border theme-border px-5 py-3 rounded-xl shadow flex-row items-center gap-5"
                ):
                    with ui.column().classes("gap-0"):
                        ui.label("ACTIVE / VALID").classes(
                            "text-[10px] font-bold text-[#86efac] tracking-wider uppercase"
                        )
                        ui.label(str(valid_count)).classes("text-xl font-bold text-[#86efac]")

                    with ui.column().classes("gap-0"):
                        ui.label("EXPIRING SOON (90 DAYS)").classes(
                            "text-[10px] font-bold text-[#fbbf24] tracking-wider uppercase"
                        )
                        ui.label(str(expiring_count)).classes("text-xl font-bold text-[#fbbf24]")

                    if expired_count > 0:
                        with ui.column().classes("gap-0"):
                            ui.label("OVERDUE / EXPIRED").classes(
                                "text-[10px] font-bold text-[#fda4af] tracking-wider uppercase"
                            )
                            ui.label(str(expired_count)).classes("text-xl font-bold text-[#fda4af]")

            # Add Certificate Button
            ui.button(
                "+ Add Certificate",
                icon="add_circle",
                on_click=self.open_create_compliance_dialog,
            ).classes(
                "bg-[#e5c07b] text-[#0e1015] font-bold text-xs px-4 py-2.5 rounded-xl shadow-md hover:bg-[#e5c07b]/90"
            )

        # Certificate Grid (Dedicated box for each certificate)
        with ui.grid(columns=3).classes("w-full gap-5"):
            for cert in formatted_certs:
                cid = cert["id"]
                status = cert["status"]

                if status == "VALID":
                    status_border = "border-emerald-500/30"
                    status_pill = "bg-emerald-950/40 text-emerald-300 border-emerald-500/40"
                    countdown_color = "text-[#86efac]"
                elif status == "EXPIRING_SOON":
                    status_border = "border-amber-500/50 shadow-[0_0_15px_rgba(251,191,36,0.15)]"
                    status_pill = "bg-amber-950/60 text-amber-300 border-amber-500/50 animate-pulse"
                    countdown_color = "text-[#fbbf24]"
                else:
                    status_border = "border-rose-500/50 shadow-[0_0_15px_rgba(244,63,94,0.15)]"
                    status_pill = "bg-rose-950/60 text-rose-300 border-rose-500/50 animate-pulse"
                    countdown_color = "text-[#fda4af]"

                with ui.card().classes(
                    f"theme-card border {status_border} p-5 rounded-xl shadow-md flex flex-col justify-between"
                ):
                    # Top Row: Title & Status Badge
                    with ui.row().classes("w-full justify-between items-start mb-2"):
                        with ui.column().classes("gap-0.5 flex-1 pr-2"):
                            ui.label(cert["title"]).classes("text-sm font-bold text-white tracking-wide")
                            ui.label(f"Provider: {cert['provider']}").classes("text-xs text-[#a8a29e]")

                        with ui.row().classes("items-center gap-1.5"):
                            if cert.get("epc_rating"):
                                ui.badge(f"Rating {cert['epc_rating']}").classes(
                                    "bg-emerald-950/60 text-emerald-300 border border-emerald-500/40 text-xs px-2 py-0.5 font-bold"
                                )
                            ui.badge(cert["status_label"]).classes(
                                f"border {status_pill} text-xs px-2.5 py-0.5 font-semibold"
                            )

                    # Dates & Countdown Block
                    with ui.card().classes("w-full theme-card-alt p-3 rounded-lg border theme-border my-2 gap-1.5"):
                        with ui.row().classes("w-full justify-between items-center text-xs"):
                            ui.label("Issue Date:").classes("text-[#a8a29e]")
                            ui.label(cert["issue_date"]).classes("font-semibold text-gray-200")
                        with ui.row().classes("w-full justify-between items-center text-xs"):
                            ui.label("Renewal Due:").classes("text-[#a8a29e]")
                            ui.label(cert["expiry_date"]).classes("font-bold text-white")

                        ui.separator().classes("my-1 opacity-20")

                        with ui.row().classes("w-full justify-between items-center"):
                            ui.label("Time Remaining:").classes("text-xs text-[#a8a29e]")
                            ui.label(cert["countdown_text"]).classes(f"text-xs font-bold {countdown_color}")

                    # Reference, Cost, and Document Indicator
                    with ui.row().classes("w-full justify-between items-center text-xs text-[#a8a29e] mb-2 px-1"):
                        ui.label(f"Ref: {cert['reference_number']}").classes("truncate max-w-[160px]")
                        ui.label(f"Cost: {cert['cost_formatted']}").classes("font-semibold text-gray-300")

                    # Footer: Action Buttons
                    with ui.row().classes("w-full justify-between items-center pt-2 border-t theme-border"):
                        if cert.get("notes"):
                            ui.label(cert["notes"]).classes("text-[11px] text-[#a8a29e] italic truncate max-w-[200px]")
                        else:
                            ui.label("").classes("text-xs")

                        ui.button(
                            "Edit Details",
                            icon="edit",
                            on_click=lambda cert_id=cid: self.open_edit_compliance_dialog(cert_id),
                        ).props("dense outline").classes(
                            "text-xs text-[#e5c07b] border-[#e5c07b]/40 hover:bg-[#e5c07b]/10 rounded px-2.5 py-1"
                        )

    # [spec: COMP-001]
    def _seed_default_compliance_certificates(self) -> None:
        """Seed initial standard statutory landlord certificates if register is empty."""
        from datetime import datetime, timedelta

        now = datetime.now()
        cp12_exp = (now + timedelta(days=240)).strftime("%d-%m-%Y")
        cp12_iss = (now - timedelta(days=125)).strftime("%d-%m-%Y")

        eicr_exp = (now + timedelta(days=780)).strftime("%d-%m-%Y")
        eicr_iss = (now - timedelta(days=400)).strftime("%d-%m-%Y")

        epc_exp = (now + timedelta(days=1825)).strftime("%d-%m-%Y")
        epc_iss = (now - timedelta(days=365)).strftime("%d-%m-%Y")

        ins_exp = (now + timedelta(days=45)).strftime("%d-%m-%Y")  # Expiring soon (< 90 days)
        ins_iss = (now - timedelta(days=320)).strftime("%d-%m-%Y")

        boiler_exp = (now + timedelta(days=210)).strftime("%d-%m-%Y")
        boiler_iss = (now - timedelta(days=155)).strftime("%d-%m-%Y")

        self.db.create_compliance_certificate(
            certificate_type="Gas Safety (CP12)",
            title="Gas Safety Certificate (CP12)",
            issue_date=cp12_iss,
            expiry_date=cp12_exp,
            provider="Gas Safe Registered Engineer",
            reference_number="CP12-902144",
            cost=Decimal("95.00"),
            notes="Annual landlord gas safety inspection completed. All flues and appliances operational.",
        )

        self.db.create_compliance_certificate(
            certificate_type="EICR (Electrical)",
            title="Electrical Installation Condition Report (EICR)",
            issue_date=eicr_iss,
            expiry_date=eicr_exp,
            provider="NICEIC Certified Electrician",
            reference_number="EICR-44810",
            cost=Decimal("220.00"),
            notes="5-year electrical installation condition report. Satisfactory condition.",
        )

        self.db.create_compliance_certificate(
            certificate_type="EPC (Energy Performance)",
            title="Energy Performance Certificate (EPC)",
            issue_date=epc_iss,
            expiry_date=epc_exp,
            provider="Domestic Energy Assessor",
            reference_number="EPC-88319-C",
            cost=Decimal("75.00"),
            epc_rating="C",
            notes="Valid for 10 years. Rating C (above legal minimum E).",
        )

        self.db.create_compliance_certificate(
            certificate_type="Landlord Insurance",
            title="Landlord Buildings & Contents Insurance",
            issue_date=ins_iss,
            expiry_date=ins_exp,
            provider="Direct Line for Business",
            reference_number="POL-77391-LL",
            cost=Decimal("280.00"),
            notes="Annual policy renewal. Covers property damage, loss of rent, and property owner liability.",
        )

        self.db.create_compliance_certificate(
            certificate_type="Annual Boiler Service",
            title="Annual Boiler Service & Inspection",
            issue_date=boiler_iss,
            expiry_date=boiler_exp,
            provider="British Gas HomeCare",
            reference_number="BG-SERV-3011",
            cost=Decimal("110.00"),
            notes="Annual heating service to maintain warranty. Heat exchanger cleaned and pressure tested.",
        )

    # [spec: UI-003]
    def refresh_all(self) -> None:
        """In-place refresh of all dashboard components without full page reloads."""
        if self.progress_container:
            self.progress_container.clear()
            with self.progress_container:
                self.render_loan_progress_section()

        if self.current_month_container:
            self.current_month_container.clear()
            with self.current_month_container:
                self.render_current_month_progress_section()

        if self.portfolio_summary_container:
            self.portfolio_summary_container.clear()
            with self.portfolio_summary_container:
                self.render_portfolio_summary_section()

        if self.kpi_container:
            self.kpi_container.clear()
            with self.kpi_container:
                self.render_kpi_cards()

        if self.chart_container:
            self.chart_container.clear()
            with self.chart_container:
                self.render_trend_charts()

        if self.statements_container:
            self.statements_container.clear()
            with self.statements_container:
                self.render_statements_table()

        if self.invoices_container:
            self.invoices_container.clear()
            with self.invoices_container:
                self.render_invoices_table()

        if self.issues_container:
            self.issues_container.clear()
            with self.issues_container:
                self.render_issues_board()

        if self.compliance_container:
            self.compliance_container.clear()
            with self.compliance_container:
                self.render_compliance_register()

        if self.mortgage_container:
            self.mortgage_container.clear()
            with self.mortgage_container:
                self.render_mortgage_analytics_tab()

    # [spec: MORT-002]
    def render_mortgage_analytics_tab(self) -> None:
        """Render dedicated Mortgage tab displaying Consent to Let tracking and multi-graph analytics."""
        progress = self.calculate_current_mortgage_progress()
        records = self.db.get_all_monthly_statements()
        ctl = calculate_consent_to_let_status(
            granted=self.config.mortgage.consent_to_let_granted,
            start_date=self.config.mortgage.consent_to_let_start_date,
            end_date=self.config.mortgage.consent_to_let_end_date,
            fee=self.config.mortgage.consent_to_let_fee,
            lender=self.config.mortgage.consent_to_let_lender,
        )

        # Compute timeline data (including projected amortization to £0)
        timeline_data = prepare_mortgage_timeline_series(
            records=records,
            initial_principal=self.config.mortgage.initial_principal,
            monthly_direct_debit=self.config.mortgage.monthly_direct_debit,
            interest_rate=self.config.mortgage.interest_rate,
        )

        # 1. Top Section: Terms & Consent to Let Status Header
        with ui.grid(columns=3).classes("w-full gap-4 mb-2"):
            # Card 1: Core Terms & Current Principal + Projected End Date
            with ui.card().classes(
                "theme-card border theme-border p-5 rounded-xl shadow-md flex flex-col justify-between"
            ):
                with ui.row().classes("justify-between items-center w-full"):
                    ui.label("MORTGAGE TERMS").classes("text-xs font-bold tracking-widest text-[#e5c07b] uppercase")
                    ui.badge(f"{self.config.mortgage.interest_rate}% Fixed").props("outline").classes(
                        "border-[#e5c07b]/40 text-[#e5c07b]"
                    )
                with ui.column().classes("gap-1 my-2"):
                    ui.label(f"£{progress.remaining_principal:,.2f}").classes("text-2xl font-bold text-white")
                    ui.label(
                        f"Initial: £{progress.initial_principal:,.2f} • Repaid: £{progress.repaid_principal:,.2f} ({progress.repaid_percentage}%)"
                    ).classes("text-xs text-[#a8a29e]")
                with ui.row().classes("justify-between items-center w-full text-xs"):
                    ui.label(f"Direct Debit: £{self.config.mortgage.monthly_direct_debit:,.2f}/mo").classes(
                        "font-semibold text-[#86efac]"
                    )
                    if timeline_data and timeline_data.get("projected_end_date"):
                        ui.label(f"Projected Payoff: {timeline_data['projected_end_date']}").classes(
                            "font-semibold text-[#e5c07b]"
                        )

            # Card 2: Fixed Rate Expiry Horizon
            with ui.card().classes(
                "theme-card border theme-border p-5 rounded-xl shadow-md flex flex-col justify-between"
            ):
                with ui.row().classes("justify-between items-center w-full"):
                    ui.label("FIXED DEAL PERIOD").classes("text-xs font-bold tracking-widest text-[#e5c07b] uppercase")
                    ui.icon("event", size="xs").classes("text-[#e5c07b]")
                with ui.column().classes("gap-1 my-2"):
                    ui.label(self.config.mortgage.fixed_deal_end_date).classes("text-2xl font-bold text-white")
                    fixed_days = (
                        progress.fixed_deal_days_remaining if progress.fixed_deal_days_remaining is not None else 0
                    )
                    countdown_label = format_countdown_years_months(
                        days_remaining=fixed_days,
                        end_date_str=self.config.mortgage.fixed_deal_end_date,
                    )
                    ui.label(countdown_label).classes("text-xs text-[#fbbf24] font-semibold")
                ui.label(f"Effective From: {self.config.mortgage.effective_from}").classes("text-xs text-[#a8a29e]")

            # Card 3: Consent to Let Tracking (AC-MORT-002.4)
            with ui.card().classes(
                "theme-card border theme-border p-5 rounded-xl shadow-md flex flex-col justify-between"
            ):
                with ui.row().classes("justify-between items-center w-full"):
                    ui.label("CONSENT TO LET (LENDER)").classes(
                        "text-xs font-bold tracking-widest text-[#e5c07b] uppercase"
                    )
                    status_badge_map = {
                        "ACTIVE": ("border-emerald-500/40 text-emerald-300 bg-emerald-950/40", "Active"),
                        "EXPIRING_SOON": ("border-amber-500/40 text-amber-300 bg-amber-950/40", "Expiring Soon"),
                        "EXPIRED": ("border-rose-500/40 text-rose-300 bg-rose-950/40", "Expired"),
                        "NOT_CONFIGURED": ("border-gray-500/40 text-gray-400 bg-gray-900/40", "Not Configured"),
                    }
                    cls, text = status_badge_map.get(ctl.status, ("border-gray-500/40 text-gray-400", ctl.status))
                    ui.badge(text).classes(f"text-xs px-2.5 py-0.5 border {cls}")

                with ui.column().classes("gap-1 my-2"):
                    if ctl.granted and ctl.end_date:
                        ui.label(f"Expires: {ctl.end_date}").classes("text-xl font-bold text-white")
                        ctl_rem_label = format_countdown_years_months(
                            days_remaining=ctl.days_remaining,
                            end_date_str=ctl.end_date,
                        )
                        ui.label(f"Start: {ctl.start_date or 'N/A'} • {ctl_rem_label}").classes(
                            "text-xs text-[#a8a29e]"
                        )
                    elif ctl.granted:
                        ui.label("Granted (Indefinite)").classes("text-xl font-bold text-white")
                        ui.label(f"Start: {ctl.start_date or 'N/A'}").classes("text-xs text-[#a8a29e]")
                    else:
                        ui.label("No Permission Set").classes("text-xl font-bold text-gray-400")
                        ui.label("Configure in config.toml").classes("text-xs text-[#a8a29e]")

                details_items = []
                if ctl.lender:
                    details_items.append(f"Lender: {ctl.lender}")
                if ctl.fee and ctl.fee > Decimal("0.00"):
                    details_items.append(f"Annual Fee: £{ctl.fee:,.2f}")
                if details_items:
                    ui.label(" • ".join(details_items)).classes("text-xs font-medium text-[#d1cbbe]")

        # 2. Interactive Charts (AC-MORT-002.1, AC-MORT-002.2, AC-MORT-002.3)
        if not records:
            with ui.card().classes("w-full theme-card border theme-border p-8 text-center rounded-xl my-4"):
                ui.icon("query_stats", size="lg").classes("text-gray-600 mb-2")
                ui.label("No rental statements ingested yet to plot amortization curves.").classes(
                    "text-gray-400 text-sm"
                )
            return

        timeline_chart_options = {
            "title": {
                "text": "MORTGAGE LOAN BALANCE AMORTIZATION TIMELINE",
                "subtext": "Historical outstanding mortgage balance declining from initial loan baseline",
                "left": "left",
                "top": "0",
                "textStyle": {"color": "#fdfbf7", "fontSize": 13, "fontWeight": 700},
                "subtextStyle": {"color": "#a8a29e", "fontSize": 11},
            },
            "tooltip": {
                "trigger": "axis",
                "backgroundColor": "rgba(20, 28, 42, 0.95)",
                "borderColor": "rgba(229, 192, 123, 0.35)",
                "textStyle": {"color": "#fdfbf7", "fontSize": 12},
                "valueFormatter": "(value) => value !== null && value !== undefined ? '£' + Number(value).toLocaleString('en-GB', {minimumFractionDigits: 2, maximumFractionDigits: 2}) : '—'",
            },
            "legend": {
                "data": [
                    "Outstanding Balance",
                    "Projected Amortization (to £0)",
                    "Initial Principal Benchmark",
                    "Cumulative Principal Repaid",
                ],
                "textStyle": {"color": "#d1cbbe", "fontSize": 11},
                "bottom": "0",
                "left": "center",
            },
            "grid": {"left": "3%", "right": "4%", "top": "18%", "bottom": "18%", "containLabel": True},
            "xAxis": {
                "type": "category",
                "data": timeline_data["categories"],
                "axisLine": {"lineStyle": {"color": "rgba(229, 192, 123, 0.3)"}},
                "axisLabel": {"color": "#d1cbbe", "fontSize": 11, "rotate": 25},
            },
            "yAxis": {
                "type": "value",
                "axisLine": {"lineStyle": {"color": "rgba(229, 192, 123, 0.3)"}},
                "axisLabel": {"formatter": "£{value}", "color": "#d1cbbe", "fontSize": 11},
                "splitLine": {"lineStyle": {"color": "rgba(229, 192, 123, 0.12)", "type": "dashed"}},
            },
            "series": [
                {
                    "name": "Outstanding Balance",
                    "type": "line",
                    "smooth": True,
                    "symbol": "circle",
                    "symbolSize": 7,
                    "lineStyle": {
                        "color": "#e5c07b",
                        "width": 3,
                        "shadowColor": "rgba(229, 192, 123, 0.4)",
                        "shadowBlur": 8,
                    },
                    "itemStyle": {"color": "#e5c07b"},
                    "areaStyle": {
                        "color": {
                            "type": "linear",
                            "x": 0,
                            "y": 0,
                            "x2": 0,
                            "y2": 1,
                            "colorStops": [
                                {"offset": 0, "color": "rgba(229, 192, 123, 0.25)"},
                                {"offset": 1, "color": "rgba(229, 192, 123, 0.0)"},
                            ],
                        }
                    },
                    "data": timeline_data["balance"],
                },
                {
                    "name": "Projected Amortization (to £0)",
                    "type": "line",
                    "smooth": True,
                    "symbol": "circle",
                    "symbolSize": 4,
                    "lineStyle": {
                        "color": "#38bdf8",
                        "width": 2.5,
                        "type": "dashed",
                        "shadowColor": "rgba(56, 189, 248, 0.3)",
                        "shadowBlur": 6,
                    },
                    "itemStyle": {"color": "#38bdf8"},
                    "data": timeline_data.get("projected_balance", []),
                },
                {
                    "name": "Initial Principal Benchmark",
                    "type": "line",
                    "lineStyle": {"color": "#64748b", "width": 2, "type": "dashed"},
                    "symbol": "none",
                    "data": timeline_data["initial_benchmark"],
                },
                {
                    "name": "Cumulative Principal Repaid",
                    "type": "bar",
                    "barWidth": "25%",
                    "itemStyle": {
                        "color": "rgba(134, 239, 172, 0.8)",
                        "borderRadius": [4, 4, 0, 0],
                    },
                    "data": timeline_data["principal_repaid"],
                },
            ],
        }

        # Chart 2: Stacked Bar - Principal vs Interest vs Landlord Out-of-Pocket Cash (AC-MORT-002.2)
        stacked_data = prepare_mortgage_stacked_repayment_series(
            records=records,
            interest_rate=self.config.mortgage.interest_rate,
        )

        stacked_chart_options = {
            "title": {
                "text": "MONTHLY MORTGAGE PAYMENT COMPOSITION & CASH SHORTFALL",
                "subtext": "Principal debt reduction vs Interest expense vs Landlord cash contribution",
                "left": "left",
                "top": "0",
                "textStyle": {"color": "#fdfbf7", "fontSize": 13, "fontWeight": 700},
                "subtextStyle": {"color": "#a8a29e", "fontSize": 11},
            },
            "tooltip": {
                "trigger": "axis",
                "axisPointer": {"type": "shadow"},
                "backgroundColor": "rgba(20, 28, 42, 0.95)",
                "borderColor": "rgba(229, 192, 123, 0.35)",
                "textStyle": {"color": "#fdfbf7", "fontSize": 12},
                "valueFormatter": "(value) => '£' + Number(value).toLocaleString('en-GB', {minimumFractionDigits: 2, maximumFractionDigits: 2})",
            },
            "legend": {
                "data": ["Principal Repayment", "Interest Charge", "Out-of-Pocket Cash Paid"],
                "textStyle": {"color": "#d1cbbe", "fontSize": 11},
                "bottom": "0",
                "left": "center",
            },
            "grid": {"left": "3%", "right": "4%", "top": "20%", "bottom": "20%", "containLabel": True},
            "xAxis": {
                "type": "category",
                "data": stacked_data["categories"],
                "axisLine": {"lineStyle": {"color": "rgba(229, 192, 123, 0.3)"}},
                "axisLabel": {"color": "#d1cbbe", "fontSize": 11, "rotate": 25},
            },
            "yAxis": {
                "type": "value",
                "axisLine": {"lineStyle": {"color": "rgba(229, 192, 123, 0.3)"}},
                "axisLabel": {"formatter": "£{value}", "color": "#d1cbbe", "fontSize": 11},
                "splitLine": {"lineStyle": {"color": "rgba(229, 192, 123, 0.12)", "type": "dashed"}},
            },
            "series": [
                {
                    "name": "Principal Repayment",
                    "type": "bar",
                    "stack": "repayment",
                    "itemStyle": {"color": "#86efac", "borderRadius": [0, 0, 0, 0]},
                    "data": stacked_data["principal"],
                },
                {
                    "name": "Interest Charge",
                    "type": "bar",
                    "stack": "repayment",
                    "itemStyle": {"color": "#fbbf24", "borderRadius": [4, 4, 0, 0]},
                    "data": stacked_data["interest"],
                },
                {
                    "name": "Out-of-Pocket Cash Paid",
                    "type": "line",
                    "lineStyle": {"color": "#f43f5e", "width": 2.5},
                    "itemStyle": {"color": "#f43f5e"},
                    "symbol": "circle",
                    "symbolSize": 6,
                    "data": stacked_data["out_of_pocket"],
                },
            ],
        }

        # Chart 3: Cumulative Rent vs Total Financing Costs & Expenses (AC-MORT-002.3)
        cum_data = prepare_cumulative_comparison_series(records=records)

        cum_chart_options = {
            "title": {
                "text": "CUMULATIVE PORTFOLIO FINANCING & EARNINGS COMPARISON",
                "subtext": "Cumulative gross rent collected vs cumulative mortgage payments and expenses",
                "left": "left",
                "top": "0",
                "textStyle": {"color": "#fdfbf7", "fontSize": 13, "fontWeight": 700},
                "subtextStyle": {"color": "#a8a29e", "fontSize": 11},
            },
            "tooltip": {
                "trigger": "axis",
                "backgroundColor": "rgba(20, 28, 42, 0.95)",
                "borderColor": "rgba(229, 192, 123, 0.35)",
                "textStyle": {"color": "#fdfbf7", "fontSize": 12},
                "valueFormatter": "(value) => '£' + Number(value).toLocaleString('en-GB', {minimumFractionDigits: 2, maximumFractionDigits: 2})",
            },
            "legend": {
                "data": [
                    "Cumulative Gross Rent",
                    "Cumulative Mortgage Payments",
                    "Cumulative Total Costs (Mortgage + Expenses)",
                ],
                "textStyle": {"color": "#d1cbbe", "fontSize": 11},
                "bottom": "0",
                "left": "center",
            },
            "grid": {"left": "3%", "right": "4%", "top": "20%", "bottom": "20%", "containLabel": True},
            "xAxis": {
                "type": "category",
                "data": cum_data["categories"],
                "axisLine": {"lineStyle": {"color": "rgba(229, 192, 123, 0.3)"}},
                "axisLabel": {"color": "#d1cbbe", "fontSize": 11, "rotate": 25},
            },
            "yAxis": {
                "type": "value",
                "axisLine": {"lineStyle": {"color": "rgba(229, 192, 123, 0.3)"}},
                "axisLabel": {"formatter": "£{value}", "color": "#d1cbbe", "fontSize": 11},
                "splitLine": {"lineStyle": {"color": "rgba(229, 192, 123, 0.12)", "type": "dashed"}},
            },
            "series": [
                {
                    "name": "Cumulative Gross Rent",
                    "type": "line",
                    "smooth": True,
                    "symbol": "circle",
                    "symbolSize": 6,
                    "lineStyle": {"color": "#e5c07b", "width": 3},
                    "itemStyle": {"color": "#e5c07b"},
                    "data": cum_data["cumulative_rent"],
                },
                {
                    "name": "Cumulative Mortgage Payments",
                    "type": "line",
                    "smooth": True,
                    "symbol": "circle",
                    "symbolSize": 6,
                    "lineStyle": {"color": "#38bdf8", "width": 2.5},
                    "itemStyle": {"color": "#38bdf8"},
                    "data": cum_data["cumulative_mortgage"],
                },
                {
                    "name": "Cumulative Total Costs (Mortgage + Expenses)",
                    "type": "line",
                    "smooth": True,
                    "symbol": "circle",
                    "symbolSize": 6,
                    "lineStyle": {"color": "#f43f5e", "width": 2.5, "type": "dashed"},
                    "itemStyle": {"color": "#f43f5e"},
                    "data": cum_data["cumulative_total_costs"],
                },
            ],
        }

        # Grid containing the 3 charts
        with ui.column().classes("w-full gap-5 mt-2"):
            with ui.card().classes("w-full theme-card border theme-border p-5 rounded-xl shadow-lg"):
                ui.echart(timeline_chart_options).classes("w-full h-[360px]")

            with ui.grid(columns=2).classes("w-full gap-5"):
                with ui.card().classes("w-full theme-card border theme-border p-5 rounded-xl shadow-lg"):
                    ui.echart(stacked_chart_options).classes("w-full h-[360px]")
                with ui.card().classes("w-full theme-card border theme-border p-5 rounded-xl shadow-lg"):
                    ui.echart(cum_chart_options).classes("w-full h-[360px]")

    # [spec: UI-003]
    def build_page(self) -> None:
        """Construct the single-property executive layout with Key Dashboard, Rent Management, Mortgage Analytics, and Issues & Maintenance tabs."""
        # Inject primary luxury colors to prevent Quasar blue defaults
        ui.colors(primary="#e5c07b", secondary="#181d2a", accent="#86efac", dark="#121622")

        # Inject active theme stylesheet into document head
        css = get_theme_css(self.current_theme)
        ui.add_head_html(f"<style id='theme-styles'>{css}</style>")
        ui.add_css(css)
        self.theme_style_tag = ui.html(f"<style id='theme-styles-body'>{css}</style>")

        self.render_top_bar()

        with ui.column().classes("w-full max-w-7xl mx-auto px-6 py-5 gap-3"):
            # Primary Navigation Tabs (Key Dashboard -> Rent Management -> Mortgage Analytics -> Issues & Maintenance -> Compliance)
            with ui.tabs().classes("w-full luxury-tabs").props("align=left no-caps") as main_tabs:
                self.main_tabs = main_tabs
                dashboard_tab = ui.tab("Key Dashboard")
                self.rent_tab = ui.tab("Rent Management")
                mortgage_tab = ui.tab("Mortgage Analytics")
                issues_tab = ui.tab("Issues & Maintenance")
                compliance_tab = ui.tab("Compliance")

            with ui.tab_panels(main_tabs, value=dashboard_tab).classes("w-full bg-transparent p-0"):
                # TAB 1: KEY DASHBOARD (Loan progress + Current Month box + Portfolio Summary box + 4 KPI cards)
                with ui.tab_panel(dashboard_tab).classes("gap-5 flex flex-col p-0"):
                    # Loan Payoff Section (AC-UI-003.1)
                    self.progress_container = ui.column().classes("w-full")
                    with self.progress_container:
                        self.render_loan_progress_section()

                    # Current Month Financial Details Box (AC-UI-003.4)
                    self.current_month_container = ui.column().classes("w-full")
                    with self.current_month_container:
                        self.render_current_month_progress_section()

                    # Portfolio Cumulative Summary Box (AC-UI-003.5)
                    self.portfolio_summary_container = ui.column().classes("w-full")
                    with self.portfolio_summary_container:
                        self.render_portfolio_summary_section()

                # TAB 2: RENT MANAGEMENT (Trend graph + Statements & Invoices Ledgers)
                with ui.tab_panel(self.rent_tab).classes("gap-5 flex flex-col p-0"):
                    # Interactive Trend Charts (AC-UI-001.4)
                    self.chart_container = ui.column().classes("w-full")
                    with self.chart_container:
                        self.render_trend_charts()

                    # Sub-tabs for Ledgers: Statements & Contractor Invoices
                    with ui.tabs().classes("w-full luxury-subtabs mt-2").props("align=left no-caps") as ledger_tabs:
                        self.ledger_tabs = ledger_tabs
                        self.stmt_tab = ui.tab("Monthly Statements")
                        self.inv_tab = ui.tab("Contractor Invoices")

                    with ui.tab_panels(ledger_tabs, value=self.stmt_tab).classes("w-full bg-transparent p-0"):
                        with ui.tab_panel(self.stmt_tab).classes("p-0"):
                            self.statements_container = ui.column().classes("w-full")
                            with self.statements_container:
                                self.render_statements_table()

                        with ui.tab_panel(self.inv_tab).classes("p-0"):
                            self.invoices_container = ui.column().classes("w-full")
                            with self.invoices_container:
                                self.render_invoices_table()

                # TAB 3: MORTGAGE ANALYTICS (AC-MORT-002.1 - AC-MORT-002.4)
                with ui.tab_panel(mortgage_tab).classes("gap-5 flex flex-col p-0"):
                    self.mortgage_container = ui.column().classes("w-full")
                    with self.mortgage_container:
                        self.render_mortgage_analytics_tab()

                # TAB 4: ISSUES & MAINTENANCE (AC-ISSUE-001.1, AC-ISSUE-002.1-5)
                with ui.tab_panel(issues_tab).classes("gap-5 flex flex-col p-0"):
                    self.issues_container = ui.column().classes("w-full")
                    with self.issues_container:
                        self.render_issues_board()

                # TAB 5: COMPLIANCE & CERTIFICATES (AC-COMP-001.1 - AC-COMP-001.5)
                with ui.tab_panel(compliance_tab).classes("gap-5 flex flex-col p-0"):
                    self.compliance_container = ui.column().classes("w-full")
                    with self.compliance_container:
                        self.render_compliance_register()


# [spec: UI-003]
def create_app(config_path: Path | str | None = None) -> ExecutiveDashboardApp:
    """Instantiate the executive dashboard app instance."""
    config = load_config(config_path)
    db = Database()
    app_instance = ExecutiveDashboardApp(db=db, config=config)

    @ui.page("/")
    def main_page():
        app_instance.build_page()

    return app_instance

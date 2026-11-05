"""Executive UI package."""

from src.ui.app import ExecutiveDashboardApp, create_app
from src.ui.components import (
    build_mortgage_progress_bar_props,
    format_kpi_card_data,
    prepare_chart_series,
    prepare_invoices_table_rows,
    prepare_statements_table_rows,
)
from src.ui.theme import DEFAULT_THEME, THEMES, get_theme_css

__all__ = [
    "DEFAULT_THEME",
    "THEMES",
    "ExecutiveDashboardApp",
    "build_mortgage_progress_bar_props",
    "create_app",
    "format_kpi_card_data",
    "get_theme_css",
    "prepare_chart_series",
    "prepare_invoices_table_rows",
    "prepare_statements_table_rows",
]

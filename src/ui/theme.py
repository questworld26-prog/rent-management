"""Theme definitions and CSS design tokens for the Executive Rent Management Dashboard.
Bound to specification UI-003 and ADR-004.
"""

from dataclasses import dataclass


# [spec: UI-003]
@dataclass(frozen=True)
class ThemeTokens:
    name: str
    bg_main: str
    bg_card: str
    bg_card_alt: str
    text_primary: str
    text_secondary: str
    text_muted: str
    accent_emerald: str
    accent_cyan: str
    accent_amber: str
    accent_coral: str
    border_color: str
    glow_color: str


# [spec: UI-003]
QUIET_LUXURY_THEME = ThemeTokens(
    name="Quiet Luxury",
    bg_main="#0e1015",
    bg_card="#141720",
    bg_card_alt="#1a1e29",
    text_primary="#fdfbf7",
    text_secondary="#d1cbbe",
    text_muted="#8c887f",
    accent_emerald="#86efac",
    accent_cyan="#e5c07b",
    accent_amber="#d97706",
    accent_coral="#9f1239",
    border_color="rgba(229, 192, 123, 0.22)",
    glow_color="rgba(229, 192, 123, 0.2)",
)

THEMES: dict[str, ThemeTokens] = {
    "Quiet Luxury": QUIET_LUXURY_THEME,
    "Nordic Aurora": QUIET_LUXURY_THEME,
    "Vibrant Multi-Color": QUIET_LUXURY_THEME,
    "Midnight Sapphire": QUIET_LUXURY_THEME,
    "Titanium & Warm Gold": QUIET_LUXURY_THEME,
}

DEFAULT_THEME = "Quiet Luxury"


# [spec: UI-003]
def get_theme_css(theme_name: str = DEFAULT_THEME) -> str:
    """Generate CSS variables string for the selected theme."""
    tokens = THEMES.get(theme_name, QUIET_LUXURY_THEME)
    return f"""
    :root {{
        --bg-main: {tokens.bg_main};
        --bg-card: {tokens.bg_card};
        --bg-card-alt: {tokens.bg_card_alt};
        --text-primary: {tokens.text_primary};
        --text-secondary: {tokens.text_secondary};
        --text-muted: {tokens.text_muted};
        --accent-emerald: {tokens.accent_emerald};
        --accent-cyan: {tokens.accent_cyan};
        --accent-amber: {tokens.accent_amber};
        --accent-coral: {tokens.accent_coral};
        --border-color: {tokens.border_color};
        --glow-color: {tokens.glow_color};
    }}
    body {{
        background-color: #162030 !important;
        color: var(--text-primary) !important;
        font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        font-variant-numeric: tabular-nums;
        min-height: 100vh;
        position: relative;
    }}
    body::before {{
        content: "";
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        width: 100vw;
        height: 100vh;
        pointer-events: none;
        z-index: 0;
        background-image:
            linear-gradient(to right, rgba(229, 192, 123, 0.095) 1px, transparent 1px),
            linear-gradient(to bottom, rgba(229, 192, 123, 0.095) 1px, transparent 1px),
            radial-gradient(ellipse at 50% 10%, rgba(68, 92, 130, 0.9) 0%, rgba(32, 45, 68, 0.8) 45%, rgba(20, 28, 42, 0.96) 100%),
            linear-gradient(180deg, #1c273a 0%, #141c2a 100%);
        background-size: 38px 38px, 38px 38px, 100% 100%, 100% 100%;
        background-repeat: repeat, repeat, no-repeat, no-repeat;
    }}
    #q-app, .q-layout, .q-page-container {{
        background: transparent !important;
        background-color: transparent !important;
        position: relative;
        z-index: 1;
    }}
    .executive-title {{
        font-family: 'Cinzel', 'Playfair Display', Georgia, serif !important;
        letter-spacing: 0.08em !important;
    }}
    header.q-header, .q-header, .theme-header, .q-header.bg-primary {{
        background-color: rgba(22, 30, 44, 0.96) !important;
        background: rgba(22, 30, 44, 0.96) !important;
        backdrop-filter: blur(12px) !important;
        color: #fdfbf7 !important;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4) !important;
        border-bottom: 1px solid rgba(229, 192, 123, 0.35) !important;
    }}
    .q-table__container, .q-table {{
        background: linear-gradient(180deg, #1d273a 0%, #151d2c 100%) !important;
        background-color: #172030 !important;
        color: var(--text-primary) !important;
        border: 1px solid rgba(229, 192, 123, 0.42) !important;
        border-radius: 12px !important;
    }}
    .q-table th {{
        color: var(--text-secondary) !important;
        font-weight: 600;
        font-size: 0.75rem;
        letter-spacing: 0.05em;
        text-transform: uppercase;
        border-bottom: 1px solid rgba(229, 192, 123, 0.35) !important;
        background-color: #25334c !important;
    }}
    .q-table td {{
        border-bottom: 1px solid rgba(229, 192, 123, 0.15) !important;
        font-size: 0.8125rem;
    }}
    .q-table tbody tr {{
        cursor: pointer;
        transition: background-color 0.2s ease;
    }}
    .q-table tbody tr:hover {{
        background-color: #2b3a56 !important;
    }}
    .theme-card {{
        background: linear-gradient(180deg, #1d273a 0%, #151d2c 100%) !important;
        background-color: #172030 !important;
        border: 1px solid rgba(229, 192, 123, 0.45) !important;
        color: var(--text-primary) !important;
        box-shadow: 0 10px 32px -4px rgba(0, 0, 0, 0.5), 0 0 1px 1px rgba(229, 192, 123, 0.25) !important;
    }}
    .theme-card-alt {{
        background: linear-gradient(180deg, #25334c 0%, #1b2639 100%) !important;
        background-color: #202c42 !important;
        border: 1px solid rgba(229, 192, 123, 0.4) !important;
        box-shadow: 0 4px 18px rgba(0, 0, 0, 0.35) !important;
    }}
    .theme-border {{
        border-color: var(--border-color) !important;
    }}
    .theme-glow {{
        box-shadow: 0 0 15px var(--glow-color) !important;
    }}
    /* Luxury folder-tab navigation matching Image 3 and 4 */
    .luxury-tabs {{
        border-bottom: 1px solid rgba(229, 192, 123, 0.35) !important;
        background: transparent !important;
        min-height: 42px !important;
        position: relative !important;
        z-index: 5 !important;
    }}
    .luxury-tabs .q-tabs__content {{
        justify-content: flex-start !important;
        gap: 8px !important;
        padding-left: 0px !important;
    }}
    .luxury-tabs .q-tab {{
        border-radius: 8px 8px 0 0 !important;
        padding: 8px 24px !important;
        min-height: 40px !important;
        font-family: 'Plus Jakarta Sans', sans-serif !important;
        font-size: 0.875rem !important;
        font-weight: 600 !important;
        letter-spacing: 0.02em !important;
        text-transform: none !important;
        color: #8c887f !important;
        background: rgba(22, 28, 40, 0.85) !important;
        border: 1px solid rgba(229, 192, 123, 0.25) !important;
        border-bottom: none !important;
        margin-bottom: -1px !important;
        transition: all 0.2s ease !important;
    }}
    .luxury-tabs .q-tab:hover {{
        color: #e5c07b !important;
        background: rgba(229, 192, 123, 0.15) !important;
        border-color: rgba(229, 192, 123, 0.4) !important;
    }}
    .luxury-tabs .q-tab.q-tab--active,
    .luxury-tabs .q-tab--active {{
        background: linear-gradient(135deg, #e5c07b 0%, #d4af37 100%) !important;
        color: #0e1015 !important;
        font-weight: 700 !important;
        border: 1px solid #e5c07b !important;
        border-bottom: 1px solid #e5c07b !important;
        box-shadow: 0 -2px 10px rgba(229, 192, 123, 0.25) !important;
    }}
    .luxury-tabs .q-tab--active .q-tab__label,
    .luxury-tabs .q-tab.q-tab--active .q-tab__label {{
        color: #0e1015 !important;
        font-weight: 700 !important;
    }}
    .luxury-tabs .q-tab:not(.q-tab--active) .q-tab__label {{
        color: #8c887f !important;
    }}
    .luxury-tabs .q-tab:not(.q-tab--active):hover .q-tab__label {{
        color: #e5c07b !important;
    }}
    .luxury-tabs .q-tab__indicator,
    .luxury-tabs > .q-tab__indicator {{
        display: none !important;
        opacity: 0 !important;
        height: 0 !important;
        visibility: hidden !important;
    }}
    .luxury-subtabs {{
        border-bottom: 1px solid rgba(229, 192, 123, 0.35) !important;
        background: transparent !important;
        min-height: 38px !important;
        position: relative !important;
        z-index: 5 !important;
    }}
    .luxury-subtabs .q-tabs__content {{
        justify-content: flex-start !important;
        gap: 6px !important;
        padding-left: 0px !important;
    }}
    .luxury-subtabs .q-tab {{
        border-radius: 8px 8px 0 0 !important;
        padding: 6px 20px !important;
        min-height: 36px !important;
        font-family: 'Plus Jakarta Sans', sans-serif !important;
        font-size: 0.8125rem !important;
        font-weight: 600 !important;
        letter-spacing: 0.02em !important;
        text-transform: none !important;
        color: #8c887f !important;
        background: transparent !important;
        border: 1px solid transparent !important;
        border-bottom: none !important;
        margin-bottom: -1px !important;
        transition: all 0.2s ease !important;
    }}
    .luxury-subtabs .q-tab:hover {{
        color: #d1cbbe !important;
        background: rgba(229, 192, 123, 0.08) !important;
    }}
    .luxury-subtabs .q-tab.q-tab--active,
    .luxury-subtabs .q-tab--active {{
        background: #1c2538 !important;
        border-top: 1px solid rgba(229, 192, 123, 0.45) !important;
        border-left: 1px solid rgba(229, 192, 123, 0.45) !important;
        border-right: 1px solid rgba(229, 192, 123, 0.45) !important;
        border-bottom: 1px solid #1c2538 !important;
        color: #fdfbf7 !important;
        font-weight: 700 !important;
        box-shadow: 0 -2px 8px rgba(0, 0, 0, 0.3) !important;
    }}
    .luxury-subtabs .q-tab--active .q-tab__label,
    .luxury-subtabs .q-tab.q-tab--active .q-tab__label {{
        color: #fdfbf7 !important;
        font-weight: 700 !important;
    }}
    .luxury-subtabs .q-tab:not(.q-tab--active) .q-tab__label {{
        color: #8c887f !important;
    }}
    .luxury-subtabs .q-tab__indicator,
    .luxury-subtabs > .q-tab__indicator {{
        display: none !important;
        opacity: 0 !important;
        height: 0 !important;
        visibility: hidden !important;
    }}
    .gold-progress .q-linear-progress__model {{
        background: linear-gradient(90deg, #d4af37, #e5c07b) !important;
    }}
    .gold-progress .q-linear-progress__track {{
        background: #23201a !important;
    }}
    .q-dialog .q-card {{
        background-color: var(--bg-card) !important;
        border: 1px solid var(--border-color) !important;
        color: var(--text-primary) !important;
        box-shadow: 0 10px 40px rgba(0, 0, 0, 0.7) !important;
    }}
    .q-expansion-item {{
        background-color: var(--bg-card) !important;
        border-color: var(--border-color) !important;
    }}
    /* Quiet Luxury custom scrollbars */
    ::-webkit-scrollbar {{
        width: 6px;
        height: 6px;
    }}
    ::-webkit-scrollbar-track {{
        background: #0e1015;
    }}
    ::-webkit-scrollbar-thumb {{
        background: rgba(229, 192, 123, 0.25);
        border-radius: 4px;
    }}
    ::-webkit-scrollbar-thumb:hover {{
        background: rgba(229, 192, 123, 0.5);
    }}
    """

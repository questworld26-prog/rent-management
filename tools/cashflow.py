"""CLI tool for calculating cashflow, mortgage excess, and progress bar metrics."""

import argparse
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from src.config import load_config
from src.domain.cashflow import calculate_monthly_cashflow
from src.domain.models import MortgageTerms, RentalStatement
from src.domain.mortgage import calculate_mortgage_progress
from src.ingestion.extractor import OllamaExtractor, OllamaServiceUnreachableError
from src.ingestion.pdf_reader import extract_text_from_pdf
from src.storage.database import Database


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="cashflow",
        description="Calculate monthly rental cashflow, landlord out-of-pocket excess, and mortgage payoff progress.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config.toml"),
        help="Path to project config file (default: config.toml)",
    )
    parser.add_argument(
        "--statement",
        type=Path,
        help="Optional path to rental statement PDF (e.g. 'Resources/2026 10 Statement.pdf')",
    )
    parser.add_argument(
        "--net-rent",
        type=Decimal,
        help="Direct net rent payout received from letting agency (if statement PDF is not provided)",
    )
    parser.add_argument(
        "--statement-date",
        help="Statement date for manual entry in DD-MM-YYYY format (default: today's date)",
    )
    parser.add_argument(
        "--mortgage-debit",
        type=Decimal,
        help="Optional override for monthly mortgage direct debit (default: from config.toml)",
    )
    parser.add_argument(
        "--balance",
        type=Decimal,
        help="Current or month-end remaining mortgage principal (default: latest from DB or initial_principal)",
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="Persist statement and mortgage record to local SQLite database",
    )
    parser.add_argument(
        "--model",
        help="Local Ollama model override (default: from config.toml)",
    )

    args = parser.parse_args()

    # [spec: CONFIG-001]
    try:
        config = load_config(args.config)
    except Exception as exc:
        print(f"❌ Configuration error: {exc}", file=sys.stderr)
        return 1

    # Resolve parameters from config with optional CLI overrides
    mortgage_debit = args.mortgage_debit if args.mortgage_debit is not None else config.mortgage.monthly_direct_debit
    model_name = args.model or config.ollama.model

    db = Database()

    # Resolve remaining principal balance: CLI arg > DB latest > config initial_principal
    if args.balance is not None:
        remaining_balance = args.balance
    else:
        latest_db_balance = db.get_latest_mortgage_balance()
        remaining_balance = latest_db_balance if latest_db_balance is not None else config.mortgage.initial_principal

    # Build mortgage terms (MORT-001)
    mortgage = MortgageTerms(
        monthly_direct_debit=mortgage_debit,
        interest_rate=config.mortgage.interest_rate,
        initial_principal=config.mortgage.initial_principal,
        remaining_principal=remaining_balance,
        fixed_deal_end_date=config.mortgage.fixed_deal_end_date,
        effective_from=config.mortgage.effective_from,
    )

    statement: RentalStatement | None = None

    if args.statement:
        if not args.statement.exists():
            print(f"❌ Error: Statement file not found: {args.statement}", file=sys.stderr)
            return 1
        print(f"\n📄 Parsing statement PDF: {args.statement.name} via local Ollama ({model_name})...")
        raw_text = extract_text_from_pdf(args.statement)
        extractor = OllamaExtractor(base_url=config.ollama.base_url, model=model_name)
        try:
            statement = extractor.parse_rental_statement(raw_text)
        except OllamaServiceUnreachableError as exc:
            print(f"\n❌ {exc}", file=sys.stderr)
            return 1
        print(f"   Extracted Net Landlord Payout: £{statement.net_payout:,.2f}")
    elif args.net_rent is not None:
        today_str = datetime.now().strftime("%d-%m-%Y")
        statement_date = args.statement_date or today_str
        statement = RentalStatement(
            statement_date=statement_date,
            reference="MANUAL",
            statement_number="1",
            gross_income=args.net_rent,
            expenditures=[],
            net_payout=args.net_rent,
        )

    # Save to database if requested
    if args.save and statement:
        record_id = db.save_monthly_statement(
            statement=statement,
            mortgage_debit=mortgage_debit,
            outstanding_balance=remaining_balance,
        )
        print(f"💾 Persisted monthly statement to local database (record #{record_id})")

    # Calculate Cashflow (CASH-001)
    cashflow = calculate_monthly_cashflow(statement=statement, mortgage=mortgage)

    # Calculate Mortgage Progress (MORT-001)
    progress = calculate_mortgage_progress(mortgage)

    # Render Terminal Dashboard
    print("\n" + "=" * 60)
    print(" 📊 RENTAL CASHFLOW & MORTGAGE DASHBOARD METRICS")
    print("=" * 60)

    # Glowing Progress Bar Simulation (Loan Payoff)
    bar_width = 30
    repaid_chars = (
        int((progress.repaid_percentage / Decimal("100.00")) * bar_width) if progress.initial_principal > 0 else 0
    )
    loan_chars = bar_width - repaid_chars
    bar_display = "█" * repaid_chars + "░" * loan_chars

    print("\n[MORTGAGE PROGRESS BAR (DD-MM-YYYY)]")
    print(f"  [{bar_display}]")
    print(f"  • Principal Repaid: {progress.repaid_percentage}% (£{progress.repaid_principal:,.2f})")
    print(f"  • Remaining Loan:   {progress.remaining_loan_percentage}% (£{progress.remaining_principal:,.2f})")
    print(f"  • Deal Baseline:    £{progress.initial_principal:,.2f} (Effective: {mortgage.effective_from})")
    if progress.fixed_deal_days_remaining is not None:
        print(
            f"  • Fixed Deal End:   {mortgage.fixed_deal_end_date} ({progress.fixed_deal_days_remaining} days remaining)"
        )

    print("\n[MONTHLY CASHFLOW BREAKDOWN]")
    print(f"  • Gross Rent:              £{cashflow.gross_income:,.2f}")
    print(f"  • Total Deductions:        £{cashflow.total_deductions:,.2f}")
    print(f"  • Net Rent Received:       £{cashflow.net_rent_received:,.2f}")
    print(f"  • Mortgage Direct Debit:   £{cashflow.mortgage_direct_debit:,.2f}")
    print("-" * 60)

    if cashflow.out_of_pocket_excess > Decimal("0.00"):
        print(f"  ⚠️ OUT-OF-POCKET SHORTFALL: £{cashflow.out_of_pocket_excess:,.2f} (Paid from your pocket)")
    else:
        print(f"  ✅ SURPLUS CASHFLOW:        £{cashflow.surplus_cashflow:,.2f} (Net profit retained)")

    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())

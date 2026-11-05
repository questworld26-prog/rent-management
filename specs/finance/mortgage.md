# Mortgage Terms & Multi-Graph Visualization Specification

## MORT-001: Mortgage Terms Configuration & Progress Bar

The system shall maintain configurable mortgage parameters and track monthly loan balance entries to calculate and display principal repayment progress without tracking or calculating property equity.

Acceptance Criteria:
- AC-MORT-001.1: The system shall calculate and display the percentage and pound amount of mortgage principal paid off relative to initial principal balance at deal effective date.
- AC-MORT-001.2: The system shall render a mortgage progress bar displaying mortgage loan payoff percentage, remaining loan balance, and days remaining on the fixed deal.
- AC-MORT-001.3: Where mortgage terms change over time, the system shall record an effective start date and initial principal so historical calculations prior to that date remain unmodified.
- AC-MORT-001.4: When monthly statement records are saved to the database, the system shall record the outstanding mortgage balance for that month, and use the latest recorded balance to calculate current loan progress.

## MORT-002: Multi-Graph Mortgage Analytics

The system shall provide a dedicated Mortgage tab displaying comprehensive interactive charts tracking loan amortization and payment history.

Acceptance Criteria:
- AC-MORT-002.1: The system shall render an interactive timeline chart showing declining mortgage loan balance over time against initial balance.
- AC-MORT-002.2: The system shall render a monthly stacked bar chart showing principal repayment vs interest charge vs landlord out-of-pocket cash paid.
- AC-MORT-002.3: The system shall render a cumulative comparison chart tracking cumulative gross rent collected vs cumulative mortgage payments and expenses.
- AC-MORT-002.4: Where Consent to Let is granted by the lender, the system shall track its start date, expiry date, days remaining, fee, and active compliance status.


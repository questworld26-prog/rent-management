# Statement & Invoice Processing and Executive UI Specification

## UI-001: Monthly Statements Ledger & Trend Graphs

The system shall display monthly statement history in an executive table and render trend charts for financial performance across months.

Acceptance Criteria:
- AC-UI-001.1: The dashboard shall display a monthly statements table listing statement date (DD-MM-YYYY) or calendar month, reference, statement number (or count badge e.g. '2 Statements' when multiple statements exist for that month), consolidated gross rent, total deductions, earning, mortgage direct debit, and calculated out-of-pocket shortfall, sorted by date by default with toggleable ascending/descending column sorting on header click.
- AC-UI-001.2: Clicking any statement row in the ledger shall open an enlarged popup dialog displaying itemized expenditure lines categorized with Property Expenses & Maintenance positioned above Management Costs (letting fees, management fees, tenancy deposit scheme), with a multi-line header displaying gross rent, earning, shortfall, and splitting total deductions into property expenses and management cost alongside net, VAT, and gross amounts; where a month has multiple statements, the popup dialog shall provide interactive tabs to switch between the Consolidated Month Summary and each individual statement's breakdown and Edit mode.
- AC-UI-001.3: The dashboard shall format 4 executive metric cards for Gross Rent, Expenses Deduction, Net Landlord Earning, and Out-of-Pocket Shortfall (ordered Gross Rent, Expenses Deduction, Earning, and Shortfall) integrated directly within the financial summary panels.
- AC-UI-001.4: The dashboard shall display interactive monthly trend graphs plotting gross rent received, total deductions, earning, and out-of-pocket shortfall over time, with the x-axis formatted as continuous month-year periods without gaps.
- AC-UI-001.5: In the statement breakdown popup dialog, the user shall have an Edit option to modify statement date, reference, statement number, gross rent, mortgage debit, and itemized expenditure lines, recalculating total deductions, net earnings, shortfall, and amortized mortgage balances upon saving.

## UI-002: Contractor Invoices Ledger & Maintenance Items

The system shall display ingested contractor invoices in a dedicated invoice ledger with contractor name, invoice date (DD-MM-YYYY), invoice number, gross amount, and job description.

Acceptance Criteria:
- AC-UI-002.1: The dashboard shall display all ingested contractor invoices in a filterable table showing contractor name, invoice date, invoice number, gross amount, and work description, with toggleable column sorting.
- AC-UI-002.2: The system shall highlight contractor invoice lines that correspond to deduction items found in letting agency statements.

## UI-003: Executive Quiet Luxury Design System & Loan Payoff Progress

The system shall render an executive single-property dashboard using NiceGUI with a loan payoff progress bar, unified Quiet Luxury palette, and batch folder ingestion controls.

Acceptance Criteria:
- AC-UI-003.1: The dashboard shall render the loan payoff progress bar displaying the percentage value directly on the progress bar, initial principal, cumulative interest paid to date next to initial principal, current loan balance, principal repaid amount, remaining time on fixed rate formatted as years and months with total months in brackets, or months and days if less than 6 months remaining, a dual-segmented split bar displaying the cumulative mortgage payment funding split between rental income and out-of-pocket shortfall, and a concise explanatory footnote at the bottom detailing UK capital repayment mortgage mechanics with the interest and principal split percentages (without displaying or tracking property equity).
- AC-UI-003.2: The dashboard shall apply a unified Quiet Luxury dark palette featuring deep obsidian surfaces (#0E1015), champagne gold accents (#E5C07B), soft mint earnings (#86EFAC), and warm muted burgundy shortfall indicators (#9F1239) across all executive panels, tables, and interactive charts without theme selector dropdowns.
- AC-UI-003.3: The dashboard shall provide a primary Key Dashboard tab and a dedicated Rent Management tab housing the monthly trend graph and ledgers, with single-file and batch folder ingestion controls featuring animated progress feedback, in-place reactive refreshing without page reload, and automatic navigation upon completion to the Rent Management tab with the active ledger subtab set to Monthly Statements or Contractor Invoices matching the ingested document type; when a statement ingestion completes, the dashboard shall automatically open the statement popup card in edit mode.
- AC-UI-003.4: The dashboard shall render a Current Month Financial Details panel on the main dashboard featuring a dual-segmented split progress bar displaying Expenses % and Earning % side-by-side above a dedicated row of 4 metric cards for Gross Rent, Expenses Deduction, Earning, and Shortfall.
- AC-UI-003.5: The dashboard shall render a Portfolio Cumulative Summary panel on the main dashboard featuring a dual-segmented split progress bar displaying cumulative Expenses % and Earning % side-by-side above a dedicated row of 4 metric cards for cumulative Gross Rent, cumulative Expenses Deduction, cumulative Earning, and cumulative Shortfall.

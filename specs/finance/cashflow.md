# Monthly Cashflow & Mortgage Shortfall Specification

## CASH-001: Monthly Mortgage Excess Calculation

When monthly letting agency statements and mortgage direct debit terms are recorded for a calendar month, the system shall calculate the net landlord out-of-pocket excess as the difference between total mortgage direct debit due and net rental payment received.

Acceptance Criteria:
- AC-CASH-001.1: If net rental payment to landlord is less than monthly mortgage direct debit, the system shall record the positive shortfall as landlord out-of-pocket excess.
- AC-CASH-001.2: If net rental payment equals or exceeds monthly mortgage direct debit, the out-of-pocket excess shall be recorded as zero and the surplus tracked as positive cashflow.
- AC-CASH-001.3: If no rental statement exists or net rent is zero for a given month, the system shall record the full mortgage direct debit as out-of-pocket excess.
- AC-CASH-001.4: All arithmetic operations shall preserve penny precision using Python Decimal.

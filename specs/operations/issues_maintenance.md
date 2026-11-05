# Issues & Maintenance Board Specification

## ISSUE-001: Auto-Detect & Suggest Maintenance Issues

When contractor expenditure lines or invoice PDFs are ingested, the system shall suggest matching maintenance items on the Issues Board with contractor name, cost, and attached invoice.

Acceptance Criteria:
- AC-ISSUE-001.1: The system shall present suggested maintenance issues with a one-click confirmation or dismissal button.
- AC-ISSUE-001.2: When confirmed, the system shall pin the contractor invoice PDF to the issue record so it is accessible via one click from the board.
- AC-ISSUE-001.3: Where multiple invoice PDFs correspond to related repairs, the user shall be able to pin multiple invoices to a single issue.

## ISSUE-002: Maintenance Issue Lifecycle & Notes

The system shall track maintenance issues across explicit lifecycle states with support for free-text progress notes and an optional final resolution note.

Acceptance Criteria:
- AC-ISSUE-002.1: Each issue shall transition across defined states: Open, In Progress, and Resolved.
- AC-ISSUE-002.2: The user shall be able to append timestamped free-text notes to an issue at any point in its lifecycle.
- AC-ISSUE-002.3: When an issue is moved to Resolved, the system shall prompt for a final closeout note and record the resolution date.
- AC-ISSUE-002.4: The Issues Board shall display total incurred maintenance costs across all issues for the active financial year.
- AC-ISSUE-002.5: The user shall be able to manually create a maintenance issue specifying topic, category, initial cost, contractor name, and description.

## ISSUE-003: Retrospective Issue Extraction from Invoices

When triggered by the user, the system shall scan historical contractor invoices and extract unmapped invoices into suggested maintenance issues.

Acceptance Criteria:
- AC-ISSUE-003.1: When the user requests synchronization, the system shall identify all ingested contractor invoices that are not associated with any active or suggested maintenance issue.
- AC-ISSUE-003.2: The system shall create candidate suggested maintenance issues for unmapped invoices preserving contractor name, job description, invoice date, and gross amount.
- AC-ISSUE-003.3: The Issues Board shall provide a dedicated action to trigger retrospective invoice synchronization and notify the user of newly created suggestions.


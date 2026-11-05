# Tenant History & Multi-Tenant Management Specification

## TENANT-001: Tenancy Period Configuration & Historical Analytics [PLANNED]

The system shall support multiple tenant profiles defined by start date, optional end date, agreed monthly rent, and descriptive notes.

Acceptance Criteria:
- AC-TENANT-001.1: For the currently active tenancy, the system shall support setting end date to null representing an ongoing tenancy.
- AC-TENANT-001.2: The system shall automatically associate rental statements, payments, and maintenance issues to the tenant whose active date window spans the transaction date.
- AC-TENANT-001.3: The system shall provide a dedicated tenant view displaying total rent collected, payment punctuality, total maintenance costs incurred during the tenancy, and net yield.
- AC-TENANT-001.4: When a tenancy concludes, the user shall be able to record an end date and archive the tenancy while preserving all historical statements and calculations.

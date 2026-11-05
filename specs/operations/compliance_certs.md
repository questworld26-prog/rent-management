# Compliance & Certificates Register Specification

## COMP-001: Statutory Compliance Register & Expiry Alerting

The system shall maintain a statutory compliance register of safety certificates and periodic inspections with completion date, renewal due date, and status alerting.

Acceptance Criteria:
- AC-COMP-001.1: The register shall track compliance items including Gas Safety (CP12), Electrical Installation Condition Report (EICR), Energy Performance Certificate (EPC), Landlord Insurance, and boiler service.
- AC-COMP-001.2: If any certificate is due for renewal within the next 3 months (90 days), the system shall render a prominent flashing amber status pill on the overview dashboard and certificates list.
- AC-COMP-001.3: If any certificate has passed its due date without renewal, the system shall render an urgent red expired alert badge.
- AC-COMP-001.4: If a certificate has more than 3 months remaining before renewal, the system shall render a calm green valid status badge.
- AC-COMP-001.5: The user shall be able to log newly completed certificates with date completed, next due date, inspection cost, and an optional pinned PDF copy.

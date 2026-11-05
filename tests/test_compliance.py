"""Unit and integration tests for COMP-001: Statutory Compliance Register & Expiry Alerting.

Verifies:
- COMP-001: Statutory Compliance Register & Expiry Alerting
  - AC-COMP-001.1: Track compliance items (Gas Safety CP12, EICR, EPC, Landlord Insurance, boiler service).
  - AC-COMP-001.2: Flashing amber status pill for expiry within 3 months (90 days).
  - AC-COMP-001.3: Urgent red expired alert badge when due date has passed.
  - AC-COMP-001.4: Calm green valid status badge when >3 months remaining.
  - AC-COMP-001.5: Manual entry and update with date, renewal date, cost, and pinned PDF/path.
"""

from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

from src.domain.compliance import (
    calculate_compliance_status,
    format_compliance_box_data,
)
from src.storage.database import Database


# [verifies: COMP-001/AC-COMP-001.1]
def test_statutory_compliance_tracking(tmp_path: Path):
    """AC-COMP-001.1: The register shall track compliance items including Gas Safety (CP12),
    Electrical Installation Condition Report (EICR), Energy Performance Certificate (EPC),
    Landlord Insurance, and boiler service.
    """
    db = Database(db_path=tmp_path / "test_compliance.db")

    statutory_types = [
        ("Gas Safety (CP12)", "Annual CP12 Gas Safety Inspection"),
        ("Electrical (EICR)", "5-Year Electrical Installation Condition Report"),
        ("EPC", "Energy Performance Certificate"),
        ("Insurance", "Landlord Buildings & Contents Insurance"),
        ("Boiler Service", "Annual Boiler Service & Maintenance"),
    ]

    for cert_type, title in statutory_types:
        cert_id = db.create_compliance_certificate(
            certificate_type=cert_type,
            title=title,
            issue_date="01-01-2026",
            expiry_date="01-01-2027",
            provider="Certified Inspector Ltd",
            reference_number="REF-12345",
            cost=Decimal("120.00"),
        )
        assert cert_id > 0

    all_certs = db.get_all_compliance_certificates()
    assert len(all_certs) == 5
    registered_types = {c["certificate_type"] for c in all_certs}
    assert registered_types == {
        "Gas Safety (CP12)",
        "Electrical (EICR)",
        "EPC",
        "Insurance",
        "Boiler Service",
    }


# [verifies: COMP-001/AC-COMP-001.2]
def test_expiring_soon_status_within_90_days():
    """AC-COMP-001.2: If any certificate is due for renewal within the next 3 months (90 days),
    the system shall render a prominent flashing amber status pill on the overview dashboard and certificates list.
    """
    ref_dt = datetime(2026, 10, 15)

    # 45 days remaining: well within 90 days
    expiry_45_days = (ref_dt + timedelta(days=45)).strftime("%d-%m-%Y")
    status_45 = calculate_compliance_status(expiry_45_days, reference_date=ref_dt)
    assert status_45.status == "EXPIRING_SOON"
    assert status_45.status_label == "Expiring Soon"
    assert status_45.color_class == "amber"
    assert "45 days remaining" in status_45.countdown_text
    assert status_45.days_remaining == 45

    # Boundary test: exactly 90 days remaining
    expiry_90_days = (ref_dt + timedelta(days=90)).strftime("%d-%m-%Y")
    status_90 = calculate_compliance_status(expiry_90_days, reference_date=ref_dt)
    assert status_90.status == "EXPIRING_SOON"
    assert status_90.color_class == "amber"

    # Boundary test: 0 days remaining (due today)
    expiry_today = ref_dt.strftime("%d-%m-%Y")
    status_today = calculate_compliance_status(expiry_today, reference_date=ref_dt)
    assert status_today.status == "EXPIRING_SOON"
    assert status_today.days_remaining == 0


# [verifies: COMP-001/AC-COMP-001.3]
def test_expired_status_when_past_due():
    """AC-COMP-001.3: If any certificate has passed its due date without renewal,
    the system shall render an urgent red expired alert badge.
    """
    ref_dt = datetime(2026, 10, 15)

    # 10 days past expiry
    past_expiry = (ref_dt - timedelta(days=10)).strftime("%d-%m-%Y")
    status = calculate_compliance_status(past_expiry, reference_date=ref_dt)
    assert status.status == "EXPIRED"
    assert status.status_label == "Expired"
    assert status.color_class == "rose"
    assert "Expired (10 days overdue)" in status.countdown_text
    assert status.days_remaining == -10


# [verifies: COMP-001/AC-COMP-001.4]
def test_valid_status_more_than_90_days():
    """AC-COMP-001.4: If a certificate has more than 3 months remaining before renewal,
    the system shall render a calm green valid status badge.
    """
    ref_dt = datetime(2026, 10, 15)

    # 91 days remaining (> 3 months)
    expiry_91_days = (ref_dt + timedelta(days=91)).strftime("%d-%m-%Y")
    status_91 = calculate_compliance_status(expiry_91_days, reference_date=ref_dt)
    assert status_91.status == "VALID"
    assert status_91.status_label == "Valid"
    assert status_91.color_class == "emerald"
    assert status_91.days_remaining == 91

    # 400 days remaining (1 year 1 month)
    expiry_400_days = (ref_dt + timedelta(days=400)).strftime("%d-%m-%Y")
    status_400 = calculate_compliance_status(expiry_400_days, reference_date=ref_dt)
    assert status_400.status == "VALID"
    assert status_400.color_class == "emerald"
    assert "1 year" in status_400.countdown_text
    assert "remaining" in status_400.countdown_text


# [verifies: COMP-001/AC-COMP-001.5]
def test_manual_logging_updating_and_file_path(tmp_path: Path):
    """AC-COMP-001.5: The user shall be able to log newly completed certificates with date completed,
    next due date, inspection cost, and an optional pinned PDF copy.
    """
    db = Database(db_path=tmp_path / "test_compliance_ops.db")

    # 1. Create new certificate
    cert_id = db.create_compliance_certificate(
        certificate_type="Gas Safety (CP12)",
        title="Landlord Gas Safety Record 2026",
        provider="Apex Heating & Plumbing",
        reference_number="CP12-998811",
        issue_date="15-10-2026",
        expiry_date="15-10-2027",
        cost=Decimal("95.50"),
        epc_rating=None,
        file_path="/documents/compliance/CP12_2026.pdf",
        notes="All appliances passed. Flue inspection hatch checked.",
    )
    assert cert_id > 0

    retrieved = db.get_compliance_certificate_by_id(cert_id)
    assert retrieved is not None
    assert retrieved["certificate_type"] == "Gas Safety (CP12)"
    assert retrieved["title"] == "Landlord Gas Safety Record 2026"
    assert retrieved["provider"] == "Apex Heating & Plumbing"
    assert retrieved["reference_number"] == "CP12-998811"
    assert retrieved["issue_date"] == "15-10-2026"
    assert retrieved["expiry_date"] == "15-10-2027"
    assert Decimal(retrieved["cost"]) == Decimal("95.50")
    assert retrieved["file_path"] == "/documents/compliance/CP12_2026.pdf"
    assert "All appliances passed" in retrieved["notes"]

    # 2. Format box data for dashboard presentation
    formatted = format_compliance_box_data(retrieved, reference_date=datetime(2026, 10, 15))
    assert formatted["status"] == "VALID"
    assert formatted["cost_formatted"] == "£95.50"
    assert formatted["days_remaining"] == 365

    # 3. Update certificate details (e.g., when renewed next year)
    db.update_compliance_certificate(
        cert_id=cert_id,
        issue_date="15-10-2027",
        expiry_date="15-10-2028",
        cost=Decimal("100.00"),
        reference_number="CP12-998812",
        file_path="/documents/compliance/CP12_2027.pdf",
        notes="Annual renewal completed smoothly.",
    )

    updated = db.get_compliance_certificate_by_id(cert_id)
    assert updated is not None
    assert updated["issue_date"] == "15-10-2027"
    assert updated["expiry_date"] == "15-10-2028"
    assert Decimal(updated["cost"]) == Decimal("100.00")
    assert updated["reference_number"] == "CP12-998812"
    assert updated["file_path"] == "/documents/compliance/CP12_2027.pdf"
    assert updated["notes"] == "Annual renewal completed smoothly."

    # 4. Delete certificate
    db.delete_compliance_certificate(cert_id)
    assert db.get_compliance_certificate_by_id(cert_id) is None

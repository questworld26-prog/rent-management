"""Unit and integration tests for ISSUE-001 and ISSUE-002.
Verifies:
- ISSUE-001: Auto-Detect & Suggest Maintenance Issues
- ISSUE-002: Maintenance Issue Lifecycle & Notes
"""

from datetime import datetime
from decimal import Decimal
from pathlib import Path

from src.domain.issues import (
    calculate_financial_year_maintenance_costs,
    get_uk_financial_year_for_date,
)
from src.domain.models import ContractorInvoice
from src.storage.database import Database
from src.ui.components import prepare_maintenance_table_rows


# [verifies: ISSUE-002/AC-ISSUE-002.5]
def test_manual_issue_creation(tmp_path: Path):
    """AC-ISSUE-002.5: The user shall be able to manually create a maintenance issue specifying topic, category, initial cost, contractor name, and description."""
    db = Database(db_path=tmp_path / "test.db")
    issue_id = db.create_maintenance_issue(
        title="Boiler Pressure Dropping",
        category="Heating / Boiler",
        status="Open",
        priority="Urgent",
        contractor_name="British Gas",
        total_cost=Decimal("150.00"),
        reported_date="15-10-2026",
        initial_note="System loses pressure daily. Need engineer inspection.",
    )

    issue = db.get_maintenance_issue_by_id(issue_id)
    assert issue is not None
    assert issue["title"] == "Boiler Pressure Dropping"
    assert issue["category"] == "Heating / Boiler"
    assert issue["status"] == "Open"
    assert issue["priority"] == "Urgent"
    assert issue["contractor_name"] == "British Gas"
    assert Decimal(issue["total_cost"]) == Decimal("150.00")
    assert issue["is_suggested"] == 0
    assert len(issue["notes"]) == 1
    assert "inspection" in issue["notes"][0]["comment"]


# [verifies: ISSUE-002/AC-ISSUE-002.1]
def test_issue_lifecycle_transitions(tmp_path: Path):
    """AC-ISSUE-002.1: Each issue shall transition across defined states: Open, In Progress, and Resolved."""
    db = Database(db_path=tmp_path / "test.db")
    issue_id = db.create_maintenance_issue(
        title="Roof Leak in Bedroom",
        status="Open",
        total_cost=Decimal("0.00"),
        reported_date="01-10-2026",
    )

    # Transition to In Progress
    db.update_issue_status(issue_id, "In Progress")
    issue = db.get_maintenance_issue_by_id(issue_id)
    assert issue["status"] == "In Progress"
    assert issue["resolved_date"] is None

    # Transition to Resolved
    db.update_issue_status(
        issue_id,
        "Resolved",
        resolved_date="05-10-2026",
        resolution_note="Replaced broken tiles and sealed flashing.",
    )
    issue_res = db.get_maintenance_issue_by_id(issue_id)
    assert issue_res["status"] == "Resolved"
    assert issue_res["resolved_date"] == "05-10-2026"
    assert issue_res["resolution_note"] == "Replaced broken tiles and sealed flashing."


# [verifies: ISSUE-002/AC-ISSUE-002.2]
def test_append_free_text_notes_thread(tmp_path: Path):
    """AC-ISSUE-002.2: The user shall be able to append timestamped free-text notes to an issue at any point in its lifecycle."""
    db = Database(db_path=tmp_path / "test.db")
    issue_id = db.create_maintenance_issue(
        title="Radiator Valve Stuck",
        status="Open",
        total_cost=Decimal("0.00"),
        reported_date="10-10-2026",
        initial_note="Tenant reported living room radiator not warming up.",
    )

    db.add_issue_note(issue_id, "Called contractor for quote.")
    db.add_issue_note(issue_id, "Contractor booked for Tuesday 10am.")

    issue = db.get_maintenance_issue_by_id(issue_id)
    notes = issue["notes"]
    assert len(notes) == 3
    assert notes[0]["comment"] == "Tenant reported living room radiator not warming up."
    assert notes[1]["comment"] == "Called contractor for quote."
    assert notes[2]["comment"] == "Contractor booked for Tuesday 10am."


# [verifies: ISSUE-002/AC-ISSUE-002.3]
def test_resolve_prompts_closeout_note_and_date(tmp_path: Path):
    """AC-ISSUE-002.3: When an issue is moved to Resolved, the system shall prompt for a final closeout note and record the resolution date."""
    db = Database(db_path=tmp_path / "test.db")
    issue_id = db.create_maintenance_issue(
        title="Cooker Hood Filter Replacement",
        status="In Progress",
        total_cost=Decimal("45.00"),
        reported_date="12-10-2026",
    )

    closeout_text = "New carbon filters installed and tested."
    db.update_issue_status(issue_id, "Resolved", resolved_date="14-10-2026", resolution_note=closeout_text)

    issue = db.get_maintenance_issue_by_id(issue_id)
    assert issue["status"] == "Resolved"
    assert issue["resolved_date"] == "14-10-2026"
    assert issue["resolution_note"] == closeout_text
    # System note should also appear in thread
    system_notes = [n for n in issue["notes"] if "Resolved closeout note:" in n["comment"]]
    assert len(system_notes) == 1


# [verifies: ISSUE-002/AC-ISSUE-002.4]
def test_active_financial_year_maintenance_costs():
    """AC-ISSUE-002.4: The Issues Board shall display total incurred maintenance costs across all issues for the active financial year."""
    # UK Tax year 2026/2027 runs from 2026-04-06 to 2027-04-05
    ref_dt = datetime(2026, 10, 15)
    start_dt, end_dt = get_uk_financial_year_for_date(ref_dt)
    assert start_dt == datetime(2026, 4, 6, 0, 0, 0)
    assert end_dt == datetime(2027, 4, 5, 23, 59, 59)

    issues = [
        {
            "id": 1,
            "total_cost": "250.50",
            "reported_date": "10-06-2026",  # inside FY 2026-2027
            "is_suggested": False,
        },
        {
            "id": 2,
            "total_cost": "500.00",
            "reported_date": "12-11-2026",  # inside FY 2026-2027
            "is_suggested": False,
        },
        {
            "id": 3,
            "total_cost": "999.00",
            "reported_date": "15-02-2026",  # outside FY 2026-2027 (belongs to FY 2025-2026)
            "is_suggested": False,
        },
        {
            "id": 4,
            "total_cost": "300.00",
            "reported_date": "20-08-2026",  # inside FY, but unconfirmed suggestion
            "is_suggested": True,
        },
    ]

    total_fy_cost = calculate_financial_year_maintenance_costs(issues, reference_date=ref_dt)
    # 250.50 + 500.00 = 750.50
    assert total_fy_cost == Decimal("750.50")


# [verifies: ISSUE-001/AC-ISSUE-001.1]
def test_auto_suggest_and_one_click_confirmation_dismissal(tmp_path: Path):
    """AC-ISSUE-001.1: The system shall present suggested maintenance issues with a one-click confirmation or dismissal button."""
    db = Database(db_path=tmp_path / "test.db")
    inv = ContractorInvoice(
        contractor_name="Aspect Maintenance",
        invoice_date="16/10/2026",
        invoice_number="ASP-9921",
        gross_amount=Decimal("320.00"),
        job_description="Emergency plumbing unblock",
    )
    inv_id = db.save_contractor_invoice(inv)
    suggested_id = db.suggest_issue_from_invoice(inv_id)
    assert suggested_id is not None

    all_issues = db.get_all_maintenance_issues(include_suggested=True)
    suggested = [i for i in all_issues if i["is_suggested"] == 1]
    assert len(suggested) == 1
    assert suggested[0]["contractor_name"] == "Aspect Maintenance"
    assert Decimal(suggested[0]["total_cost"]) == Decimal("320.00")

    # One click confirm
    db.confirm_suggested_issue(suggested_id)
    active_issues = db.get_all_maintenance_issues(include_suggested=False)
    assert len(active_issues) == 1
    assert active_issues[0]["id"] == suggested_id
    assert active_issues[0]["is_suggested"] == 0

    # Test dismissal on a second suggestion
    inv2 = ContractorInvoice(
        contractor_name="Pest Control Ltd",
        invoice_date="18/10/2026",
        invoice_number="PC-102",
        gross_amount=Decimal("120.00"),
        job_description="Wasp nest removal",
    )
    inv2_id = db.save_contractor_invoice(inv2)
    sug2_id = db.suggest_issue_from_invoice(inv2_id)
    assert sug2_id is not None

    db.dismiss_suggested_issue(sug2_id)
    remaining_suggested = [i for i in db.get_all_maintenance_issues(include_suggested=True) if i["is_suggested"] == 1]
    assert len(remaining_suggested) == 0


# [verifies: ISSUE-001/AC-ISSUE-001.2]
def test_pin_contractor_invoice_to_issue(tmp_path: Path):
    """AC-ISSUE-001.2: When confirmed, the system shall pin the contractor invoice PDF to the issue record so it is accessible via one click from the board."""
    db = Database(db_path=tmp_path / "test.db")
    inv = ContractorInvoice(
        contractor_name="Metro Electrical",
        invoice_date="05/10/2026",
        invoice_number="ME-7788",
        gross_amount=Decimal("180.00"),
        job_description="Consumer unit inspection",
    )
    inv_id = db.save_contractor_invoice(inv)
    issue_id = db.create_maintenance_issue(
        title="Electrical Fault Investigation",
        contractor_name="Metro Electrical",
        reported_date="05-10-2026",
    )

    db.pin_invoice_to_issue(issue_id, inv_id)
    issue = db.get_maintenance_issue_by_id(issue_id)
    assert len(issue["pinned_invoices"]) == 1
    pin = issue["pinned_invoices"][0]
    assert pin["invoice_number"] == "ME-7788"
    assert pin["contractor_name"] == "Metro Electrical"
    assert Decimal(issue["total_cost"]) == Decimal("180.00")


# [verifies: ISSUE-001/AC-ISSUE-001.3]
def test_pin_multiple_invoices_to_single_issue(tmp_path: Path):
    """AC-ISSUE-001.3: Where multiple invoice PDFs correspond to related repairs, the user shall be able to pin multiple invoices to a single issue."""
    db = Database(db_path=tmp_path / "test.db")
    inv1 = ContractorInvoice(
        contractor_name="Premier Plumbing",
        invoice_date="01/10/2026",
        invoice_number="PP-001",
        gross_amount=Decimal("150.00"),
        job_description="Leak detection",
    )
    inv2 = ContractorInvoice(
        contractor_name="Premier Plumbing",
        invoice_date="04/10/2026",
        invoice_number="PP-002",
        gross_amount=Decimal("280.00"),
        job_description="Pipe replacement and sealing",
    )
    inv1_id = db.save_contractor_invoice(inv1)
    inv2_id = db.save_contractor_invoice(inv2)

    issue_id = db.create_maintenance_issue(
        title="Bathroom Water Ingress",
        contractor_name="Premier Plumbing",
        reported_date="01-10-2026",
    )

    db.pin_invoice_to_issue(issue_id, inv1_id)
    db.pin_invoice_to_issue(issue_id, inv2_id)

    issue = db.get_maintenance_issue_by_id(issue_id)
    assert len(issue["pinned_invoices"]) == 2
    # Deterministic Decimal sum: 150.00 + 280.00 = 430.00
    assert Decimal(issue["total_cost"]) == Decimal("430.00")

    # Verify table formatting
    rows = prepare_maintenance_table_rows([issue])
    assert len(rows) == 1
    assert rows[0]["cost_formatted"] == "£430.00"
    assert rows[0]["pinned_invoices_count"] == 2


# [verifies: ISSUE-003/AC-ISSUE-003.1]
def test_retrospective_issue_sync_identifies_unmapped_invoices(tmp_path: Path):
    """AC-ISSUE-003.1: Verify identifying ingested contractor invoices not associated with any active issue."""
    db = Database(db_path=tmp_path / "test.db")

    # Invoice 1: Already mapped to an existing issue
    inv1 = ContractorInvoice(
        contractor_name="Gas Safety First",
        invoice_date="10/05/2026",
        invoice_number="GS-100",
        gross_amount=Decimal("95.00"),
        job_description="Annual CP12 boiler check",
    )
    inv1_id = db.save_contractor_invoice(inv1)
    db.create_maintenance_issue(
        title="Boiler Certification",
        reported_date="10-05-2026",
        source_invoice_id=inv1_id,
    )

    # Invoices 2 & 3: Historical invoices currently unmapped
    inv2 = ContractorInvoice(
        contractor_name="City Electrical",
        invoice_date="20/06/2026",
        invoice_number="CE-202",
        gross_amount=Decimal("210.00"),
        job_description="EICR remedial socket replacement",
    )
    inv3 = ContractorInvoice(
        contractor_name="Fast Locksmiths",
        invoice_date="15/07/2026",
        invoice_number="FL-303",
        gross_amount=Decimal("85.50"),
        job_description="Front door barrel replacement",
    )
    inv2_id = db.save_contractor_invoice(inv2)
    inv3_id = db.save_contractor_invoice(inv3)

    # Trigger retrospective sync
    new_ids = db.sync_issues_from_invoices()
    assert len(new_ids) == 2

    # Verify newly created suggested issues match only the unmapped invoices
    all_suggested = [i for i in db.get_all_maintenance_issues(include_suggested=True) if i["is_suggested"] == 1]
    assert len(all_suggested) == 2
    sug_map = {s["source_invoice_id"]: s for s in all_suggested}
    assert inv1_id not in sug_map
    assert inv2_id in sug_map
    assert inv3_id in sug_map


# [verifies: ISSUE-003/AC-ISSUE-003.2]
def test_retrospective_issue_sync_preserves_invoice_attributes(tmp_path: Path):
    """AC-ISSUE-003.2: Verify candidate suggested issues preserve contractor name, description, date, and amount."""
    db = Database(db_path=tmp_path / "test.db")

    inv = ContractorInvoice(
        contractor_name="City Electrical",
        invoice_date="20/06/2026",
        invoice_number="CE-202",
        gross_amount=Decimal("210.00"),
        job_description="EICR remedial socket replacement",
    )
    inv_id = db.save_contractor_invoice(inv)

    new_ids = db.sync_issues_from_invoices()
    assert len(new_ids) == 1

    sug = db.get_maintenance_issue_by_id(new_ids[0])
    assert sug is not None
    assert "City Electrical" in sug["title"]
    assert "socket replacement" in sug["title"]
    assert Decimal(sug["total_cost"]) == Decimal("210.00")
    assert sug["reported_date"] == "20/06/2026"
    assert sug["contractor_name"] == "City Electrical"
    assert sug["source_invoice_id"] == inv_id


# [verifies: ISSUE-003/AC-ISSUE-003.3]
def test_retrospective_issue_sync_board_action_and_idempotency(tmp_path: Path):
    """AC-ISSUE-003.3: Verify triggering invoice synchronization on the board and notification idempotency."""
    db = Database(db_path=tmp_path / "test.db")

    inv = ContractorInvoice(
        contractor_name="Fast Locksmiths",
        invoice_date="15/07/2026",
        invoice_number="FL-303",
        gross_amount=Decimal("85.50"),
        job_description="Front door barrel replacement",
    )
    db.save_contractor_invoice(inv)

    # First sync returns newly created suggestions
    first_sync_ids = db.sync_issues_from_invoices()
    assert len(first_sync_ids) == 1

    # Second sync returns empty list allowing UI to notify all invoices mapped
    second_sync_ids = db.sync_issues_from_invoices()
    assert len(second_sync_ids) == 0

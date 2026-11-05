"""Unit tests for the Spec Guardian engine."""

from pathlib import Path

from tools.guardian.auditor import AuditReport, audit_specs
from tools.guardian.parser import hash_text, normalize_block, parse_spec_file
from tools.guardian.scanner import scan_codebase


def test_normalize_and_hash_block():
    raw_block = "## CASH-001: Test Title\r\n\r\n  When trigger occurs, system shall respond.  \r\n"
    normalized = normalize_block(raw_block)
    expected_normalized = "## CASH-001: Test Title\n\nWhen trigger occurs, system shall respond."
    assert normalized == expected_normalized
    assert hash_text(normalized) == hash_text(expected_normalized)


def test_parse_spec_file(tmp_path: Path):
    spec_content = """# Sample Spec

## REQ-001: First Requirement

When event A occurs, the system shall do B.

Acceptance Criteria:
- AC-REQ-001.1: Criteria one.
- AC-REQ-001.2: Criteria two.

## REQ-002: Second Requirement

The system shall always do C.

Acceptance Criteria:
- AC-REQ-002.1: Criteria for two.
"""
    spec_file = tmp_path / "sample.md"
    spec_file.write_text(spec_content)

    requirements = parse_spec_file(spec_file)
    assert len(requirements) == 2

    req1 = requirements[0]
    assert req1.req_id == "REQ-001"
    assert req1.title == "First Requirement"
    assert req1.acceptance_criteria == ["AC-REQ-001.1", "AC-REQ-001.2"]
    assert len(req1.sha256) == 64

    req2 = requirements[1]
    assert req2.req_id == "REQ-002"
    assert req2.title == "Second Requirement"
    assert req2.acceptance_criteria == ["AC-REQ-002.1"]


def test_scanner_finds_spec_and_verifies_tags(tmp_path: Path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    code_file = src_dir / "service.py"
    code_file.write_text(f"""
# [{"spec"}: REQ-001]
def process_data():
    pass
""")

    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    test_file = tests_dir / "test_service.py"
    test_file.write_text(f"""
# [{"verifies"}: REQ-001/AC-REQ-001.1]
def test_process():
    assert True
""")

    implementations, verifications = scan_codebase(src_dir, tests_dir)
    assert "REQ-001" in implementations
    assert any("service.py" in str(loc.file_path) for loc in implementations["REQ-001"])

    assert "REQ-001/AC-REQ-001.1" in verifications
    assert any("test_service.py" in str(loc.file_path) for loc in verifications["REQ-001/AC-REQ-001.1"])


def test_auditor_flags_missing_criteria(tmp_path: Path):
    spec_dir = tmp_path / "specs"
    spec_dir.mkdir()
    (spec_dir / "test.md").write_text("""
## REQ-001: Requirement

The system shall work.

Acceptance Criteria:
- AC-REQ-001.1: Criteria one.
- AC-REQ-001.2: Criteria two.
""")

    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "app.py").write_text(f"""
# [{"spec"}: REQ-001]
def run():
    pass
""")

    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_app.py").write_text(f"""
# [{"verifies"}: REQ-001/AC-REQ-001.1]
def test_one():
    pass
""")

    report: AuditReport = audit_specs(spec_dir=spec_dir, src_dir=src_dir, tests_dir=tests_dir)
    # AC-REQ-001.2 is missing tests!
    assert report.total_requirements == 1
    assert report.total_criteria == 2
    assert report.active_untested_criteria == ["REQ-001/AC-REQ-001.2"]
    assert report.has_active_violations is True


def test_auditor_filters_unstarted_specs_by_default(tmp_path: Path):
    spec_dir = tmp_path / "specs"
    spec_dir.mkdir()
    (spec_dir / "started.md").write_text("""
## REQ-001: Active Feature
The system shall do work.
Acceptance Criteria:
- AC-REQ-001.1: Criteria.
""")
    (spec_dir / "unstarted.md").write_text("""
## REQ-002: Future Feature [PLANNED]
The system shall do future work.
Acceptance Criteria:
- AC-REQ-002.1: Future criteria.
""")

    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "app.py").write_text(f"""
# [{"spec"}: REQ-001]
def run():
    pass
""")

    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_app.py").write_text(f"""
# [{"verifies"}: REQ-001/AC-REQ-001.1]
def test_one():
    pass
""")

    # Default audit: only active specs reported, clean output
    default_report = audit_specs(spec_dir=spec_dir, src_dir=src_dir, tests_dir=tests_dir, show_all=False)
    assert len(default_report.active_statuses) == 1
    assert default_report.active_statuses[0].req_id == "REQ-001"
    assert len(default_report.planned_statuses) == 1
    assert default_report.planned_statuses[0].req_id == "REQ-002"

    # --all audit: reports all specs
    all_report = audit_specs(spec_dir=spec_dir, src_dir=src_dir, tests_dir=tests_dir, show_all=True)
    assert len(all_report.requirement_statuses) == 2
    assert all_report.has_strict_violations is True

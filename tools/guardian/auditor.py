"""Audit engine and traceability generator."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from tools.guardian.parser import (
    RequirementBlock,
    parse_specs_directory,
)
from tools.guardian.scanner import (
    SemanticAuditData,
    _rel_path,
    scan_codebase,
    scan_reverse_and_semantic_traceability,
)


def _visual_width(text: str) -> int:
    """Compute approximate monospace terminal column width of a string containing emojis."""
    width = 0
    i = 0
    while i < len(text):
        ch = text[i]
        code = ord(ch)
        if code == 0xFE0F:
            i += 1
            continue
        if code in (0x2705, 0x274C, 0x23F3, 0x26A0, 0x1F512, 0x1F6AB):
            width += 2
        else:
            width += 1
        i += 1
    return width


def _pad_cell(text: str, target_width: int) -> str:
    """Pad cell string with spaces to match target visual column width."""
    pad = max(0, target_width - _visual_width(text))
    return text + (" " * pad)


def format_aligned_markdown_table(headers: list[str], rows: list[list[str]]) -> list[str]:
    """Format a Markdown table with padded columns for clean terminal & Markdown readability."""
    col_widths = [max(4, _visual_width(h)) for h in headers]
    for row in rows:
        for idx, cell in enumerate(row):
            col_widths[idx] = max(col_widths[idx], _visual_width(cell))

    header_line = "| " + " | ".join(_pad_cell(h, col_widths[i]) for i, h in enumerate(headers)) + " |"
    sep_line = "| :" + " | :".join("-" * max(3, col_widths[i] - 1) for i in range(len(headers))) + " |"

    out = [header_line, sep_line]
    for row in rows:
        out.append("| " + " | ".join(_pad_cell(row[i], col_widths[i]) for i in range(len(headers))) + " |")
    return out


@dataclass
class RequirementAuditStatus:
    req_id: str
    title: str
    spec_path: str
    sha256: str
    is_planned: bool
    acceptance_criteria: list[str]
    implementation_files: list[str] = field(default_factory=list)
    verified_criteria: list[str] = field(default_factory=list)
    unverified_criteria: list[str] = field(default_factory=list)
    status: str = "PENDING"


@dataclass
class AuditReport:
    total_requirements: int = 0
    total_criteria: int = 0
    requirement_statuses: list[RequirementAuditStatus] = field(default_factory=list)
    orphan_spec_tags: list[str] = field(default_factory=list)
    orphan_verify_tags: list[str] = field(default_factory=list)
    untagged_files: list[str] = field(default_factory=list)
    untagged_src_symbols: list[str] = field(default_factory=list)
    untagged_tests: list[str] = field(default_factory=list)
    semantic: SemanticAuditData = field(default_factory=SemanticAuditData)
    show_all: bool = False

    @property
    def active_statuses(self) -> list[RequirementAuditStatus]:
        return [s for s in self.requirement_statuses if not s.is_planned or s.status == "PREMATURE_IMPL"]

    @property
    def planned_statuses(self) -> list[RequirementAuditStatus]:
        return [s for s in self.requirement_statuses if s.is_planned and s.status == "PLANNED"]

    @property
    def unimplemented_active(self) -> list[str]:
        return [s.req_id for s in self.active_statuses if s.status in ("UNIMPLEMENTED", "REGRESSION")]

    @property
    def premature_planned(self) -> list[str]:
        return [s.req_id for s in self.requirement_statuses if s.status == "PREMATURE_IMPL"]

    @property
    def active_untested_criteria(self) -> list[str]:
        untested: list[str] = []
        for s in self.active_statuses:
            for ac in s.unverified_criteria:
                untested.append(f"{s.req_id}/{ac}")
        return untested

    @property
    def drifted_requirements(self) -> list[str]:
        return [s.req_id for s in self.requirement_statuses if s.status == "HASH_DRIFT"]

    @property
    def has_reverse_violations(self) -> bool:
        return bool(
            self.orphan_spec_tags
            or self.orphan_verify_tags
            or self.untagged_files
            or self.untagged_src_symbols
            or self.untagged_tests
        )

    @property
    def has_semantic_violations(self) -> bool:
        return bool(
            self.semantic.stacked_test_tags
            or self.semantic.weak_test_assertions
            or self.semantic.cross_link_mismatches
            or self.semantic.ac_anchor_mismatches
        )

    @property
    def has_forward_violations(self) -> bool:
        return bool(
            self.unimplemented_active
            or self.premature_planned
            or self.active_untested_criteria
            or self.drifted_requirements
        )

    @property
    def has_strict_violations(self) -> bool:
        if self.show_all and self.planned_statuses:
            return True
        return self.has_forward_violations or self.has_reverse_violations or self.has_semantic_violations

    @property
    def has_active_violations(self) -> bool:
        return self.has_strict_violations

    @property
    def has_violations(self) -> bool:
        return self.has_strict_violations

    def _render_summary(self) -> list[str]:
        active = self.active_statuses
        planned = self.planned_statuses
        active_criteria_count = sum(len(s.acceptance_criteria) for s in active)
        active_verified_count = sum(len(s.verified_criteria) for s in active)
        pct = 100 if not active_criteria_count else (active_verified_count * 100 // active_criteria_count)
        result_icon = "❌ ACTION REQUIRED" if self.has_strict_violations else "✅ ALL ACTIVE SPECS & CODE VERIFIED"

        reverse_status = (
            "✅ 100% Bound (0 unspecified symbols, 0 untagged tests, 0 orphan tags)"
            if not self.has_reverse_violations
            else (
                f"❌ {len(self.untagged_files)} untagged files, "
                f"{len(self.untagged_src_symbols)} untagged symbols, "
                f"{len(self.untagged_tests)} untagged tests, "
                f"{len(self.orphan_spec_tags) + len(self.orphan_verify_tags)} orphan tags"
            )
        )

        semantic_status = (
            "✅ 100% Aligned (1-Test-per-AC, Call-Graph Verified, Anti-Mirage Assertions, AC Anchors Matched)"
            if not self.has_semantic_violations
            else (
                f"❌ {len(self.semantic.stacked_test_tags)} stacked test tags, "
                f"{len(self.semantic.cross_link_mismatches)} call-graph mismatches, "
                f"{len(self.semantic.weak_test_assertions)} weak assertions, "
                f"{len(self.semantic.ac_anchor_mismatches)} AC anchor mismatches"
            )
        )

        return [
            "# Spec Guardian Bi-Directional Audit Report",
            f"Generated: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}",
            "",
            "## 1. Executive Summary",
            f"- **Active Requirements**:     {len(active)} active ({len(active) - len(self.unimplemented_active)} implemented, {len(self.unimplemented_active)} missing)",
            f"- **Planned Roadmap (`[PLANNED]`)**: {len(planned)} deferred for future iterations",
            f"- **Active Criteria Verified**: {active_verified_count} / {active_criteria_count} ({pct}%)",
            f"- **Reverse Traceability**:     {reverse_status}",
            f"- **Semantic & Anti-Mirage**:   {semantic_status}",
            f"- **Hash Drift Violations**:    {len(self.drifted_requirements)}",
            f"- **Audit Verdict**:            {result_icon}",
            "",
            "## 2. Active Requirements Traceability Matrix",
        ]

    def _render_active_table(self) -> list[str]:
        headers = ["Req ID", "Title", "Spec File", "Status", "Code Bound", "ACs Verified", "SHA-256"]
        rows: list[list[str]] = []
        status_badges = {
            "VERIFIED": "✅ VERIFIED",
            "UNTESTED_CRITERIA": "⚠️ UNTESTED_AC",
            "UNIMPLEMENTED": "❌ UNIMPLEMENTED",
            "REGRESSION": "❌ REGRESSION",
            "HASH_DRIFT": "❌ HASH_DRIFT",
            "PREMATURE_IMPL": "❌ PREMATURE_IMPL",
            "PLANNED": "⏳ PLANNED",
        }

        display_list = self.requirement_statuses if self.show_all else self.active_statuses
        if not display_list:
            rows.append(["(None)", "No active requirements found", "-", "⏳ PLANNED", "No", "0/0", "-"])
        else:
            for s in display_list:
                badge = status_badges.get(s.status, s.status)
                tested_summary = f"{len(s.verified_criteria)}/{len(s.acceptance_criteria)}"
                impl_summary = f"Yes ({len(s.implementation_files)})" if s.implementation_files else "No (0)"
                short_title = s.title if len(s.title) <= 44 else s.title[:41] + "..."
                rows.append(
                    [
                        s.req_id,
                        short_title,
                        Path(s.spec_path).name,
                        badge,
                        impl_summary,
                        tested_summary,
                        s.sha256[:10],
                    ]
                )
        return format_aligned_markdown_table(headers, rows)

    def _render_planned_table(self) -> list[str]:
        planned = self.planned_statuses
        if not planned or self.show_all:
            return []
        p_headers = ["Req ID", "Title", "Spec File", "Status", "Planned ACs"]
        p_rows = [
            [
                s.req_id,
                s.title if len(s.title) <= 50 else s.title[:47] + "...",
                Path(s.spec_path).name,
                "⏳ PLANNED",
                str(len(s.acceptance_criteria)),
            ]
            for s in planned
        ]
        return ["", "## 3. Planned Roadmap Requirements (`[PLANNED]`)"] + format_aligned_markdown_table(
            p_headers, p_rows
        )

    def _render_spec_violations(self) -> list[str]:
        lines: list[str] = []
        if self.unimplemented_active:
            lines.extend(["", "## ❌ Unimplemented or Regressed Active Requirements (Action Required)"])
            for r in self.unimplemented_active:
                lines.append(f"- `{r}`: Active requirement has no `# [spec: {r}]` in `src/`.")
        if self.premature_planned:
            lines.extend(["", "## ❌ Prematurely Implemented `[PLANNED]` Requirements (Action Required)"])
            for r in self.premature_planned:
                lines.append(f"- `{r}`: Spec is marked `[PLANNED]`, but code/tests already reference it.")
        if self.active_untested_criteria:
            lines.extend(["", "## ⚠️ Untested Acceptance Criteria (Action Required)"])
            for ac in self.active_untested_criteria:
                lines.append(f"- `{ac}`: Missing `# [verifies: {ac}]` in `tests/`.")
        if self.drifted_requirements:
            lines.extend(["", "## ❌ Hash Drift Detected (Specs Modified Since Last Verification)"])
            for d in self.drifted_requirements:
                lines.append(f"- `{d}`: Re-verify code/tests and run `tools.guardian audit --update-hashes`.")
        return lines

    def _render_reverse_violations(self) -> list[str]:
        lines: list[str] = []
        if self.orphan_spec_tags or self.orphan_verify_tags:
            lines.extend(["", "## ❌ Orphan / Unknown Traceability Tags (Hallucinated IDs)"])
            for item in self.orphan_spec_tags:
                lines.append(f"- Unknown `[spec]` tag: {item}")
            for item in self.orphan_verify_tags:
                lines.append(f"- Unknown `[verifies]` tag: {item}")
        if self.untagged_files:
            lines.extend(["", "## ❌ Unspecified Source Modules (Zero `# [spec: ...]` Tags)"])
            for f in self.untagged_files:
                lines.append(f"- `{f}`")
        if self.untagged_src_symbols:
            lines.extend(["", "## ❌ Unspecified Public Functions / Classes in `src/` (Feature Creep Check)"])
            for sym in self.untagged_src_symbols:
                lines.append(f"- `{sym}`")
        if self.untagged_tests:
            lines.extend(["", "## ❌ Untagged Test Functions in `tests/` (Missing `# [verifies: REQ/AC]`)"])
            for t in self.untagged_tests:
                lines.append(f"- `{t}`")
        return lines

    def _render_semantic_violations(self) -> list[str]:
        lines: list[str] = []
        if self.semantic.stacked_test_tags:
            lines.extend(["", "## ❌ Tag-Stacking Violations in `tests/` (Layer 1: 1-Test-to-1-AC Rule)"])
            for item in self.semantic.stacked_test_tags:
                lines.append(f"- `{item}`")
        if self.semantic.cross_link_mismatches:
            lines.extend(["", "## ❌ Cross-Graph Call Mismatches (Layer 2: Test Does Not Reference Bound Spec Code)"])
            for item in self.semantic.cross_link_mismatches:
                lines.append(f"- {item}")
        if self.semantic.weak_test_assertions:
            lines.extend(["", "## ❌ Weak / Mirage Test Assertions (Layer 3: Anti-Mirage AST Audit)"])
            for item in self.semantic.weak_test_assertions:
                lines.append(f"- `{item}`")
        if self.semantic.ac_anchor_mismatches:
            lines.extend(["", "## ❌ AC Backtick-Identifier Anchor Mismatches (Layer 4: Spec-to-AST Alignment)"])
            for item in self.semantic.ac_anchor_mismatches:
                lines.append(f"- {item}")
        return lines

    def to_markdown(self) -> str:
        lines = self._render_summary()
        lines.extend(self._render_active_table())
        lines.extend(self._render_planned_table())
        lines.extend(self._render_spec_violations())
        lines.extend(self._render_reverse_violations())
        lines.extend(self._render_semantic_violations())
        return "\n".join(lines)


def _check_orphan_tags(
    report: AuditReport,
    implementations: dict,
    verifications: dict,
    valid_req_ids: set[str],
    valid_ac_keys: set[str],
    base_dir: Path,
) -> None:
    """Find orphan tags in implementations and verifications."""
    for tag_req_id, locs in sorted(implementations.items()):
        if tag_req_id not in valid_req_ids:
            for loc in locs:
                report.orphan_spec_tags.append(
                    f"`{tag_req_id}` at `{_rel_path(loc.file_path, base_dir)}:{loc.line_number}`"
                )
    for tag_ac_key, locs in sorted(verifications.items()):
        if tag_ac_key not in valid_ac_keys:
            for loc in locs:
                report.orphan_verify_tags.append(
                    f"`{tag_ac_key}` at `{_rel_path(loc.file_path, base_dir)}:{loc.line_number}`"
                )


def _determine_status(
    req: RequirementBlock,
    impl_files: list[str],
    verified_acs: list[str],
    unverified_acs: list[str],
    previously_verified: set[str],
    prev_hash: str | None,
    update_hashes: bool,
) -> str:
    """Determine requirement verification status."""
    if req.is_planned:
        return "PREMATURE_IMPL" if (impl_files or verified_acs) else "PLANNED"

    if not impl_files:
        status = "REGRESSION" if req.req_id in previously_verified else "UNIMPLEMENTED"
    elif unverified_acs:
        status = "UNTESTED_CRITERIA"
    else:
        status = "VERIFIED"

    if prev_hash and prev_hash != req.sha256 and not (update_hashes and status == "VERIFIED"):
        return "HASH_DRIFT"
    return status


def _save_manifest(
    traceability_path: Path,
    report: AuditReport,
    manifest_records: list[dict],
) -> None:
    """Write specs/traceability.json manifest."""
    traceability_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_data = {
        "last_audited_at": datetime.now(UTC).isoformat(),
        "total_requirements": report.total_requirements,
        "total_criteria": report.total_criteria,
        "verified_criteria_count": sum(len(s.verified_criteria) for s in report.active_statuses),
        "planned_requirements_count": len(report.planned_statuses),
        "reverse_traceability": {
            "untagged_files_count": len(report.untagged_files),
            "untagged_src_symbols_count": len(report.untagged_src_symbols),
            "untagged_tests_count": len(report.untagged_tests),
            "orphan_tags_count": len(report.orphan_spec_tags) + len(report.orphan_verify_tags),
        },
        "semantic_alignment": {
            "stacked_test_tags_count": len(report.semantic.stacked_test_tags),
            "cross_link_mismatches_count": len(report.semantic.cross_link_mismatches),
            "weak_test_assertions_count": len(report.semantic.weak_test_assertions),
            "ac_anchor_mismatches_count": len(report.semantic.ac_anchor_mismatches),
        },
        "status": "PASS" if not report.has_strict_violations else "FAIL",
        "requirements": manifest_records,
    }
    with open(traceability_path, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2)


def audit_specs(
    spec_dir: Path,
    src_dir: Path,
    tests_dir: Path,
    traceability_path: Path | None = None,
    show_all: bool = False,
    update_hashes: bool = False,
) -> AuditReport:
    """Audit all specs against src/ and tests/ in both directions, updating traceability.json if provided."""
    base_dir = spec_dir.resolve().parent
    requirements = parse_specs_directory(spec_dir)
    implementations, verifications = scan_codebase(src_dir, tests_dir)
    untagged_files, untagged_src_symbols, untagged_tests, semantic = scan_reverse_and_semantic_traceability(
        requirements, src_dir, tests_dir, base_dir
    )

    existing_hashes: dict[str, str] = {}
    previously_verified: set[str] = set()
    if traceability_path and traceability_path.exists():
        try:
            with open(traceability_path, encoding="utf-8") as f:
                data = json.load(f)
                for req in data.get("requirements", []):
                    rid = req["requirement_id"].upper()
                    existing_hashes[rid] = req.get("verified_sha256", "")
                    if req.get("status") == "VERIFIED":
                        previously_verified.add(rid)
        except Exception:
            pass

    report = AuditReport(
        show_all=show_all,
        untagged_files=untagged_files,
        untagged_src_symbols=untagged_src_symbols,
        untagged_tests=untagged_tests,
        semantic=semantic,
        total_requirements=len(requirements),
    )

    valid_req_ids = {r.req_id for r in requirements}
    valid_ac_keys = {f"{r.req_id}/{ac.upper()}" for r in requirements for ac in r.acceptance_criteria}
    _check_orphan_tags(report, implementations, verifications, valid_req_ids, valid_ac_keys, base_dir)

    manifest_records = []
    for req in requirements:
        report.total_criteria += len(req.acceptance_criteria)
        impl_locs = implementations.get(req.req_id, [])
        impl_files = sorted({_rel_path(loc.file_path, base_dir) for loc in impl_locs})
        verified_acs = [ac for ac in req.acceptance_criteria if f"{req.req_id}/{ac.upper()}" in verifications]
        unverified_acs = [ac for ac in req.acceptance_criteria if f"{req.req_id}/{ac.upper()}" not in verifications]

        prev_hash = existing_hashes.get(req.req_id)
        status = _determine_status(
            req, impl_files, verified_acs, unverified_acs, previously_verified, prev_hash, update_hashes
        )

        status_obj = RequirementAuditStatus(
            req_id=req.req_id,
            title=req.title,
            spec_path=_rel_path(req.spec_path, base_dir),
            sha256=req.sha256,
            is_planned=req.is_planned,
            acceptance_criteria=req.acceptance_criteria,
            implementation_files=impl_files,
            verified_criteria=verified_acs,
            unverified_criteria=unverified_acs,
            status=status,
        )
        report.requirement_statuses.append(status_obj)

        manifest_records.append(
            {
                "requirement_id": req.req_id,
                "title": req.title,
                "spec_file": status_obj.spec_path,
                "is_planned": req.is_planned,
                "sha256": req.sha256,
                "verified_sha256": req.sha256 if status == "VERIFIED" else prev_hash,
                "acceptance_criteria": req.acceptance_criteria,
                "verified_criteria": verified_acs,
                "implementation_files": impl_files,
                "status": status,
            }
        )

    if traceability_path:
        _save_manifest(traceability_path, report, manifest_records)

    return report

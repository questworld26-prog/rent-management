"""Command line interface for Spec Guardian."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tools.guardian.auditor import audit_specs

STARTER_README = """# Specifications Directory (`specs/`)

This directory houses all formal system requirements written in **Easy Approach to Requirements Syntax (EARS)**.

## EARS Format Syntax Reference
Every requirement must follow one of the 5 standard EARS patterns:
1. **Ubiquitous**: The system shall [system response].
2. **Event-driven**: When [trigger], the system shall [system response].
3. **State-driven**: While [specific system state], the system shall [system response].
4. **Unwanted behaviour**: If [error condition / edge case], then the system shall [system response].
5. **Optional feature**: Where [feature flag or setting enabled], the system shall [system response].

## Requirement Structure & `[PLANNED]` Lifecycle
```markdown
## [MODULE]-[NUMBER]: [Descriptive Title]

[EARS Statement]

Acceptance Criteria:
- AC-[MODULE]-[NUMBER].1: [Criterion 1]
- AC-[MODULE]-[NUMBER].2: [Criterion 2]
```

To author roadmap specs upfront for incremental implementation, append `[PLANNED]` to the heading:
```markdown
## [MODULE]-[NUMBER]: [Future Feature Title] [PLANNED]
```
- **Active Specs (No `[PLANNED]` tag)**: Must be implemented in `src/` and 100% verified in `tests/`.
- **Planned Specs (`[PLANNED]`)**: Deferred for future steps; `guardian.py --strict` will fail if AI implements them prematurely before `[PLANNED]` is removed.

## Bi-Directional Traceability & Semantic Anti-Mirage Rules
- **Normalized Block Hashing**: Each requirement block from `## [REQ-ID]:` to the next `##` or EOF is normalized and fingerprinted via SHA-256.
- **Forward & Reverse Code Binding**: Every public function/class in `src/` must carry `# [spec: REQ-ID]`.
- **1-Test-to-1-AC Binding**: Every `def test_*` in `tests/` must carry exactly one `# [verifies: REQ-ID/AC-ID]` tag, reference a symbol/module bound to `REQ-ID`, and execute deterministic anti-mirage assertions.
- **Traceability Manifest**: `specs/traceability.json` is auto-compiled and verified by Spec Guardian.
"""

STARTER_SPEC = """# Core Module Specifications

## CORE-001: System Initialization & Configuration

When launched, the system shall validate its runtime environment and load application configuration.

Acceptance Criteria:
- AC-CORE-001.1: System reads environment variables and defaults without crashing.
- AC-CORE-001.2: System fails gracefully with an informative error message if required secrets are absent.
"""


def init_project(target_dir: Path) -> int:
    """Initialize standard specs/ structure in target project."""
    specs_dir = target_dir / "specs"
    specs_dir.mkdir(parents=True, exist_ok=True)

    readme_path = specs_dir / "README.md"
    if not readme_path.exists():
        readme_path.write_text(STARTER_README, encoding="utf-8")
        print(f"Created {readme_path}")

    starter_spec_path = specs_dir / "core.md"
    if not starter_spec_path.exists():
        starter_spec_path.write_text(STARTER_SPEC, encoding="utf-8")
        print(f"Created starter spec: {starter_spec_path}")

    print("\n✅ Spec-Driven Development initialized! Directory structure ready in specs/.")
    print("Next step: Run 'guardian audit' to generate specs/traceability.json.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="guardian",
        description="Spec Guardian: Airtight Two-Way EARS Specification & Traceability Auditor",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # audit command
    audit_parser = subparsers.add_parser("audit", help="Audit specs against code and tests in both directions")
    audit_parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with code 1 on any unimplemented active spec, untested AC, unspecified code/test, stacked test tag, semantic mismatch, or hash drift",
    )
    audit_parser.add_argument(
        "--all",
        action="store_true",
        help="Include [PLANNED] roadmap specs in the main matrix and require 0 planned specs remaining when combined with --strict",
    )
    audit_parser.add_argument(
        "--update-hashes",
        action="store_true",
        help="Update verified hashes in traceability.json for specs whose criteria are fully verified",
    )
    audit_parser.add_argument(
        "--specs-dir",
        type=Path,
        default=Path("specs"),
        help="Path to specs directory (default: specs)",
    )
    audit_parser.add_argument(
        "--src-dir",
        type=Path,
        default=Path("src"),
        help="Path to source directory (default: src)",
    )
    audit_parser.add_argument(
        "--tests-dir",
        type=Path,
        default=Path("tests"),
        help="Path to tests directory (default: tests)",
    )
    audit_parser.add_argument(
        "--traceability",
        type=Path,
        default=Path("specs/traceability.json"),
        help="Path to traceability output file (default: specs/traceability.json)",
    )

    # report command
    report_parser = subparsers.add_parser("report", help="Print verification matrix report")
    report_parser.add_argument(
        "--all",
        action="store_true",
        help="Include all [PLANNED] requirements in main report table",
    )
    report_parser.add_argument(
        "--specs-dir",
        type=Path,
        default=Path("specs"),
        help="Path to specs directory",
    )
    report_parser.add_argument(
        "--src-dir",
        type=Path,
        default=Path("src"),
        help="Path to source directory",
    )
    report_parser.add_argument(
        "--tests-dir",
        type=Path,
        default=Path("tests"),
        help="Path to tests directory",
    )

    # init command
    init_parser = subparsers.add_parser("init", help="Initialize specs directory and starter EARS spec")
    init_parser.add_argument(
        "--target-dir",
        type=Path,
        default=Path("."),
        help="Target project directory (default: current directory)",
    )

    args = parser.parse_args()

    if args.command == "init":
        return init_project(args.target_dir)

    elif args.command == "audit":
        report = audit_specs(
            spec_dir=args.specs_dir,
            src_dir=args.src_dir,
            tests_dir=args.tests_dir,
            traceability_path=args.traceability,
            show_all=args.all,
            update_hashes=args.update_hashes,
        )
        print(report.to_markdown())
        if args.strict and report.has_strict_violations:
            print(
                "\n❌ Spec Guardian strict check failed: Forward, reverse, or semantic traceability violations present.",
                file=sys.stderr,
            )
            return 1
        return 0

    elif args.command == "report":
        report = audit_specs(
            spec_dir=args.specs_dir,
            src_dir=args.src_dir,
            tests_dir=args.tests_dir,
            show_all=args.all,
        )
        print(report.to_markdown())
        return 0

    return 0

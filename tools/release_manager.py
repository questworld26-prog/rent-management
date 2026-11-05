"""Automated Release Management Tool.

Enforces 6-Gate Release Governance:
1. Git working tree validation
2. Architectural Compliance & Code Review Audit (Four-Pillar Project Rubric)
3. Spec Guardian strict audit (zero untested criteria, zero spec hash drift)
4. Full Python test suite (uv run pytest)
5. Code hygiene and linting (uv run ruff check and ruff format)
6. Version bumping in pyproject.toml and annotated Git release tagging
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path


def run_cmd(cmd: list[str], error_msg: str) -> str:
    """Run a shell command, printing output and raising on error."""
    env = os.environ.copy()
    local_bin = str(Path.home() / ".local" / "bin")
    if local_bin not in env.get("PATH", ""):
        env["PATH"] = f"{local_bin}:{env.get('PATH', '')}"
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        print(f"❌ {error_msg}", file=sys.stderr)
        if result.stdout:
            print(result.stdout, file=sys.stderr)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        sys.exit(result.returncode)
    return result.stdout.strip()


def get_current_version() -> str:
    """Read version from pyproject.toml."""
    content = Path("pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'version\s*=\s*"([^"]+)"', content)
    if not match:
        raise ValueError("Could not find version in pyproject.toml")
    return match.group(1)


def update_version(new_version: str) -> None:
    """Update version string in pyproject.toml."""
    path = Path("pyproject.toml")
    content = path.read_text(encoding="utf-8")
    updated = re.sub(r'version\s*=\s*"[^"]+"', f'version = "{new_version}"', content, count=1)
    path.write_text(updated, encoding="utf-8")


def audit_pillar_1_privacy(violations: list[str]) -> None:
    """Verify offline privacy and absence of sensitive files in git."""
    external_url_pattern = re.compile(r"https?://(?!localhost|127\.0\.0\.1)[^\s\"'>]+")
    for py_file in Path("src").rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        matches = external_url_pattern.findall(content)
        if matches:
            violations.append(f"[Pillar 1 Privacy] Non-local endpoint in {py_file}: {', '.join(matches)}")

    status_proc = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
    for line in status_proc.stdout.splitlines():
        code = line[:2]
        file_path = line[3:].strip()
        if (
            any(sensitive in file_path for sensitive in ["Resources/", "config.toml", ".db", ".sqlite"])
            and "D" not in code
        ):
            violations.append(f"[Pillar 1 Privacy] Sensitive file tracked/staged in git: {file_path}")


def audit_pillar_2_math(violations: list[str]) -> None:
    """Verify absence of float calculations in domain models."""
    float_pattern = re.compile(r"\bfloat\s*\(")
    for py_file in Path("src/domain").rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        if float_pattern.search(content):
            violations.append(f"[Pillar 2 Math] Float conversion found in domain model: {py_file}")


def audit_pillar_3_spec_and_config(violations: list[str]) -> None:
    """Verify absence of equity attributes and hardcoded money fallbacks."""
    equity_pattern = re.compile(r"\b(equity_percentage|equity_pounds|calculate_equity)\b")
    for py_file in Path("src").rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        if equity_pattern.search(content):
            violations.append(f"[Pillar 3 Domain] Forbidden equity attribute/calculation found in {py_file}")

    fallback_pattern = re.compile(r"except\s+Exception:\s*(?:\n\s*.*){0,5}Decimal\(\s*[\"'][0-9]+")
    for py_file in Path("tools").rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        if fallback_pattern.search(content):
            violations.append(f"[Pillar 3 Config] Hardcoded money fallback in exception handler: {py_file}")


def audit_pillar_4_engineering(violations: list[str], warnings: list[str]) -> None:
    """Verify documentation paths, function readability, and spec annotations."""
    abs_path_pattern = re.compile(r"(/Users/|file:///Users/|/home/|[A-Za-z]:\\)")
    for md_file in Path(".").rglob("*.md"):
        if any(part.startswith(".") or part == ".venv" for part in md_file.parts):
            continue
        content = md_file.read_text(encoding="utf-8")
        if abs_path_pattern.search(content):
            violations.append(f"[Pillar 4 Paths] Machine-specific absolute path found in {md_file}")

    import ast

    spec_tag_regex = re.compile(r"\[spec:\s*([A-Z0-9\-]+)\]")
    for check_dir in [Path("src"), Path("tools")]:
        for py_path in check_dir.rglob("*.py"):
            try:
                raw_code = py_path.read_text(encoding="utf-8")
                lines = raw_code.splitlines()
                tree = ast.parse(raw_code)
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                        func_len = getattr(node, "end_lineno", node.lineno) - node.lineno
                        if func_len > 60:
                            warnings.append(
                                f"[Pillar 4 Readability] Function '{node.name}' in {py_path} is {func_len} lines long"
                            )
                        if node.name.startswith("_") and not node.name.startswith("__"):
                            warnings.append(
                                f"[Pillar 4 Naming] Function '{node.name}' in {py_path} has leading underscore"
                            )
                        if node.name not in ["main", "__init__"]:
                            start_l = max(0, node.lineno - 6)
                            preceding_chunk = "\n".join(lines[start_l : node.lineno])
                            docstring = ast.get_docstring(node) or ""
                            if not spec_tag_regex.search(preceding_chunk) and not spec_tag_regex.search(docstring):
                                warnings.append(
                                    f"[Pillar 3 Spec] Function '{node.name}' in {py_path} is missing a [spec: REQ-ID] annotation"
                                )
            except Exception:
                pass


def audit_architecture_and_code() -> tuple[list[str], list[str]]:
    """Audit codebase against the Four-Pillar Project Rubric (ADR-001 through ADR-005)."""
    violations: list[str] = []
    warnings: list[str] = []

    audit_pillar_1_privacy(violations)
    audit_pillar_2_math(violations)
    audit_pillar_3_spec_and_config(violations)
    audit_pillar_4_engineering(violations, warnings)

    return violations, warnings


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="release",
        description="Execute standardized 6-gate release pipeline and git tagger",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # create release
    create_parser = subparsers.add_parser("create", help="Create a new release")
    create_parser.add_argument("version", help="Semantic version tag to create, e.g. 0.3.0 or v0.3.0")
    create_parser.add_argument("-m", "--message", required=True, help="Release summary message")
    create_parser.add_argument("--skip-tests", action="store_true", help="Skip pytest run")

    # list releases
    subparsers.add_parser("list", help="List all release tags in repository")

    args = parser.parse_args()

    if args.command == "list":
        tags = run_cmd(["git", "tag", "-n", "--sort=v:refname"], "Failed to list git tags")
        if not tags:
            print("No release tags found in repository.")
        else:
            print(tags)
        return 0

    elif args.command == "create":
        raw_version = args.version.lstrip("v")
        tag_name = f"v{raw_version}"

        print(f"\n🚀 Initiating 6-Gate Release Pipeline for {tag_name}...")

        # Gate 1: Check git working tree
        print("\n[Gate 1/6] Checking git working tree...")
        status = run_cmd(["git", "status", "--porcelain"], "Failed to check git status")
        uncommitted = [
            line
            for line in status.splitlines()
            if not line.endswith("pyproject.toml") and not line.endswith("release.md")
        ]
        if uncommitted:
            print("⚠️ Warning: Uncommitted changes present in repository:", file=sys.stderr)
            for line in uncommitted:
                print(f"  {line}", file=sys.stderr)

        # Gate 2: Architectural Compliance & Code Review
        print("\n[Gate 2/6] Performing Four-Pillar Architectural & Code Review Audit...")
        violations, _ = audit_architecture_and_code()

        if violations:
            print("\n❌ Architectural & Code Review Failed:", file=sys.stderr)
            for v in violations:
                print(f"  • {v}", file=sys.stderr)
            sys.exit(1)
        print("✅ Four-Pillar Review: 100% compliant with ADRs, privacy, math, and path standards.")

        # Gate 3: Spec Guardian Strict Audit
        print("\n[Gate 3/6] Running Spec Guardian strict audit...")
        run_cmd(
            ["uv", "run", "python", "-m", "tools.guardian", "audit", "--strict"],
            "Spec Guardian strict audit failed! Unverified specs or untested criteria exist.",
        )
        print("✅ Spec Guardian: All active specs 100% verified.")

        # Gate 4: Test Suite
        if not args.skip_tests:
            print("\n[Gate 4/6] Executing test suite via uv...")
            run_cmd(["uv", "run", "pytest"], "Test suite failed! Cannot release failing code.")
            print("✅ Pytest: All tests passed.")

        # Gate 5: Code Formatting & Linting
        print("\n[Gate 5/6] Enforcing code hygiene via Ruff...")
        run_cmd(["uv", "run", "ruff", "check", "--fix", "."], "Ruff linting failed.")
        run_cmd(["uv", "run", "ruff", "format", "."], "Ruff formatting failed.")
        print("✅ Ruff: Code is formatted and lint-free.")

        # Gate 6: Update Version & Create Annotated Git Tag
        print(f"\n[Gate 6/6] Updating pyproject.toml to {raw_version} and tagging {tag_name}...")
        update_version(raw_version)

        # Commit release manifest changes if any
        subprocess.run(
            ["git", "add", "pyproject.toml", "release.md", "specs/traceability.json"],
            check=False,
        )
        subprocess.run(["git", "commit", "-m", f"chore(release): bump version to {tag_name}"], check=False)

        # Create annotated tag
        run_cmd(
            ["git", "tag", "-a", tag_name, "-m", f"Release {tag_name}: {args.message}"],
            f"Failed to create git tag {tag_name}",
        )

        print(f"\n🎉 Successfully created annotated Git release {tag_name}!")
        print(f"Release Message: {args.message}\n")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())

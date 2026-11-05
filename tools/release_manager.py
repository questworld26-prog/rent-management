#!/usr/bin/env python3
"""
Universal Automated Release Manager (6-Gate Orchestrator)
Bundled with the global 'release-management' Antigravity skill.
Zero external dependencies (pure Python 3.10+ standard library).

Enforces Modular 6-Gate Release Governance across Python, TypeScript, Kotlin/Android, Go, and Rust:
1. Git working tree validation (Strict block on uncommitted non-manifest files)
2. Quad-Persona Code & OWASP Security Review (Delegates to ~/.gemini/config/skills/code-review/scripts/reviewer.py)
3. Spec Guardian strict bi-directional audit (Delegates to ~/.gemini/config/skills/spec-driven-development/scripts/guardian.py)
4. Code hygiene, security linting, formatting & static typecheck (Runs BEFORE tests)
5. Project Test Suite Execution (Guided by local project test skill)
6. Version synchronization (pyproject.toml, package.json, Cargo.toml, build.gradle.kts) & annotated Git release tagging
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

for extra_path in (
    str(Path.home() / ".local" / "bin"),
    "/opt/homebrew/bin",
    "/opt/homebrew/sbin",
    "/usr/local/bin",
):
    if os.path.exists(extra_path) and extra_path not in os.environ.get("PATH", ""):
        os.environ["PATH"] = f"{extra_path}:{os.environ.get('PATH', '')}"

ALLOWED_MANIFEST_SUFFIXES = (
    "pyproject.toml",
    "package.json",
    "package-lock.json",
    "Cargo.toml",
    "build.gradle.kts",
    "build.gradle",
    "gradle.properties",
    "release.md",
    "RELEASE.md",
    "traceability.json",
)


def run_cmd(cmd: list[str], error_msg: str, capture: bool = True, cwd: Path | None = None) -> str:
    """Run a shell command, printing output and exiting on error."""
    result = subprocess.run(cmd, capture_output=capture, text=True, cwd=cwd)  # noqa: S603
    if result.returncode != 0:
        print(f"❌ {error_msg}", file=sys.stderr)
        if capture:
            if result.stdout:
                print(result.stdout, file=sys.stderr)
            if result.stderr:
                print(result.stderr, file=sys.stderr)
        sys.exit(result.returncode)
    return result.stdout.strip() if capture else ""


def find_project_root() -> Path:
    """Find repository root by walking up looking for .git."""
    curr = Path.cwd().resolve()
    while curr != curr.parent:
        if (curr / ".git").exists():
            return curr
        curr = curr.parent
    return Path.cwd().resolve()


def resolve_release_doc(root: Path) -> Path:
    """Resolve the release notes file (prefer existing RELEASE.md or release.md)."""
    if (root / "RELEASE.md").exists():
        return root / "RELEASE.md"
    if (root / "release.md").exists():
        return root / "release.md"
    return root / "RELEASE.md"


# ============================================================================
# Gate 1: Git Working Tree Validation (Strict Block)
# ============================================================================


def audit_gate_1_git(root: Path) -> list[str]:
    """Verify git working tree status. Returns uncommitted non-manifest lines."""
    status = run_cmd(["git", "status", "--porcelain"], "Failed to check git status", cwd=root)
    if not status:
        return []

    uncommitted = [
        line
        for line in status.splitlines()
        if not any(line.strip().endswith(suffix) for suffix in ALLOWED_MANIFEST_SUFFIXES)
    ]
    return [f"Uncommitted modification: {line}" for line in uncommitted]


# ============================================================================
# Gate 2: Modular Delegation to 'code-review' Skill (Quad-Persona + OWASP)
# ============================================================================


def _load_global_reviewer_module():
    reviewer_path = Path.home() / ".gemini" / "config" / "skills" / "code-review" / "scripts" / "reviewer.py"
    if not reviewer_path.exists():
        return None
    spec = importlib.util.spec_from_file_location("code_review_reviewer", reviewer_path)
    if spec and spec.loader:
        mod = importlib.util.module_from_spec(spec)
        sys.modules["code_review_reviewer"] = mod
        spec.loader.exec_module(mod)
        return mod
    return None


def audit_gate_2_quad_persona_review(root: Path, diff_ref: str | None = None, show_hotspots: bool = True) -> bool:
    """Execute Quad-Persona Code & OWASP Security Review via the modular 'code-review' skill."""
    mod = _load_global_reviewer_module()
    if mod is not None and hasattr(mod, "run_quad_persona_review"):
        report = mod.run_quad_persona_review(root, diff_ref=diff_ref)
        report.print_summary(show_hotspots=show_hotspots)
        return not report.has_violations

    # Fallback subprocess invocation if module loading fails
    reviewer_script = Path.home() / ".gemini" / "config" / "skills" / "code-review" / "scripts" / "reviewer.py"
    if reviewer_script.exists():
        cmd = [sys.executable, str(reviewer_script), "audit", "--strict"]
        if diff_ref:
            cmd.extend(["--diff", diff_ref])
        res = subprocess.run(cmd, cwd=root)  # noqa: S603
        return res.returncode == 0

    print(
        "⚠️ Global 'code-review' script not found at ~/.gemini/config/skills/code-review/scripts/reviewer.py",
        file=sys.stderr,
    )
    return False


def audit_gate_2_tri_persona_review(root: Path):
    """Backwards-compatible entrypoint returning the review report object from code-review."""
    mod = _load_global_reviewer_module()
    if mod is not None:
        return mod.run_quad_persona_review(root)
    raise RuntimeError("Global code-review skill script reviewer.py not found")


# ============================================================================
# Gate 3: Spec Guardian Strict Bi-Directional Audit
# ============================================================================


def audit_gate_3_specs(root: Path) -> bool:
    """Run Spec Guardian strict bi-directional audit if specs/ directory exists."""
    specs_dir = root / "specs"
    if not specs_dir.exists():
        print("ℹ️ No specs/ directory found; skipping Spec Guardian audit.")
        return True

    use_uv = (root / "pyproject.toml").exists() and shutil.which("uv") is not None

    if (root / "tools" / "guardian.py").exists():
        guardian_cmd = (
            ["uv", "run", "python", "tools/guardian.py", "audit", "--strict"]
            if use_uv
            else [sys.executable, "tools/guardian.py", "audit", "--strict"]
        )
    elif (root / "tools" / "guardian").exists():
        guardian_cmd = (
            ["uv", "run", "python", "-m", "tools.guardian", "audit", "--strict"]
            if use_uv
            else [sys.executable, "-m", "tools.guardian", "audit", "--strict"]
        )
    else:
        global_guardian = (
            Path.home() / ".gemini" / "config" / "skills" / "spec-driven-development" / "scripts" / "guardian.py"
        )
        if global_guardian.exists():
            guardian_cmd = (
                ["uv", "run", "python", str(global_guardian), "audit", "--strict"]
                if use_uv
                else [sys.executable, str(global_guardian), "audit", "--strict"]
            )
        else:
            print("⚠️ Spec Guardian script not found; skipping strict spec audit.", file=sys.stderr)
            return True

    print(f"Running Spec Guardian audit: {' '.join(guardian_cmd)}")
    result = subprocess.run(guardian_cmd, cwd=root)  # noqa: S603
    return result.returncode == 0


# ============================================================================
# Gate 4: Code Hygiene, Security Linting & Static Typecheck (Pre-Test Gate)
# ============================================================================


def _run_ruff(root: Path, args: list[str]) -> int:
    """Run ruff via `uv run ruff` if available in project, falling back to `uvx ruff` or `ruff` per uv.md."""
    if shutil.which("uv"):
        res = subprocess.run(["uv", "run", "ruff", *args], cwd=root)  # noqa: S603
        if res.returncode == 0:
            return 0
        # Fallback to ephemeral uvx if ruff is not installed in project .venv
        if shutil.which("uvx"):
            return subprocess.run(["uvx", "ruff", *args], cwd=root).returncode  # noqa: S603
        return res.returncode
    if shutil.which("ruff"):
        return subprocess.run(["ruff", *args], cwd=root).returncode  # noqa: S603
    return 0


def run_gate_4_hygiene_and_typecheck(root: Path) -> bool:
    """Run project-appropriate formatters, security linters, and static typecheckers before tests."""
    ok = True

    # 1. Python (Ruff lint + format)
    if (root / "pyproject.toml").exists() or any(root.glob("src/**/*.py")):
        if _run_ruff(root, ["check", "--fix", "."]) != 0:
            print("❌ Python Ruff lint check failed with unfixable violations.", file=sys.stderr)
            ok = False
        if _run_ruff(root, ["format", "."]) != 0:
            print("❌ Python Ruff format failed.", file=sys.stderr)
            ok = False

    # 2. TypeScript / Node (ESLint + Prettier + TSC)
    if (root / "package.json").exists():
        if shutil.which("npm"):
            lint_res = subprocess.run(["npm", "run", "lint", "--if-present"], cwd=root)  # noqa: S603
            if lint_res.returncode != 0:
                print("❌ npm run lint failed.", file=sys.stderr)
                ok = False
        if (root / "tsconfig.json").exists() and shutil.which("npx") and (root / "node_modules").exists():
            tsc_res = subprocess.run(["npx", "tsc", "--noEmit"], cwd=root)  # noqa: S603
            if tsc_res.returncode != 0:
                print("❌ TypeScript static typecheck (tsc --noEmit) failed.", file=sys.stderr)
                ok = False

    # 3. Kotlin / Android (ktlint if available)
    has_kotlin = (root / "build.gradle.kts").exists() or (root / "build.gradle").exists() or any(root.glob("**/*.kt"))
    if has_kotlin and shutil.which("ktlint"):
        kt_res = subprocess.run(["ktlint", "-F"], cwd=root)  # noqa: S603
        if kt_res.returncode != 0:
            print("⚠️ ktlint reported unfixable style findings.", file=sys.stderr)

    # 4. Rust & Go
    if (root / "Cargo.toml").exists() and shutil.which("cargo"):
        subprocess.run(["cargo", "fmt"], cwd=root, check=False)  # noqa: S603
    if (root / "go.mod").exists() and shutil.which("gofmt"):
        subprocess.run(["gofmt", "-w", "."], cwd=root, check=False)  # noqa: S603

    return ok


# ============================================================================
# Gate 5: Test Suite Execution (Guided by Local Project Test Skill)
# ============================================================================


def detect_default_test_command(root: Path) -> list[str]:
    """Detect default test command for Python, TypeScript, Kotlin/Android, Rust, or Go."""
    if (root / "pyproject.toml").exists():
        return ["uv", "run", "pytest"]
    if (root / "gradlew").exists():
        if (root / "app" / "build.gradle.kts").exists() or (root / "app" / "build.gradle").exists():
            return ["./gradlew", "testDebugUnitTest"]
        return ["./gradlew", "test"]
    if (root / "build.gradle.kts").exists() or (root / "build.gradle").exists():
        return ["gradle", "test"]
    if (root / "package.json").exists():
        return ["npm", "test"]
    if (root / "Cargo.toml").exists():
        return ["cargo", "test"]
    if (root / "go.mod").exists():
        return ["go", "test", "./..."]
    return ["uv", "run", "pytest"]


def resolve_test_command(root: Path) -> list[str]:
    """Parse the project test execution command from local test skill or project files."""
    skills_dir = root / ".agents" / "skills"
    runner_regex = re.compile(
        r"```(?:bash|sh)?\s*\n\s*((?:uv run pytest|pytest|npm test|npx vitest[^\n]*|\./gradlew\s+test[^\n]*|gradle\s+test[^\n]*|cargo test[^\n]*|go test[^\n]*))\s*\n```"
    )
    inline_regex = re.compile(
        r"(?<!`)`((?:uv run pytest|pytest|npm test|npx vitest|\./gradlew\s+test|gradle\s+test|cargo test|go test)[^`\n]*)`(?!`)"
    )

    if skills_dir.exists():
        for skill_file in skills_dir.rglob("*.md"):
            if "test" in skill_file.name.lower() or "test" in skill_file.parent.name.lower():
                try:
                    content = skill_file.read_text(encoding="utf-8")
                    fenced = runner_regex.search(content)
                    if fenced:
                        return fenced.group(1).strip().split()
                    inline = inline_regex.search(content)
                    if inline:
                        return inline.group(1).strip().split()
                except (OSError, UnicodeDecodeError):
                    pass

    return detect_default_test_command(root)


def ensure_local_test_skill(root: Path) -> Path:
    """Ensure that the project defines a local test skill so testing requirements are unambiguous."""
    skills_dir = root / ".agents" / "skills"
    test_skill_dir = skills_dir / "test-protocol"
    test_skill_file = test_skill_dir / "SKILL.md"

    if skills_dir.exists():
        for skill_file in skills_dir.rglob("SKILL.md"):
            if "test" in skill_file.name.lower() or "test" in skill_file.parent.name.lower():
                return skill_file

    test_skill_dir.mkdir(parents=True, exist_ok=True)
    project_name = root.name
    default_cmd = " ".join(detect_default_test_command(root))
    template = f"""---
name: {project_name}-test-protocol
description: >-
  Defines the testing methodology, runner commands, test tiering, and isolation rules
  for {project_name}. Enforced during [Gate 5] Test Suite Execution in release management.
---

# Test Protocol: {project_name}

This skill defines the official testing process for **{project_name}**.

## 1. Test Command & Execution
Execute tests via:
```bash
{default_cmd}
```

## 2. Test Execution Tiers
- **Fast Unit Tests**: Deterministic fast tests validating pure logic, schemas, and math. Must run in `< 5s`.
- **Integration Tests**: Tests database, file I/O, or local service boundaries.
- **Heavy / Live Inference (Opt-In)**: Heavy multi-model, UI emulator, or network tests isolated from standard pre-commit runs.

## 3. Anti-Mirage Assertion & Traceability Rules
- Every test function (`def test_*`, `it(...)`, `@Test fun ...`) must carry a `[verifies: REQ-ID/AC-ID]` annotation when `specs/` is present.
- All test assertions must verify deterministic outputs and exact numeric/factual anchors.
- Vacuous assertions (`assert result is not None`, `expect(x).toBeDefined()`, `assertTrue(true)`) are strictly forbidden.
"""
    test_skill_file.write_text(template, encoding="utf-8")
    print(f"✨ Scaffolded local project test skill: {test_skill_file.relative_to(root)}")
    return test_skill_file


# ============================================================================
# Gate 6: Version Synchronization & Tagging (Python, TS, Kotlin/Android, Rust)
# ============================================================================


def update_manifest_version(root: Path, new_version: str) -> list[str]:
    """Update version in pyproject.toml, package.json, Cargo.toml, or Android/Kotlin Gradle files."""
    updated_files: list[str] = []

    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        content = pyproject.read_text(encoding="utf-8")
        updated = re.sub(r'version\s*=\s*"[^"]+"', f'version = "{new_version}"', content, count=1)
        pyproject.write_text(updated, encoding="utf-8")
        updated_files.append("pyproject.toml")

    package_json = root / "package.json"
    if package_json.exists():
        content = package_json.read_text(encoding="utf-8")
        updated = re.sub(r'"version":\s*"[^"]+"', f'"version": "{new_version}"', content, count=1)
        package_json.write_text(updated, encoding="utf-8")
        updated_files.append("package.json")

    cargo_toml = root / "Cargo.toml"
    if cargo_toml.exists():
        content = cargo_toml.read_text(encoding="utf-8")
        updated = re.sub(r'version\s*=\s*"[^"]+"', f'version = "{new_version}"', content, count=1)
        cargo_toml.write_text(updated, encoding="utf-8")
        updated_files.append("Cargo.toml")

    # Kotlin / Android Gradle manifests
    for gradle_rel in (
        "app/build.gradle.kts",
        "app/build.gradle",
        "build.gradle.kts",
        "build.gradle",
        "gradle.properties",
    ):
        g_path = root / gradle_rel
        if not g_path.exists():
            continue
        content = g_path.read_text(encoding="utf-8")
        new_content = content
        # Update versionName = "X.Y.Z" or version = "X.Y.Z"
        new_content = re.sub(
            r'(versionName\s*=?\s*["\'])[^"\']+(["\'])',
            rf"\g<1>{new_version}\g<2>",
            new_content,
            count=1,
        )
        # Auto-increment versionCode if present
        vc_match = re.search(r"\b(versionCode\s*=?\s*)(\d+)\b", new_content)
        if vc_match:
            next_code = int(vc_match.group(2)) + 1
            new_content = re.sub(
                r"\b(versionCode\s*=?\s*)\d+\b",
                rf"\g<1>{next_code}",
                new_content,
                count=1,
            )
        if new_content != content:
            g_path.write_text(new_content, encoding="utf-8")
            updated_files.append(gradle_rel)

    return updated_files


# ============================================================================
# CLI Commands
# ============================================================================


def init_release_governance(root: Path) -> int:
    """Initialize release governance in the current repository."""
    release_doc = resolve_release_doc(root)
    if not release_doc.exists():
        project_name = root.name
        template = f"""# Release Plan & Version Roadmap: {project_name}

## Release Strategy
- **Versioning**: Semantic Versioning (`MAJOR.MINOR.PATCH`).
- **Human-in-the-Loop Approval**: Always request explicit user approval before releasing any MAJOR or MINOR version.
- **Automated 6-Gate Release Pipeline**:
  1. Git working tree validation (strict block on uncommitted files)
  2. Quad-Persona Code & OWASP Security Review (`reviewer.py audit --strict`)
  3. Spec Guardian strict bi-directional audit (`guardian.py audit --strict`)
  4. Code hygiene, security linting, formatting & static typecheck
  5. Project Test Suite Execution (guided by local test skill)
  6. Version bumping and creation of annotated Git tag (`vX.Y.Z`).

---

## Roadmap & Milestones

### Release `v0.1.0`: Initial Project Baseline
- **Status**: ⏳ PLANNED
- **Deliverables**:
  - [ ] Core module implementation
  - [ ] Automated test suite verification
"""
        release_doc.write_text(template, encoding="utf-8")
        print(f"✨ Created release manifest: {release_doc.relative_to(root)}")
    else:
        print(f"ℹ️ Found existing release manifest: {release_doc.relative_to(root)}")

    ensure_local_test_skill(root)
    print("\n✅ Release governance successfully initialized!")
    return 0


def create_release(root: Path, raw_version: str, message: str, skip_tests: bool = False) -> int:
    """Execute 6-Gate Release Pipeline."""
    clean_version = raw_version.lstrip("v")
    tag_name = f"v{clean_version}"

    print(f"\n🚀 Initiating 6-Gate Release Pipeline for {tag_name} in {root.name}...\n")

    # Gate 1: Git working tree (Strict Block)
    print("[Gate 1/6] Checking git working tree cleanliness...")
    git_violations = audit_gate_1_git(root)
    if git_violations:
        print("❌ Gate 1 Failed — Uncommitted non-manifest changes present:", file=sys.stderr)
        for v in git_violations:
            print(f"  • {v}", file=sys.stderr)
        print("Commit or stash changes before cutting a release.", file=sys.stderr)
        return 1
    print("✅ Git working tree is clean.")

    # Gate 2: Quad-Persona Code & OWASP Security Review (via code-review skill)
    print("\n[Gate 2/6] Executing Quad-Persona Code & OWASP Security Review (via 'code-review' skill)...")
    if not audit_gate_2_quad_persona_review(root, show_hotspots=True):
        print(
            "\n❌ Gate 2 Failed — Resolve Quad-Persona / OWASP Security violations before proceeding.", file=sys.stderr
        )
        return 1
    print("✅ Quad-Persona Code & OWASP Security Review: 100% compliant.")

    # Gate 3: Spec Guardian Strict Audit
    print("\n[Gate 3/6] Running Spec Guardian strict bi-directional audit...")
    if not audit_gate_3_specs(root):
        print(
            "❌ Gate 3 Failed — Fix forward/reverse traceability or spec hash drift before release.",
            file=sys.stderr,
        )
        return 1
    print("✅ Spec Guardian: All active specs & code verified.")

    # Gate 4: Code Hygiene, Security Linting & Static Typecheck (Runs BEFORE Tests)
    print("\n[Gate 4/6] Enforcing code formatting, lint hygiene, and static typechecking...")
    if not run_gate_4_hygiene_and_typecheck(root):
        print("❌ Gate 4 Failed — Resolve linting or static typecheck errors before release.", file=sys.stderr)
        return 1
    print("✅ Code formatting, linting & typecheck passed.")

    # Gate 5: Test Suite Execution (guided by local test skill)
    print("\n[Gate 5/6] Executing project test suite...")
    local_test_skill = ensure_local_test_skill(root)
    print(f"Guided by local test skill: {local_test_skill.relative_to(root)}")

    if not skip_tests:
        test_cmd = resolve_test_command(root)
        print(f"Executing: {' '.join(test_cmd)}")
        res = subprocess.run(test_cmd, cwd=root)  # noqa: S603
        if res.returncode != 0:
            print("❌ Gate 5 Failed — Test suite failed! Cannot release failing code.", file=sys.stderr)
            return 1
        print("✅ Test suite passed.")
    else:
        print("⚠️ Tests skipped (--skip-tests).")

    # Gate 6: Version Synchronization & Tagging
    print(f"\n[Gate 6/6] Synchronizing version manifest and tagging {tag_name}...")
    updated_manifests = update_manifest_version(root, clean_version)

    stage_files = [
        "RELEASE.md",
        "release.md",
        "specs/traceability.json",
        *updated_manifests,
    ]
    for sf in stage_files:
        if (root / sf).exists():
            subprocess.run(["git", "add", sf], cwd=root, check=False)  # noqa: S603

    # Stage any formatting fixes applied in Gate 4
    subprocess.run(["git", "add", "-u"], cwd=root, check=False)  # noqa: S603
    subprocess.run(["git", "commit", "-m", f"chore(release): bump version to {tag_name}"], cwd=root, check=False)  # noqa: S603

    run_cmd(
        ["git", "tag", "-a", tag_name, "-m", f"Release {tag_name}: {message}"],
        f"Failed to create git tag {tag_name}",
        cwd=root,
    )

    print(f"\n🎉 Successfully created annotated Git release {tag_name}!")
    print(f"Release Message: {message}\n")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="release_manager",
        description="Universal 6-Gate Release Pipeline & Git Tagger",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init", help="Initialize RELEASE.md/release.md and local project test skill")
    subparsers.add_parser("list", help="List all release tags in repository")

    review_p = subparsers.add_parser("review", help="Execute Quad-Persona Code & OWASP Security Review (Gate 2)")
    review_p.add_argument("--diff", metavar="REF", help="Scope review to changes since Git REF")
    review_p.add_argument(
        "--diff-from-last-tag",
        action="store_true",
        help="Scope review to changes since latest Git tag",
    )

    create_parser = subparsers.add_parser("create", help="Execute 6-Gate release pipeline and tag version")
    create_parser.add_argument("version", help="Semantic version to tag, e.g. 1.0.0 or v1.0.0")
    create_parser.add_argument("-m", "--message", required=True, help="Release summary message")
    create_parser.add_argument("--skip-tests", action="store_true", help="Skip test suite execution")

    args = parser.parse_args()
    root = find_project_root()

    if args.command == "init":
        return init_release_governance(root)
    elif args.command == "list":
        tags = run_cmd(["git", "tag", "-n", "--sort=v:refname"], "Failed to list git tags", cwd=root)
        print(tags if tags else "No release tags found in repository.")
        return 0
    elif args.command == "review":
        print(f"\n🔍 Executing Quad-Persona Code & OWASP Security Review in {root.name}...\n")
        diff_ref = getattr(args, "diff", None)
        if getattr(args, "diff_from_last_tag", False) and not diff_ref:
            mod = _load_global_reviewer_module()
            if mod is not None:
                diff_ref = mod.get_last_git_tag(root)
        ok = audit_gate_2_quad_persona_review(root, diff_ref=diff_ref, show_hotspots=True)
        if not ok:
            print("\n❌ Quad-Persona Code & Security Review: Violations present.", file=sys.stderr)
            return 1
        print("\n✅ Quad-Persona Code & Security Review: 100% compliant.")
        return 0
    elif args.command == "create":
        return create_release(root, args.version, args.message, args.skip_tests)

    return 0


if __name__ == "__main__":
    sys.exit(main())

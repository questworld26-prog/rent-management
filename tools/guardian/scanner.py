"""Forward, reverse, and AST semantic codebase scanner."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path

from tools.guardian.parser import RequirementBlock

SPEC_TAG_REGEX = re.compile(r"\[spec:\s*([A-Z0-9\-]+)\]", re.IGNORECASE)
VERIFIES_TAG_REGEX = re.compile(r"\[verifies:\s*([A-Z0-9\-]+/[A-Z0-9\-\.]+)\]", re.IGNORECASE)
BACKTICK_IDENT_REGEX = re.compile(r"`([a-zA-Z_][a-zA-Z0-9_]*)`")


@dataclass
class CodeLocation:
    file_path: Path
    line_number: int
    symbol_name: str = ""
    tag_content: str = ""


def _rel_path(path: Path, base: Path) -> str:
    try:
        return str(path.resolve().relative_to(base.resolve()))
    except Exception:
        return str(path)


def scan_file_for_tags(file_path: Path, pattern: re.Pattern) -> list[tuple[str, CodeLocation]]:
    """Scan a source or test file for matches of a specific tag regex pattern."""
    results: list[tuple[str, CodeLocation]] = []
    try:
        lines = file_path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return results

    for line_idx, line in enumerate(lines, start=1):
        for match in pattern.finditer(line):
            tag_id = match.group(1).strip().upper()
            loc = CodeLocation(
                file_path=file_path,
                line_number=line_idx,
                tag_content=line.strip(),
            )
            results.append((tag_id, loc))
    return results


def _get_attached_tags(
    lines: list[str],
    node: ast.AST,
    pattern: re.Pattern,
) -> list[str]:
    """Extract tags from contiguous comment block immediately preceding AST node and docstring."""
    decorators = getattr(node, "decorator_list", [])
    start_line = decorators[0].lineno if decorators else getattr(node, "lineno", 1)
    idx = start_line - 2
    tags: list[str] = []
    while idx >= 0:
        stripped = lines[idx].strip()
        if not stripped:
            idx -= 1
            continue
        if stripped.startswith("#"):
            found = [m.group(1).strip().upper() for m in pattern.finditer(stripped)]
            tags = found + tags
            idx -= 1
        else:
            break

    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        doc = ast.get_docstring(node) or ""
        for m in pattern.finditer(doc):
            t = m.group(1).strip().upper()
            if t not in tags:
                tags.append(t)
    return tags


def _has_tag_before_node(
    lines: list[str],
    node: ast.AST,
    pattern: re.Pattern,
) -> bool:
    """Check if a tag pattern appears in the contiguous comment block above an AST node or inside its docstring."""
    return len(_get_attached_tags(lines, node, pattern)) > 0


def _is_pytest_fixture(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Return True if the function is decorated as a pytest fixture."""
    for dec in node.decorator_list:
        dec_str = ast.unparse(dec) if hasattr(ast, "unparse") else ""
        if "fixture" in dec_str:
            return True
    return False


def _is_vacuous_assert(test_expr: ast.AST) -> bool:
    """Return True if an `assert <test_expr>` is a vacuous mirage assertion."""
    if isinstance(test_expr, ast.Constant):
        return bool(test_expr.value)
    if isinstance(test_expr, ast.Name):
        return True
    if (
        isinstance(test_expr, ast.Call)
        and isinstance(test_expr.func, ast.Name)
        and test_expr.func.id in ("isinstance", "bool", "hasattr")
    ):
        return True
    if isinstance(test_expr, ast.Compare) and len(test_expr.ops) == 1 and len(test_expr.comparators) == 1:
        op = test_expr.ops[0]
        right = test_expr.comparators[0]
        left = test_expr.left
        if isinstance(op, (ast.IsNot, ast.NotEq)) and isinstance(right, ast.Constant) and right.value is None:
            return True
        if (
            isinstance(left, ast.Call)
            and isinstance(left.func, ast.Name)
            and left.func.id == "len"
            and isinstance(right, ast.Constant)
        ):
            if isinstance(op, (ast.Gt, ast.NotEq)) and right.value == 0:
                return True
            if isinstance(op, ast.GtE) and right.value == 1:
                return True
    return False


def _audit_test_assertions(node: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[bool, str]:
    """Verify that a test function contains at least one non-vacuous, deterministic assertion."""
    assert_nodes: list[ast.Assert] = []
    has_strong_helper_assert = False

    for child in ast.walk(node):
        if isinstance(child, ast.Assert):
            assert_nodes.append(child)
        elif isinstance(child, ast.Call):
            func_str = (ast.unparse(child.func) if hasattr(ast, "unparse") else "").lower()
            if any(
                k in func_str
                for k in (
                    "pytest.raises",
                    "pytest.fail",
                    "assert_called",
                    "assert_has_calls",
                    "assertequal",
                    "asserttrue",
                    "assertin",
                )
            ):
                has_strong_helper_assert = True

    if has_strong_helper_assert:
        return True, ""
    if not assert_nodes:
        return False, "contains 0 `assert` statements"

    non_vacuous_count = sum(1 for a in assert_nodes if not _is_vacuous_assert(a.test))
    if non_vacuous_count == 0:
        return (
            False,
            f"contains only vacuous mirage assertions ({len(assert_nodes)} total: e.g. `is not None`, `len(x) > 0`, or bare truthiness)",
        )
    return True, ""


def _collect_ast_identifiers(node: ast.AST) -> set[str]:
    """Collect all symbol names, attribute names, function/class defs, and string tokens inside an AST node."""
    tokens: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            tokens.add(child.name)
        elif isinstance(child, ast.Name):
            tokens.add(child.id)
        elif isinstance(child, ast.Attribute):
            tokens.add(child.attr)
        elif isinstance(child, ast.Import):
            for alias in child.names:
                tokens.update(alias.name.split("."))
                if alias.asname:
                    tokens.add(alias.asname)
        elif isinstance(child, ast.ImportFrom):
            if child.module:
                tokens.update(child.module.split("."))
            for alias in child.names:
                tokens.add(alias.name)
                if alias.asname:
                    tokens.add(alias.asname)
        elif isinstance(child, ast.Constant) and isinstance(child.value, str) and len(child.value) <= 120:
            tokens.update(re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", child.value))
    return tokens


@dataclass
class SemanticAuditData:
    stacked_test_tags: list[str] = field(default_factory=list)
    weak_test_assertions: list[str] = field(default_factory=list)
    cross_link_mismatches: list[str] = field(default_factory=list)
    ac_anchor_mismatches: list[str] = field(default_factory=list)


def _inspect_src_nodes(
    tree: ast.AST,
    lines: list[str],
    rel: str,
    req_bound_symbols: dict[str, set[str]],
    untagged_src_symbols: list[str],
) -> None:
    """Inspect top-level functions and classes in a source module."""
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            node_tags = _get_attached_tags(lines, node, SPEC_TAG_REGEX)
            for r_id in node_tags:
                req_bound_symbols.setdefault(r_id, set()).add(node.name)
            if not node.name.startswith("_") and node.name != "main" and not node_tags:
                untagged_src_symbols.append(f"{rel}:{node.lineno} -> def {node.name}()")
        elif isinstance(node, ast.ClassDef):
            class_tags = _get_attached_tags(lines, node, SPEC_TAG_REGEX)
            for r_id in class_tags:
                req_bound_symbols.setdefault(r_id, set()).add(node.name)
            method_tags_all: list[str] = []
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    m_tags = _get_attached_tags(lines, item, SPEC_TAG_REGEX)
                    method_tags_all.extend(m_tags)
                    for r_id in m_tags:
                        req_bound_symbols.setdefault(r_id, set()).add(node.name)
                        req_bound_symbols.setdefault(r_id, set()).add(item.name)
                    for r_id in class_tags:
                        req_bound_symbols.setdefault(r_id, set()).add(item.name)
            if not node.name.startswith("_") and not class_tags and not method_tags_all:
                untagged_src_symbols.append(f"{rel}:{node.lineno} -> class {node.name}")


def _scan_src_reverse_traceability(
    src_dir: Path,
    base_dir: Path,
) -> tuple[list[str], list[str], dict[str, set[str]], dict[str, set[str]]]:
    """Inspect src/ files and AST nodes for missing spec tags."""
    untagged_files: list[str] = []
    untagged_src_symbols: list[str] = []
    req_bound_symbols: dict[str, set[str]] = {}
    req_src_ast_tokens: dict[str, set[str]] = {}

    if not src_dir.exists():
        return untagged_files, untagged_src_symbols, req_bound_symbols, req_src_ast_tokens

    for py_file in sorted(src_dir.rglob("*.py")):
        if py_file.name == "__init__.py" or any(p.startswith(".") for p in py_file.parts):
            continue
        rel = _rel_path(py_file, base_dir)
        try:
            raw = py_file.read_text(encoding="utf-8")
        except Exception:
            continue
        if not raw.strip():
            continue

        file_tags = [m.upper() for m in SPEC_TAG_REGEX.findall(raw)]
        if not file_tags:
            untagged_files.append(rel)

        lines = raw.splitlines()
        try:
            tree = ast.parse(raw)
        except SyntaxError:
            continue

        file_ast_tokens = _collect_ast_identifiers(tree)
        file_ast_tokens.add(py_file.stem)
        if py_file.parent != src_dir:
            file_ast_tokens.add(py_file.parent.name)

        for r_id in set(file_tags):
            req_src_ast_tokens.setdefault(r_id, set()).update(file_ast_tokens)
            req_bound_symbols.setdefault(r_id, set()).add(py_file.stem)
            if py_file.parent != src_dir:
                req_bound_symbols.setdefault(r_id, set()).add(py_file.parent.name)

        _inspect_src_nodes(tree, lines, rel, req_bound_symbols, untagged_src_symbols)

    return untagged_files, untagged_src_symbols, req_bound_symbols, req_src_ast_tokens


def _collect_test_nodes(
    tree: ast.AST, lines: list[str]
) -> list[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef, list[str]]]:
    """Extract test functions and their attached tags."""
    test_nodes: list[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef, list[str]]] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
            if not _is_pytest_fixture(node):
                test_nodes.append((node.name, node, _get_attached_tags(lines, node, VERIFIES_TAG_REGEX)))
        elif isinstance(node, ast.ClassDef):
            class_tags = _get_attached_tags(lines, node, VERIFIES_TAG_REGEX)
            for item in node.body:
                if (
                    isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and item.name.startswith("test_")
                    and not _is_pytest_fixture(item)
                ):
                    item_tags = _get_attached_tags(lines, item, VERIFIES_TAG_REGEX) or class_tags
                    test_nodes.append((f"{node.name}.{item.name}", item, item_tags))
    return test_nodes


def _inspect_test_file(
    test_file: Path,
    base_dir: Path,
    req_bound_symbols: dict[str, set[str]],
    untagged_tests: list[str],
    semantic: SemanticAuditData,
    ac_test_ast_tokens: dict[str, set[str]],
) -> None:
    """Inspect a single test file for Layer 1-3 semantic checks."""
    rel = _rel_path(test_file, base_dir)
    try:
        raw = test_file.read_text(encoding="utf-8")
        tree = ast.parse(raw)
    except Exception:
        return
    lines = raw.splitlines()

    module_level_tokens: set[str] = set()
    fixture_tokens: dict[str, set[str]] = {}
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.Assign)):
            module_level_tokens.update(_collect_ast_identifiers(node))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _is_pytest_fixture(node):
            fixture_tokens[node.name] = _collect_ast_identifiers(node)

    for display_name, t_node, tags in _collect_test_nodes(tree, lines):
        if not tags:
            untagged_tests.append(f"{rel}:{t_node.lineno} -> {display_name}()")
            continue
        if len(tags) > 1:
            semantic.stacked_test_tags.append(
                f"{rel}:{t_node.lineno} -> {display_name}() stacks {len(tags)} tags {tags} (strictly 1 AC per test function allowed)"
            )
        assert_ok, assert_reason = _audit_test_assertions(t_node)
        if not assert_ok:
            semantic.weak_test_assertions.append(f"{rel}:{t_node.lineno} -> {display_name}() {assert_reason}")

        fn_tokens = _collect_ast_identifiers(t_node) | module_level_tokens
        for arg in t_node.args.args:
            if arg.arg in fixture_tokens:
                fn_tokens.update(fixture_tokens[arg.arg])

        for ac_key in tags:
            ac_test_ast_tokens.setdefault(ac_key, set()).update(fn_tokens)
            req_id = ac_key.split("/", 1)[0]
            bound_syms = req_bound_symbols.get(req_id, set())
            if bound_syms and not (fn_tokens & bound_syms):
                sample_syms = sorted(bound_syms)[:5]
                semantic.cross_link_mismatches.append(
                    f"{rel}:{t_node.lineno} -> {display_name}() tags `{ac_key}`, but never references any symbol/module bound to `{req_id}` (expected one of {sample_syms})"
                )


def _scan_tests_semantic_traceability(
    tests_dir: Path,
    base_dir: Path,
    req_bound_symbols: dict[str, set[str]],
) -> tuple[list[str], SemanticAuditData, dict[str, set[str]]]:
    """Inspect tests/ for Layer 1-3 semantic compliance."""
    untagged_tests: list[str] = []
    semantic = SemanticAuditData()
    ac_test_ast_tokens: dict[str, set[str]] = {}

    if not tests_dir.exists():
        return untagged_tests, semantic, ac_test_ast_tokens

    for test_file in sorted(tests_dir.rglob("test_*.py")):
        if any(p.startswith(".") for p in test_file.parts):
            continue
        _inspect_test_file(test_file, base_dir, req_bound_symbols, untagged_tests, semantic, ac_test_ast_tokens)

    return untagged_tests, semantic, ac_test_ast_tokens


def _verify_ac_backtick_anchors(
    requirements: list[RequirementBlock],
    req_src_ast_tokens: dict[str, set[str]],
    ac_test_ast_tokens: dict[str, set[str]],
    semantic: SemanticAuditData,
) -> None:
    """Verify Layer 4 backtick identifier matching."""
    for req in requirements:
        if req.is_planned:
            continue
        src_tokens = req_src_ast_tokens.get(req.req_id, set())
        for ac_id in req.acceptance_criteria:
            ac_upper = ac_id.upper()
            full_key = f"{req.req_id}/{ac_upper}"
            ac_text = req.ac_texts.get(ac_upper, "")
            backtick_idents = BACKTICK_IDENT_REGEX.findall(ac_text)
            if not backtick_idents:
                continue
            combined_tokens = src_tokens | ac_test_ast_tokens.get(full_key, set())
            for ident in backtick_idents:
                if ident in ("True", "False", "None") or len(ident) < 3:
                    continue
                if ident not in combined_tokens:
                    semantic.ac_anchor_mismatches.append(
                        f"`{full_key}` specifies identifier `{ident}` in spec text, but `{ident}` was not found in the AST of `{req.req_id}` code or `{ac_id}` tests"
                    )


def scan_reverse_and_semantic_traceability(
    requirements: list[RequirementBlock],
    src_dir: Path,
    tests_dir: Path,
    base_dir: Path,
) -> tuple[list[str], list[str], list[str], SemanticAuditData]:
    """Scan src/ and tests/ for reverse traceability and 4 semantic layers."""
    untagged_files, untagged_src_symbols, req_bound_symbols, req_src_ast_tokens = _scan_src_reverse_traceability(
        src_dir, base_dir
    )
    untagged_tests, semantic, ac_test_ast_tokens = _scan_tests_semantic_traceability(
        tests_dir, base_dir, req_bound_symbols
    )
    _verify_ac_backtick_anchors(requirements, req_src_ast_tokens, ac_test_ast_tokens, semantic)
    return untagged_files, untagged_src_symbols, untagged_tests, semantic


def scan_codebase(
    src_dir: Path, tests_dir: Path
) -> tuple[dict[str, list[CodeLocation]], dict[str, list[CodeLocation]]]:
    """Scan src/ for [spec: REQ] and tests/ for [verifies: REQ/AC]."""
    implementations: dict[str, list[CodeLocation]] = {}
    verifications: dict[str, list[CodeLocation]] = {}

    extensions = ("*.py", "*.ts", "*.tsx", "*.js", "*.jsx", "*.go", "*.rs", "*.java")

    if src_dir.exists():
        for ext in extensions:
            for source_file in sorted(src_dir.rglob(ext)):
                for req_id, loc in scan_file_for_tags(source_file, SPEC_TAG_REGEX):
                    implementations.setdefault(req_id, []).append(loc)

    if tests_dir.exists():
        for ext in extensions:
            for test_file in sorted(tests_dir.rglob(ext)):
                for ac_key, loc in scan_file_for_tags(test_file, VERIFIES_TAG_REGEX):
                    verifications.setdefault(ac_key, []).append(loc)

    return implementations, verifications

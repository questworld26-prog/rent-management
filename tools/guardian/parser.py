"""EARS Markdown specification parser and hasher with [PLANNED] roadmap lifecycle support."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

REQ_HEADING_REGEX = re.compile(
    r"^##\s+([A-Z0-9\-]+):\s+(.+?)(?:\s+\[(PLANNED)\])?\s*$",
    re.MULTILINE | re.IGNORECASE,
)
AC_REGEX = re.compile(r"^-\s+(AC-[A-Z0-9\-\.]+):\s*(.+)$", re.MULTILINE)
STATUS_PLANNED_REGEX = re.compile(r"^(?:Status|State):\s*\[?PLANNED\]?\s*$", re.MULTILINE | re.IGNORECASE)


@dataclass
class RequirementBlock:
    req_id: str
    title: str
    spec_path: Path
    statement: str
    is_planned: bool = False
    acceptance_criteria: list[str] = field(default_factory=list)
    ac_texts: dict[str, str] = field(default_factory=dict)
    raw_block: str = ""
    normalized_block: str = ""
    sha256: str = ""


def normalize_block(text: str) -> str:
    """Normalize requirement block to prevent false-positive hash drift from whitespace."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.strip() for line in text.split("\n")]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def hash_text(text: str) -> str:
    """Compute SHA-256 hash of normalized text string."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def parse_spec_file(file_path: Path) -> list[RequirementBlock]:
    """Parse a single EARS markdown spec file into structured RequirementBlocks."""
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception:
        return []

    matches = list(REQ_HEADING_REGEX.finditer(content))
    if not matches:
        return []

    requirements: list[RequirementBlock] = []

    for i, match in enumerate(matches):
        req_id = match.group(1).strip().upper()
        title = match.group(2).strip()
        heading_planned = bool(match.group(3))
        start_idx = match.start()
        end_idx = matches[i + 1].start() if i + 1 < len(matches) else len(content)

        raw_block = content[start_idx:end_idx]
        normalized = normalize_block(raw_block)
        block_hash = hash_text(normalized)

        ac_matches = AC_REGEX.findall(raw_block)
        criteria_ids = [ac[0].strip() for ac in ac_matches]
        ac_texts = {ac[0].strip().upper(): ac[1].strip() for ac in ac_matches}

        parts = re.split(r"Acceptance Criteria:", raw_block, flags=re.IGNORECASE)
        statement_text = ""
        body_planned = False
        if parts:
            heading_line = match.group(0)
            before_ac = parts[0].replace(heading_line, "", 1)
            body_planned = bool(STATUS_PLANNED_REGEX.search(before_ac))
            statement_text = normalize_block(before_ac)

        block = RequirementBlock(
            req_id=req_id,
            title=title,
            spec_path=file_path,
            statement=statement_text,
            is_planned=heading_planned or body_planned,
            acceptance_criteria=criteria_ids,
            ac_texts=ac_texts,
            raw_block=raw_block,
            normalized_block=normalized,
            sha256=block_hash,
        )
        requirements.append(block)

    return requirements


def parse_specs_directory(specs_dir: Path) -> list[RequirementBlock]:
    """Recursively parse all .md spec files in specs directory."""
    all_reqs: list[RequirementBlock] = []
    if not specs_dir.exists():
        return all_reqs

    for md_file in sorted(specs_dir.rglob("*.md")):
        if md_file.name.lower() in ("readme.md", "architecture.md"):
            continue
        all_reqs.extend(parse_spec_file(md_file))
    return all_reqs

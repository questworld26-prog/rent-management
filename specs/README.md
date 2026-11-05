# Specifications Directory (`specs/`)

This directory houses all formal system requirements written in **Easy Approach to Requirements Syntax (EARS)**.

## EARS Format Syntax Reference
Every requirement must follow one of the 5 standard EARS patterns:
1. **Ubiquitous**: The system shall [system response].
2. **Event-driven**: When [trigger], the system shall [system response].
3. **State-driven**: While [specific system state], the system shall [system response].
4. **Unwanted behaviour**: If [error condition / edge case], then the system shall [system response].
5. **Optional feature**: Where [feature flag or setting enabled], the system shall [system response].

## Requirement Structure
```markdown
## [MODULE]-[NUMBER]: [Descriptive Title]

[EARS Statement]

Acceptance Criteria:
- AC-[MODULE]-[NUMBER].1: [Criterion 1]
- AC-[MODULE]-[NUMBER].2: [Criterion 2]
```

## Traceability & Hashing Rules
- **Normalized Block Hashing**: Each requirement block from `## [REQ-ID]:` to the next `##` or EOF is stripped of trailing whitespace, normalized to `\n` line endings, and fingerprinted via SHA-256.
- **Code Binding**: Source code in `src/` tags `# [spec: REQ-ID]`.
- **Test Binding**: Pytest test cases tag `# [verifies: REQ-ID/AC-ID]`.
- **Traceability Manifest**: `specs/traceability.json` is auto-compiled and verified by the Spec Guardian tool (`tools/guardian/`).

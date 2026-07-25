"""Contract tests for Maestro verdict v2 schema.

Validates that the vendored schema is well-formed and correctly discriminates
v1 (Stage A) from v2 (Stage B) verdict formats.
"""

import json
from pathlib import Path

import jsonschema

# Module-level constant for the vendored schema path
VENDORED_SCHEMA_PATH = (
    Path(__file__).parent.parent
    / "contracts"
    / "maestro-verdict-v2"
    / "verdict_v2.json"
)
VENDORED_FROM_PATH = (
    Path(__file__).parent.parent / "contracts" / "maestro-verdict-v2" / "VENDORED_FROM"
)


def load_vendored_schema() -> dict:
    """Load the vendored Maestro verdict v2 schema.

    Returns:
        dict: The JSON Schema as a dictionary.
    """
    with open(VENDORED_SCHEMA_PATH) as f:
        return json.load(f)


def test_vendored_schema_is_valid_jsonschema() -> None:
    """Verify the vendored schema is a valid JSON Schema document."""
    schema = load_vendored_schema()
    # Will raise an exception if schema is invalid
    jsonschema.Draft202012Validator.check_schema(schema)


def test_pin_file_records_expected_commit() -> None:
    """Verify VENDORED_FROM contains the expected commit hash."""
    with open(VENDORED_FROM_PATH) as f:
        content = f.read()

    lines = content.strip().split("\n")
    assert len(lines) == 3, f"Expected 3 lines, got {len(lines)}"

    # Check repo line
    repo_line = lines[0]
    assert repo_line.startswith("repo:"), (
        f"First line should start with 'repo:', got {repo_line}"
    )

    # Check commit line contains expected commit hash
    commit_line = lines[1]
    assert "346222e3b" in commit_line, f"Commit hash not found in {commit_line}"

    # Check note line: five-var echo env addendum, per merged Maestro PR #106
    note_line = lines[2]
    assert note_line.startswith("note:"), (
        f"Third line should start with 'note:', got {note_line}"
    )
    assert "#106" in note_line, f"PR #106 reference not found in {note_line}"


def test_stage_a_v1_document_does_not_validate() -> None:
    """Verify that a v1 Stage A verdict fails validation against v2 schema.

    This ensures the schema actually discriminates between generations.
    """
    schema = load_vendored_schema()
    validator = jsonschema.Draft202012Validator(schema)

    # Load the first v1 verdict file (sorted deterministically)
    verdicts_dir = Path(__file__).parent.parent / "verdicts" / "sqlite-wal"
    v1_files = sorted(verdicts_dir.glob("**/attempt-*.json"))

    assert v1_files, "No v1 verdict files found in verdicts/sqlite-wal/"

    v1_file = v1_files[0]
    with open(v1_file) as f:
        v1_document = json.load(f)

    # The v1 document should NOT validate against v2 schema
    errors = list(validator.iter_errors(v1_document))
    assert errors, (
        f"v1 verdict at {v1_file} unexpectedly validates against v2 schema. "
        "This means the schema doesn't properly discriminate generations. "
        f"Document: {json.dumps(v1_document, indent=2)[:500]}..."
    )


def test_minimal_valid_v2_document_validates() -> None:
    """Verify a minimal valid v2 document passes schema validation."""
    schema = load_vendored_schema()
    validator = jsonschema.Draft202012Validator(schema)

    # Construct minimal v2 document from required fields in schema
    minimal_v2 = {
        "schema_version": 2,
        "identity": {
            "verification_run_id": "run-123",
            "verification_attempt": 1,
            "rework_attempt": 0,
            "workstream_id": "ws-abc",
            "artifact": "reports/test/result.md",
            "artifact_sha256": "abc123",
            "criteria_sha256": "def456",
            "profile_sha256": "ghi789",
            "verified_source_commit": "deadbeef",
            "verified_source_tree": "cafebabe",
        },
        "verdict": "PASS",
    }

    # Should not raise any validation errors
    validator.validate(minimal_v2)

"""Where the integration tests find a real sequence.

Sequences live in the repo's own gitignored `data/` folder, so the tests find them without any
environment plumbing. `DRIFTLINE_TEST_SEQUENCE` still wins where it is set, which is what a
machine keeping its sequences somewhere else needs.
"""

import os
from pathlib import Path

import pytest

SEQUENCE_ENV = "DRIFTLINE_TEST_SEQUENCE"
DEFAULT_SEQUENCE = "dataset-room1_512_16"

# backend/src/datasets/_tests/sequences.py -> repo root is five levels up
REPO_ROOT = Path(__file__).resolve().parents[4]
DATA_ROOT = REPO_ROOT / "data"


def sequence_path() -> Path:
    """The real sequence to test against, or skip when there is not one on this machine."""
    raw = os.getenv(SEQUENCE_ENV)
    if raw:
        root = Path(raw)
        if not root.is_dir():
            pytest.skip(f"{SEQUENCE_ENV} does not point at a directory: {root}")
        return root

    root = DATA_ROOT / DEFAULT_SEQUENCE
    if not root.is_dir():
        pytest.skip(
            f"no sequence at {root}. Put one there, or set {SEQUENCE_ENV} to point at one"
        )
    return root

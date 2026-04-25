#!/usr/bin/env python3
"""
Fail-closed real social posting success gate.

Purpose:
    Prevent anyone from claiming X/Reddit/GitHub posting is fully verified unless a
    real E2E run leaves platform permalink/Discussion evidence for every platform.

Main responsibilities:
    - Require an external JSON evidence file with X, Reddit, and GitHub Discussions URLs.
    - Validate permalink shape, trace ID, verification timestamp, and source.
    - Fail by default when no real posting evidence exists.

Not responsible for:
    - Creating posts on X or Reddit.
    - Accepting fixture/example URLs as real success.
    - Skipping the real verification requirement.
"""

import os
from pathlib import Path

from Agent.posting_workflows.verification_gate import validate_real_success_evidence_file


DEFAULT_EVIDENCE_PATH = Path("Agent/data/real_posting_success_evidence.json")


def test_real_social_posting_success_evidence_exists_and_is_valid():
    evidence_path = Path(os.environ.get("REAL_POSTING_EVIDENCE_PATH", DEFAULT_EVIDENCE_PATH))

    report = validate_real_success_evidence_file(evidence_path)

    assert report["valid"] is True, report

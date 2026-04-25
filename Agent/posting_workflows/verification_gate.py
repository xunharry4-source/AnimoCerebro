"""
Real posting success verification gate.

Purpose:
    Centralize the checks that separate a real, platform-verifiable post from a
    synthetic or test-only success state.

Main responsibilities:
    - Validate X, Reddit, and GitHub Discussions post URLs with platform-specific URL shapes.
    - Require submit and verification node evidence before success is recorded.
    - Validate external real-post evidence files used by fail-closed E2E tests.

Not responsible for:
    - Publishing posts to social platforms.
    - Calling browsers, OCR, or LLM providers.
    - Treating fixture data as real platform evidence.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional
from urllib.parse import urlparse

from Agent.posting_workflows.errors import PostingWorkflowError


X_SUCCESS_NODES = ("x_write_post", "x_verify_success")
REDDIT_SUCCESS_NODES = ("reddit_submit_post", "reddit_analyze_submission_popup", "reddit_verify_success")
GITHUB_SUCCESS_NODES = ("github_submit_discussion", "github_verify_success")
URL_BOUND_EVIDENCE_NODES = {
    "x_verify_success",
    "reddit_submit_post",
    "reddit_analyze_submission_popup",
    "reddit_verify_success",
    "github_submit_discussion",
    "github_verify_success",
}
REAL_SUCCESS_PLATFORMS = ("x", "reddit", "github")


def is_platform_post_url(platform: str, post_url: Optional[str], *, subreddit: Optional[str] = None) -> bool:
    """Return whether a URL has the expected post permalink shape for a platform."""
    if not post_url or not isinstance(post_url, str):
        return False
    parsed = urlparse(post_url.strip())
    host = parsed.netloc.lower().removeprefix("www.")
    path_parts = [part for part in parsed.path.split("/") if part]
    if parsed.scheme not in {"http", "https"}:
        return False
    if platform == "x":
        return _is_x_post_url(host, path_parts)
    if platform == "reddit":
        return _is_reddit_post_url(host, path_parts, subreddit=subreddit)
    if platform == "github":
        return _is_github_discussion_url(host, path_parts)
    return False


def require_verified_post_success(
    platform: str,
    state: Any,
    *,
    node: str,
    required_nodes: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    """Fail closed unless a success state has platform URL and node evidence."""
    if getattr(state, "status", None) != "success":
        raise PostingWorkflowError(
            "Only success states can be recorded as verified posts",
            node=node,
            code="success_state_required",
            details={"status": getattr(state, "status", None)},
        )
    post_url = getattr(state, "post_url", None)
    subreddit = getattr(state, "subreddit", None)
    if not is_platform_post_url(platform, post_url, subreddit=subreddit):
        raise PostingWorkflowError(
            "Success state is missing a verifiable platform post URL",
            node=node,
            code="verified_post_url_missing",
            details={"platform": platform, "post_url": post_url, "subreddit": subreddit},
        )
    attempts = int(getattr(state, "attempts", 0) or 0)
    if attempts < 1:
        raise PostingWorkflowError(
            "Success state has no recorded submit attempt",
            node=node,
            code="submit_attempt_missing",
            details={"platform": platform, "post_url": post_url},
        )
    expected_nodes = tuple(required_nodes or _success_nodes_for_platform(platform))
    missing_nodes = [
        evidence_node
        for evidence_node in expected_nodes
        if not _has_success_evidence(
            getattr(state, "evidence", []),
            evidence_node,
            post_url,
            require_url=evidence_node in URL_BOUND_EVIDENCE_NODES,
        )
    ]
    if missing_nodes:
        raise PostingWorkflowError(
            "Success state is missing required platform verification evidence",
            node=node,
            code="success_evidence_missing",
            details={
                "platform": platform,
                "post_url": post_url,
                "missing_nodes": missing_nodes,
                "required_nodes": list(expected_nodes),
            },
        )
    return {
        "platform": platform,
        "post_url": post_url,
        "attempts": attempts,
        "verification_nodes": list(expected_nodes),
        "subreddit": subreddit,
    }


def validate_real_success_evidence_file(path: Path) -> Dict[str, Any]:
    """Validate the external evidence file used by the real posting gate test."""
    evidence_path = Path(path)
    if not evidence_path.exists():
        return {
            "valid": False,
            "code": "real_success_evidence_file_missing",
            "message": f"Missing real posting evidence file: {evidence_path}",
        }
    try:
        payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise PostingWorkflowError(
            f"Could not read real posting evidence file: {exc}",
            node="real_posting_success_gate",
            code="real_success_evidence_read_failed",
            details={"path": str(evidence_path)},
        ) from exc
    return validate_real_success_evidence_payload(payload)


def validate_real_success_evidence_payload(payload: Any) -> Dict[str, Any]:
    """Validate persisted proof that every configured platform produced real post URLs."""
    if not isinstance(payload, Mapping):
        return _invalid("real_success_evidence_invalid_format", "Evidence payload must be a JSON object")
    failures: List[Dict[str, Any]] = []
    for platform in REAL_SUCCESS_PLATFORMS:
        entry = payload.get(platform)
        if not isinstance(entry, Mapping):
            failures.append({"platform": platform, "code": "platform_evidence_missing"})
            continue
        post_url = entry.get("post_url")
        subreddit = str(entry.get("subreddit") or "") or None
        if not is_platform_post_url(platform, post_url, subreddit=subreddit):
            failures.append(
                {
                    "platform": platform,
                    "code": "platform_post_url_invalid",
                    "post_url": post_url,
                    "subreddit": subreddit,
                }
            )
        if not entry.get("trace_id"):
            failures.append({"platform": platform, "code": "trace_id_missing"})
        if not entry.get("verified_at"):
            failures.append({"platform": platform, "code": "verified_at_missing"})
        if not entry.get("verification_source"):
            failures.append({"platform": platform, "code": "verification_source_missing"})
    if failures:
        return {
            "valid": False,
            "code": "real_success_evidence_incomplete",
            "message": "Real posting success evidence is missing or invalid",
            "failures": failures,
        }
    return {"valid": True, "code": "real_success_evidence_valid", "message": "Real posting evidence accepted"}


def _is_x_post_url(host: str, path_parts: List[str]) -> bool:
    if host not in {"x.com", "mobile.x.com", "twitter.com", "mobile.twitter.com"}:
        return False
    if len(path_parts) < 3:
        return False
    status_index = _index_of(path_parts, "status")
    if status_index is None or status_index + 1 >= len(path_parts):
        return False
    return path_parts[status_index + 1].isdigit()


def _is_reddit_post_url(host: str, path_parts: List[str], *, subreddit: Optional[str]) -> bool:
    if host == "redd.it":
        return len(path_parts) >= 1 and len(path_parts[0]) >= 4
    if host not in {"reddit.com", "old.reddit.com", "new.reddit.com"}:
        return False
    if len(path_parts) < 5:
        return False
    if path_parts[0].lower() != "r" or path_parts[2].lower() != "comments":
        return False
    if subreddit and path_parts[1].lower() != subreddit.lower().removeprefix("r/"):
        return False
    return len(path_parts[3]) >= 4


def _is_github_discussion_url(host: str, path_parts: List[str]) -> bool:
    if host != "github.com":
        return False
    if len(path_parts) < 4:
        return False
    if path_parts[2].lower() != "discussions":
        return False
    return bool(path_parts[0] and path_parts[1] and path_parts[3].isdigit())


def _success_nodes_for_platform(platform: str) -> Iterable[str]:
    if platform == "x":
        return X_SUCCESS_NODES
    if platform == "reddit":
        return REDDIT_SUCCESS_NODES
    if platform == "github":
        return GITHUB_SUCCESS_NODES
    raise PostingWorkflowError(
        "Unsupported platform for verified success gate",
        node="verification_gate",
        code="unsupported_platform",
        details={"platform": platform},
    )


def _has_success_evidence(
    evidence_items: Iterable[Any],
    node: str,
    post_url: str,
    *,
    require_url: bool,
) -> bool:
    for evidence in evidence_items:
        if getattr(evidence, "node", None) != node or getattr(evidence, "success", None) is not True:
            continue
        if not require_url:
            return True
        data = getattr(evidence, "data", {}) or {}
        if _data_contains_url(data, post_url):
            return True
    return False


def _data_contains_url(data: Any, post_url: str) -> bool:
    if isinstance(data, Mapping):
        return any(_data_contains_url(value, post_url) for value in data.values())
    if isinstance(data, list):
        return any(_data_contains_url(value, post_url) for value in data)
    return isinstance(data, str) and data == post_url


def _index_of(values: List[str], needle: str) -> Optional[int]:
    try:
        return values.index(needle)
    except ValueError:
        return None


def _invalid(code: str, message: str) -> Dict[str, Any]:
    return {"valid": False, "code": code, "message": message}

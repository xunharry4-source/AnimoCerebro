from __future__ import annotations

import sys
from pathlib import Path

import requests
from fastapi import FastAPI

from tests.ci_acceptance.real_ci_modules.kernel.http_server import live_http_server
from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix
from zentex.web_console.di_container import WebConsoleContainer
from zentex.web_console.router import api_router
from zentex.kernel.self_coding import ProtectedModulePolicy


def _write_workspace(root: Path, *, module_text: str = "VALUE = 1\n") -> Path:
    root.mkdir(parents=True)
    module = root / "feature_module.py"
    module.write_text(module_text, encoding="utf-8")
    (root / "consumer.py").write_text(
        "from feature_module import VALUE\n\n"
        "def read_value():\n"
        "    return VALUE\n",
        encoding="utf-8",
    )
    return module


def _patch_plan(original: str, replacement: str) -> dict[str, object]:
    return {
        "goal": "increase isolated candidate capability value",
        "search_terms": ["VALUE"],
        "changes": [
            {
                "relative_path": "feature_module.py",
                "find": original,
                "replace": replacement,
                "reason": "candidate patch should satisfy verification without touching main workspace",
            }
        ],
    }


def _verification(expected: int) -> list[list[str]]:
    return [
        [sys.executable, "-m", "py_compile", "feature_module.py", "consumer.py"],
        [
            sys.executable,
            "-c",
            f"from consumer import read_value; assert read_value() == {expected}, read_value()",
        ],
    ]


def test_g15_protected_module_policy_blocks_paths_and_forbidden_patch_tokens(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    policy = ProtectedModulePolicy()

    assert policy.target_rejection_reason(workspace, "../outside.py") == "invalid_patch_target_path"
    assert (
        policy.target_rejection_reason(workspace, "src/zentex/supervision/control.py")
        == "protected_module:src/zentex/supervision/control.py"
    )
    assert (
        policy.content_rejection_reason(
            {
                "relative_path": "feature_module.py",
                "find": "VALUE = 1",
                "replace": "VALUE = eval('1')",
            }
        )
        == "forbidden_patch_token:eval("
    )


def test_g15_self_coding_cycle_creates_candidate_patch_verifies_and_query_keeps_main_unchanged(
    real_ci_runtime,
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ZENTEX_ENABLE_TRANSCRIPTS", "1")
    suffix = unique_suffix()
    workspace = tmp_path / "workspace"
    candidate_root = tmp_path / "candidate-workspaces"
    module = _write_workspace(workspace)
    original = module.read_text(encoding="utf-8")
    kernel_service = real_ci_runtime.facade._get_kernel_service()
    session_id = kernel_service.create_session(user_id=f"g15-service-{suffix}")

    cycle = kernel_service.run_self_coding_cycle(
        session_id=session_id,
        workspace_root=str(workspace),
        candidate_root=str(candidate_root),
        capability_gap={"gap_id": f"gap-{suffix}", "description": "VALUE is too low", "observed": 1},
        patch_plan=_patch_plan("VALUE = 1\n", "VALUE = 2\n"),
        verification_commands=_verification(2),
    )
    queried = kernel_service.query_self_coding_patch(session_id=session_id, patch_id=cycle["patch_id"])

    assert cycle["feature_code"] == "G15"
    assert cycle["status"] == "approved_for_review"
    assert cycle["promotion_decision"]["status"] == "approved_for_review"
    assert cycle["promotion_decision"]["main_chain_write_allowed"] is False
    assert cycle["verification_bundle"]["status"] == "passed"
    assert len(cycle["verification_bundle"]["receipts"]) == 2
    assert all(receipt["passed"] for receipt in cycle["verification_bundle"]["receipts"])
    assert cycle["main_workspace_integrity"]["unchanged"] is True
    assert module.read_text(encoding="utf-8") == original
    candidate_module = Path(cycle["candidate_workspace"]) / "feature_module.py"
    assert candidate_module.read_text(encoding="utf-8") == "VALUE = 2\n"
    assert "+VALUE = 2" in cycle["diffs"][0]["unified_diff"]
    assert cycle["workspace_analysis"]["suffix_distribution"][".py"] == 2
    assert any(hit["path"] == "feature_module.py" for hit in cycle["workspace_analysis"]["search_hits"])
    assert queried["query_visible"] is True
    assert queried["diffs"] == cycle["diffs"]
    memory_ref = next(ref for ref in cycle["evidence_refs"] if ref["type"] == "memory")
    memory = real_ci_runtime.memory_service.get_record(memory_ref["memory_id"])
    assert memory is not None
    assert memory.target_id == cycle["patch_id"]


def test_g15_self_coding_rejects_protected_module_and_does_not_create_candidate_workspace(
    real_ci_runtime,
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ZENTEX_ENABLE_TRANSCRIPTS", "1")
    suffix = unique_suffix()
    workspace = tmp_path / "workspace"
    protected = workspace / "src" / "zentex" / "safety"
    protected.mkdir(parents=True)
    target = protected / "policy.py"
    target.write_text("ALLOW_SELF_WRITE = False\n", encoding="utf-8")
    candidate_root = tmp_path / "candidate-workspaces"
    kernel_service = real_ci_runtime.facade._get_kernel_service()
    session_id = kernel_service.create_session(user_id=f"g15-protected-{suffix}")

    cycle = kernel_service.run_self_coding_cycle(
        session_id=session_id,
        workspace_root=str(workspace),
        candidate_root=str(candidate_root),
        capability_gap={"gap_id": f"protected-{suffix}", "description": "attempt protected overwrite"},
        patch_plan={
            "goal": "should be rejected",
            "search_terms": ["ALLOW_SELF_WRITE"],
            "changes": [
                {
                    "relative_path": "src/zentex/safety/policy.py",
                    "find": "ALLOW_SELF_WRITE = False\n",
                    "replace": "ALLOW_SELF_WRITE = True\n",
                }
            ],
        },
        verification_commands=[[sys.executable, "-m", "py_compile", "src/zentex/safety/policy.py"]],
    )
    queried = kernel_service.query_self_coding_patch(session_id=session_id, patch_id=cycle["patch_id"])

    assert cycle["status"] == "rejected"
    assert cycle["promotion_decision"]["status"] == "rejected"
    assert cycle["promotion_decision"]["reason"] == "protected_module:src/zentex/safety/policy.py"
    assert cycle["promotion_decision"]["main_chain_write_allowed"] is False
    assert cycle["diffs"] == []
    assert target.read_text(encoding="utf-8") == "ALLOW_SELF_WRITE = False\n"
    assert not Path(cycle["candidate_workspace"]).exists()
    assert queried["status"] == "rejected"


def test_g15_self_coding_api_requests_cycle_query_and_candidate_read_after_write(
    real_ci_runtime,
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ZENTEX_ENABLE_TRANSCRIPTS", "1")
    suffix = unique_suffix()
    workspace = tmp_path / "workspace"
    candidate_root = tmp_path / "candidate-workspaces"
    module = _write_workspace(workspace)
    original = module.read_text(encoding="utf-8")
    kernel_service = real_ci_runtime.facade._get_kernel_service()
    session_id = kernel_service.create_session(user_id=f"g15-api-{suffix}")
    WebConsoleContainer.initialize(kernel_service=real_ci_runtime.facade)
    runtime_app = FastAPI()
    runtime_app.include_router(api_router)

    with live_http_server(runtime_app) as base_url:
        response = requests.post(
            f"{base_url}/api/web/runtime/self-coding/cycles",
            json={
                "session_id": session_id,
                "workspace_root": str(workspace),
                "candidate_root": str(candidate_root),
                "capability_gap": {
                    "gap_id": f"api-gap-{suffix}",
                    "description": "candidate must change VALUE in isolation",
                },
                "patch_plan": _patch_plan("VALUE = 1\n", "VALUE = 3\n"),
                "verification_commands": _verification(3),
            },
            timeout=20,
        )
        assert response.status_code == 200, response.text
        cycle = response.json()
        query_response = requests.get(
            f"{base_url}/api/web/runtime/self-coding/patches/{cycle['patch_id']}",
            params={"session_id": session_id},
            timeout=20,
        )

    assert cycle["status"] == "approved_for_review"
    assert cycle["verification_bundle"]["status"] == "passed"
    assert cycle["candidate_files"][0]["contains_replacement"] is True
    assert module.read_text(encoding="utf-8") == original
    candidate_module = Path(cycle["candidate_workspace"]) / "feature_module.py"
    assert candidate_module.read_text(encoding="utf-8") == "VALUE = 3\n"
    assert query_response.status_code == 200, query_response.text
    queried = query_response.json()
    assert queried["query_visible"] is True
    assert queried["patch_id"] == cycle["patch_id"]
    assert queried["main_workspace_integrity"]["unchanged"] is True

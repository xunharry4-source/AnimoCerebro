from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from zentex.kernel.state_domain import TranscriptEntry, TranscriptEntryType
from zentex.safety.sanity_auditor import SanityAuditor


UTC = timezone.utc
PROTECTED_PATH_PARTS = (
    "src/zentex/safety",
    "src/zentex/kernel/safety_gate.py",
    "src/zentex/kernel/identity_kernel.py",
    "src/zentex/kernel/service.py",
    "identity",
    "guardrail",
)
ATTACK_SIGNATURES = (
    "disable safety",
    "bypass approval",
    "skip g25",
    "ignore audit",
    "rm -rf",
    "os.system",
    "subprocess.Popen",
    "eval(",
    "exec(",
)


class VerificationReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    command: list[str]
    returncode: int
    stdout: str = ""
    stderr: str = ""
    passed: bool


class EvidenceBundle(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    bundle_id: str
    proposal_id: str
    lint_test_build_receipts: list[VerificationReceipt] = Field(default_factory=list)
    sandbox_status: str
    post_merge_status: str | None = None
    all_required_evidence_present: bool


class CodingCompletionGate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    gate_id: str
    proposal_id: str
    allowed_to_merge: bool
    required_evidence: list[str]
    missing_evidence: list[str]
    reason: str


class VerificationCommandRunner:
    def run(self, cwd: Path, commands: list[list[str]]) -> dict[str, Any]:
        receipts: list[dict[str, Any]] = []
        for command in commands:
            if not command or not all(isinstance(part, str) and part for part in command):
                raise ValueError("sandbox command must be a non-empty list of strings")
            completed = subprocess.run(command, cwd=str(cwd), text=True, capture_output=True, timeout=20, check=False)
            receipt = VerificationReceipt(
                command=command,
                returncode=completed.returncode,
                stdout=completed.stdout[-2000:],
                stderr=completed.stderr[-2000:],
                passed=completed.returncode == 0,
            ).model_dump(mode="json")
            receipts.append(receipt)
            if completed.returncode != 0:
                return {"status": "failed", "receipts": receipts}
        return {"status": "passed", "receipts": receipts}


def submit_self_refactor_proposal(
    kernel: Any,
    *,
    session_id: str,
    workspace_root: str,
    target_path: str,
    bottleneck_evidence: dict[str, Any],
    change_summary: str,
    replacement: dict[str, str],
    sandbox_commands: list[list[str]],
    capability_id: str,
    resource_state: Optional[dict[str, Any]] = None,
    risk_state: Optional[dict[str, Any]] = None,
    context: Optional[dict[str, Any]] = None,
    self_mod_gate_inputs: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    if not session_id:
        raise ValueError("session_id is required")
    if not workspace_root or not target_path:
        raise ValueError("workspace_root and target_path are required")
    if not bottleneck_evidence:
        raise ValueError("bottleneck_evidence is required")
    if not change_summary.strip():
        raise ValueError("change_summary is required")
    if not sandbox_commands:
        raise ValueError("sandbox_commands is required")
    if not capability_id:
        raise ValueError("capability_id is required")
    state = kernel._get_state(session_id)
    if state is None:
        raise ValueError(f"Session state missing for: {session_id}")

    workspace = Path(workspace_root).expanduser().resolve()
    target = Path(target_path).expanduser().resolve()
    if not workspace.exists() or not workspace.is_dir():
        raise ValueError(f"workspace_root must be an existing directory: {workspace}")
    if not target.exists() or not target.is_file():
        raise ValueError(f"target_path must be an existing file: {target}")
    if not _is_relative_to(target, workspace):
        raise ValueError("target_path must be inside workspace_root")

    proposal_id = f"g14-self-refactor-{uuid4().hex}"
    base = _base_record(
        session_id=session_id,
        proposal_id=proposal_id,
        workspace=workspace,
        target=target,
        bottleneck_evidence=bottleneck_evidence,
        change_summary=change_summary,
        replacement=replacement,
        sandbox_commands=sandbox_commands,
        capability_id=capability_id,
    )
    freeze_reason = _freeze_reason(workspace, target, change_summary, replacement, bottleneck_evidence)
    if freeze_reason:
        base.update({"status": "frozen", "freeze_reason": freeze_reason, "merged": False})
        return _finalize(kernel, state, base, "g14_self_refactor_frozen")

    capability_approval = _verify_capability(kernel, capability_id)
    if capability_approval["status"] != "approved":
        base.update({"status": "blocked_capability", "capability_approval": capability_approval, "merged": False})
        return _finalize(kernel, state, base, "g14_self_refactor_blocked")
    base["capability_approval"] = capability_approval
    base["g12_approval"] = capability_approval

    budget_value_decision = _run_budget_value_check(
        kernel,
        session_id=session_id,
        proposal_id=proposal_id,
        resource_state=resource_state or {},
        risk_state=risk_state or {},
        context=context or {},
    )
    base["budget_value_decision"] = budget_value_decision
    base["g13_decision"] = budget_value_decision
    if budget_value_decision["budget_gate"]["status"] != "approved" or budget_value_decision["recommended_goal_id"] != proposal_id:
        base.update({"status": "blocked_budget_value", "merged": False})
        return _finalize(kernel, state, base, "g14_self_refactor_blocked")

    self_mod_report = _run_self_mod_gate(kernel, proposal_id, self_mod_gate_inputs or {})
    base["g25_approval"] = self_mod_report
    if self_mod_report["self_shaping_blocked"]:
        base.update({"status": "blocked_self_mod_gate", "merged": False})
        return _finalize(kernel, state, base, "g14_self_refactor_blocked")

    original = target.read_text(encoding="utf-8")
    new_content = _apply_replacement(original, replacement)
    sandbox = _run_sandbox(workspace, target, new_content, sandbox_commands)
    base["sandbox"] = sandbox
    base["evidence_bundle"] = _evidence_bundle(proposal_id, sandbox=sandbox, post_merge=None).model_dump(mode="json")
    base["coding_completion_gate"] = _completion_gate(proposal_id, base["evidence_bundle"]).model_dump(mode="json")
    if sandbox["status"] != "passed":
        base.update({"status": "rolled_back", "rollback": {"performed": True, "reason": "sandbox_failed"}, "merged": False})
        return _finalize(kernel, state, base, "g14_self_refactor_rolled_back")

    target.write_text(new_content, encoding="utf-8")
    post_merge = _run_commands(workspace, sandbox_commands)
    base["post_merge_verification"] = post_merge
    base["evidence_bundle"] = _evidence_bundle(proposal_id, sandbox=sandbox, post_merge=post_merge).model_dump(mode="json")
    base["coding_completion_gate"] = _completion_gate(proposal_id, base["evidence_bundle"]).model_dump(mode="json")
    if post_merge["status"] != "passed":
        target.write_text(original, encoding="utf-8")
        base.update({"status": "rolled_back", "rollback": {"performed": True, "reason": "post_merge_verification_failed"}, "merged": False})
        return _finalize(kernel, state, base, "g14_self_refactor_rolled_back")
    if not base["coding_completion_gate"]["allowed_to_merge"]:
        target.write_text(original, encoding="utf-8")
        base.update({"status": "blocked_completion_gate", "merged": False})
        return _finalize(kernel, state, base, "g14_self_refactor_blocked")

    observed = target.read_text(encoding="utf-8")
    if observed != new_content:
        target.write_text(original, encoding="utf-8")
        raise RuntimeError("G14 read-after-write verification failed after merge")
    base.update(
        {
            "status": "merged",
            "merged": True,
            "rollback": {"performed": False, "restore_content_sha256": _sha256(original)},
            "read_after_write": {
                "target_path": str(target),
                "content_sha256": _sha256(observed),
                "contains_replacement": replacement["replace"] in observed,
            },
        }
    )
    return _finalize(kernel, state, base, "g14_self_refactor_merged")


def query_self_refactor_proposal(kernel: Any, *, session_id: str, proposal_id: str) -> dict[str, Any]:
    if not session_id or not proposal_id:
        raise ValueError("session_id and proposal_id are required")
    state = kernel._get_state(session_id)
    if state is None:
        raise ValueError(f"Session state missing for: {session_id}")
    proposal = getattr(kernel, "_self_refactor_proposals", {}).get(proposal_id)
    if not proposal or proposal["session_id"] != session_id:
        raise KeyError(f"G14 self-refactor proposal not found: {proposal_id}")
    _append_transcript(state, proposal, "g14_self_refactor_queried")
    return {**proposal, "query_visible": True}


def _base_record(
    *,
    session_id: str,
    proposal_id: str,
    workspace: Path,
    target: Path,
    bottleneck_evidence: dict[str, Any],
    change_summary: str,
    replacement: dict[str, str],
    sandbox_commands: list[list[str]],
    capability_id: str,
) -> dict[str, Any]:
    return {
        "feature_code": "G14",
        "session_id": session_id,
        "proposal_id": proposal_id,
        "proposal": {
            "workspace_root": str(workspace),
            "target_path": str(target),
            "relative_target_path": str(target.relative_to(workspace)),
            "bottleneck_evidence": bottleneck_evidence,
            "change_summary": change_summary,
            "replacement_find_sha256": _sha256(replacement.get("find", "")),
            "replacement_replace_sha256": _sha256(replacement.get("replace", "")),
            "safety_impact": "bounded single-file replacement with protected path and attack signature checks",
            "rollback_strategy": "restore original file content when sandbox or post-merge verification fails",
            "sandbox_commands": sandbox_commands,
            "capability_id": capability_id,
        },
        "status": "created",
        "merged": False,
        "created_at": datetime.now(UTC).isoformat(),
        "evidence_refs": [],
    }


def _freeze_reason(
    workspace: Path,
    target: Path,
    summary: str,
    replacement: dict[str, str],
    evidence: dict[str, Any],
) -> str | None:
    relative = str(target.relative_to(workspace)).replace("\\", "/").lower()
    for part in PROTECTED_PATH_PARTS:
        if part in relative:
            return f"protected_path:{part}"
    combined = " ".join(
        [
            summary,
            replacement.get("find", ""),
            replacement.get("replace", ""),
            json.dumps(evidence, ensure_ascii=False, sort_keys=True),
        ]
    ).lower()
    for signature in ATTACK_SIGNATURES:
        if signature.lower() in combined:
            return f"attack_signature:{signature}"
    return None


def _verify_capability(kernel: Any, capability_id: str) -> dict[str, Any]:
    capability = getattr(kernel, "_capabilities_store", {}).get(capability_id)
    if not capability:
        return {"status": "rejected", "reason": "missing_capability_registration"}
    if capability.get("status") != "active" or capability.get("verification_status") != "real_verified":
        return {"status": "rejected", "reason": "capability_not_real_verified", "capability": capability}
    return {"status": "approved", "reason": "real_verified_capability", "capability": capability}


def _run_budget_value_check(
    kernel: Any,
    *,
    session_id: str,
    proposal_id: str,
    resource_state: dict[str, Any],
    risk_state: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    method = getattr(kernel, "evaluate_value_engine", None)
    if not callable(method):
        raise RuntimeError("G14 requires G13 value engine")
    return method(
        session_id=session_id,
        candidate_goals=[
            {
                "goal_id": proposal_id,
                "title": "apply bounded self-refactor proposal",
                "expected_value": 0.82,
                "urgency": 0.55,
                "risk": 0.25,
                "cost": 0.35,
                "creativity": 0.2,
                "continuity": 0.85,
                "authorized": True,
                "audit_passed": True,
                "rollback_ready": True,
                "rollback_required": True,
            },
            {
                "goal_id": f"{proposal_id}-defer",
                "title": "defer refactor",
                "expected_value": 0.2,
                "urgency": 0.2,
                "risk": 0.05,
                "cost": 0.05,
                "continuity": 0.4,
                "authorized": True,
                "audit_passed": True,
                "rollback_ready": True,
            },
        ],
        resource_state=resource_state or {
            "compute_remaining_ratio": 0.8,
            "token_remaining_ratio": 0.8,
            "time_remaining_ratio": 0.8,
        },
        risk_state=risk_state or {"risk_level": "medium", "entropy": 0.2},
        context={**context, "scenario": context.get("scenario", "cost_guard")},
        requested_capabilities=["G18"],
    )


def _run_self_mod_gate(kernel: Any, proposal_id: str, inputs: dict[str, Any]) -> dict[str, Any]:
    auditor = getattr(kernel, "_self_refactor_sanity_auditor", None)
    if auditor is None:
        auditor = SanityAuditor(brain_scope="g14.self-refactor", drift_threshold=0.25)
        auditor.set_baseline_profile({"curiosity": 0.3, "safety": 0.9, "mission_focus": 0.8})
        setattr(kernel, "_self_refactor_sanity_auditor", auditor)
    checkpoint = auditor.create_checkpoint({"proposal_id": proposal_id, "stage": "pre_merge"})
    report = auditor.audit(
        world_model=inputs.get(
            "world_model",
            {
                "active_goals": [{"id": proposal_id, "name": "bounded self-refactor", "priority": 1}],
                "physical_host_state": {"network": {"status": "connected"}, "memory": {"status": "normal"}},
                "external_signals": [],
            },
        ),
        strategy_graph=inputs.get(
            "strategy_graph",
            {"policies": {"bounded": {"action": "self_modify", "conditions": ["approved", "rollback_ready"]}}, "actions": ["self_modify"], "reasoning_chains": [{"path": ["propose", "sandbox", "merge"]}]},
        ),
        ban_layer=inputs.get("ban_layer", {"banned_actions": []}),
        motivation_state=inputs.get("motivation_state", {"curiosity": 0.3, "safety": 0.9, "mission_focus": 0.8}),
        self_rewrite_history=inputs.get("self_rewrite_history", [{"proposal_id": proposal_id, "stage": "candidate"}]),
    )
    payload = report.model_dump(mode="json")
    payload["checkpoint_id"] = checkpoint.checkpoint_id
    payload["g18_self_shaping_blocked"] = bool(payload.get("self_shaping_blocked"))
    return payload


def _apply_replacement(original: str, replacement: dict[str, str]) -> str:
    find = replacement.get("find")
    replace = replacement.get("replace")
    if not find or replace is None:
        raise ValueError("replacement must contain find and replace")
    if find not in original:
        raise ValueError("replacement find text is not present in target file")
    return original.replace(find, replace, 1)


def _run_sandbox(workspace: Path, target: Path, new_content: str, commands: list[list[str]]) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="zentex-g14-sandbox-") as tmp:
        sandbox_root = Path(tmp) / "workspace"
        shutil.copytree(workspace, sandbox_root)
        sandbox_target = sandbox_root / target.relative_to(workspace)
        sandbox_target.write_text(new_content, encoding="utf-8")
        result = _run_commands(sandbox_root, commands)
        result["sandbox_root_removed"] = not sandbox_root.exists()
        return result


def _run_commands(cwd: Path, commands: list[list[str]]) -> dict[str, Any]:
    return VerificationCommandRunner().run(cwd, commands)


def _evidence_bundle(proposal_id: str, *, sandbox: dict[str, Any], post_merge: dict[str, Any] | None) -> EvidenceBundle:
    receipts = [
        VerificationReceipt.model_validate(item)
        for item in list(sandbox.get("receipts") or []) + list((post_merge or {}).get("receipts") or [])
    ]
    return EvidenceBundle(
        bundle_id=f"evidence-bundle:{uuid4().hex}",
        proposal_id=proposal_id,
        lint_test_build_receipts=receipts,
        sandbox_status=str(sandbox.get("status") or "missing"),
        post_merge_status=str((post_merge or {}).get("status")) if post_merge else None,
        all_required_evidence_present=bool(
            sandbox.get("status") == "passed"
            and post_merge is not None
            and post_merge.get("status") == "passed"
            and receipts
            and all(item.passed for item in receipts)
        ),
    )


def _completion_gate(proposal_id: str, evidence_bundle: dict[str, Any]) -> CodingCompletionGate:
    missing: list[str] = []
    if evidence_bundle.get("sandbox_status") != "passed":
        missing.append("sandbox_verification")
    if evidence_bundle.get("post_merge_status") != "passed":
        missing.append("post_merge_verification")
    if not evidence_bundle.get("lint_test_build_receipts"):
        missing.append("lint_test_build_receipts")
    return CodingCompletionGate(
        gate_id=f"coding-completion-gate:{uuid4().hex}",
        proposal_id=proposal_id,
        allowed_to_merge=not missing and bool(evidence_bundle.get("all_required_evidence_present")),
        required_evidence=["sandbox_verification", "post_merge_verification", "lint_test_build_receipts"],
        missing_evidence=missing,
        reason="all_required_evidence_present" if not missing else "missing_required_evidence",
    )


def _finalize(kernel: Any, state: Any, record: dict[str, Any], entry_type: str) -> dict[str, Any]:
    memory_id = _persist_memory(kernel, record)
    if memory_id:
        record["evidence_refs"].append({"type": "memory", "memory_id": memory_id})
    _cache_record(kernel, "_self_refactor_proposals", record["proposal_id"], record)
    _append_transcript(state, record, entry_type)
    return record


def _persist_memory(kernel: Any, record: dict[str, Any]) -> str | None:
    memory_service = getattr(kernel, "_memory_service", None)
    if memory_service is None or not callable(getattr(memory_service, "remember", None)):
        return None
    memory = memory_service.remember(
        title=f"G14 self-refactor {record['proposal_id']}",
        summary=f"G14 {record['status']} {record['proposal']['relative_target_path']}",
        content=json.dumps(record, ensure_ascii=False, sort_keys=True),
        layer="procedural",
        source="g14_self_refactor",
        trace_id=record["proposal_id"],
        target_id=record["proposal_id"],
        tags=["G14", "self_refactor", record["status"]],
        self_refactor_record=record,
    )
    memory_id = str(getattr(memory, "memory_id", "") or "")
    if memory_id and getattr(memory_service.get_record(memory_id), "memory_id", None) != memory_id:
        raise RuntimeError(f"G14 memory writeback query verification failed: {memory_id}")
    return memory_id or None


def _cache_record(kernel: Any, attr: str, key: str, record: dict[str, Any]) -> None:
    if not hasattr(kernel, attr):
        setattr(kernel, attr, {})
    getattr(kernel, attr)[key] = record


def _append_transcript(state: Any, record: dict[str, Any], entry_type: str) -> None:
    state.transcript.append(
        TranscriptEntry(
            entry_type=TranscriptEntryType.state_change,
            session_id=record["session_id"],
            payload={"feature_code": "G14", "entry_type": entry_type, **record},
        )
    )


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _sha256(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()

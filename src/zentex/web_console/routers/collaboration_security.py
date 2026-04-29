from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from zentex.collaboration.secure_communication import (
    BrainIdentityPublicKey,
    IdentityCreateRequest,
    IdentityLoadRequest,
    KeyRotationRequest,
    KeyRevocationRequest,
    SecureCollaborationRuntime,
    SignMessageRequest,
    SignedBrainMessage,
    SignedKeyRevocationNotice,
    build_default_secure_collaboration_runtime,
)
from zentex.kernel.state_domain.brain_transcript_models import BrainTranscriptEntryType


router = APIRouter(prefix="/collaboration/security", tags=["collaboration-security"])


def _runtime(request: Request) -> SecureCollaborationRuntime:
    runtime = getattr(request.app.state, "secure_collaboration_runtime", None)
    if runtime is None:
        runtime = build_default_secure_collaboration_runtime()
        request.app.state.secure_collaboration_runtime = runtime
    if not isinstance(runtime, SecureCollaborationRuntime):
        raise HTTPException(status_code=503, detail="SecureCollaborationRuntime is unavailable")
    return runtime


def _write_audit(request: Request, event_type: str, trace_id: str, payload: dict[str, Any]) -> None:
    store = getattr(request.app.state, "transcript_store", None)
    if store is None or not callable(getattr(store, "write_entry", None)):
        raise HTTPException(status_code=503, detail="BrainTranscriptStore is unavailable")
    store.write_entry(
        session_id="collaboration-security",
        turn_id=trace_id,
        entry_type=BrainTranscriptEntryType.FLOW_AUDIT,
        source="collaboration.secure_communication",
        trace_id=trace_id,
        payload={
            "event_type": event_type,
            **payload,
        },
    )


@router.post("/identities")
def create_local_identity(payload: IdentityCreateRequest, request: Request) -> dict[str, Any]:
    try:
        identity = _runtime(request).create_identity(payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    result = identity.model_dump(mode="json")
    _write_audit(
        request,
        "brain_identity_created",
        f"identity:{identity.brain_id}:{identity.key_id}",
        {
            "brain_id": identity.brain_id,
            "key_id": identity.key_id,
            "private_key_exported": identity.private_key_exported,
        },
    )
    return result


@router.post("/identities/load")
def load_local_identity(payload: IdentityLoadRequest, request: Request) -> dict[str, Any]:
    try:
        identity = _runtime(request).load_identity(payload)
    except Exception as exc:
        raise HTTPException(status_code=409, detail=str(exc) or exc.__class__.__name__) from exc
    result = identity.model_dump(mode="json")
    _write_audit(
        request,
        "brain_identity_loaded",
        f"identity-load:{identity.brain_id}:{identity.key_id}",
        {
            "brain_id": identity.brain_id,
            "key_id": identity.key_id,
            "private_key_exported": identity.private_key_exported,
        },
    )
    return result


@router.post("/identities/rotate")
def rotate_local_identity(payload: KeyRotationRequest, request: Request) -> dict[str, Any]:
    try:
        result = _runtime(request).rotate_identity(payload)
    except Exception as exc:
        raise HTTPException(status_code=409, detail=str(exc) or exc.__class__.__name__) from exc
    result_payload = result.model_dump(mode="json")
    _write_audit(
        request,
        "brain_identity_rotated",
        f"identity-rotate:{result.brain_id}:{result.new_key_id}",
        {
            "brain_id": result.brain_id,
            "old_key_id": result.old_key_id,
            "new_key_id": result.new_key_id,
            "old_key_status": result.old_key_status,
            "new_key_status": result.new_key_status,
        },
    )
    return result_payload


@router.get("/public-keys")
def list_public_keys(request: Request) -> list[dict[str, Any]]:
    return [item.model_dump(mode="json") for item in _runtime(request).list_public_keys()]


@router.get("/public-keys/{brain_id}")
def get_public_key(brain_id: str, request: Request) -> dict[str, Any]:
    try:
        return _runtime(request).get_public_key(brain_id).model_dump(mode="json")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"public key not found: {brain_id}") from exc


@router.post("/public-keys")
def register_public_key(payload: BrainIdentityPublicKey, request: Request) -> dict[str, Any]:
    try:
        key = _runtime(request).register_public_key(payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _write_audit(
        request,
        "brain_public_key_registered",
        f"public-key:{key.brain_id}:{key.key_id}",
        {"brain_id": key.brain_id, "key_id": key.key_id, "status": key.status},
    )
    return key.model_dump(mode="json")


@router.post("/messages/sign")
def sign_brain_message(payload: SignMessageRequest, request: Request) -> dict[str, Any]:
    try:
        message = _runtime(request).sign_message(payload)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return message.model_dump(mode="json")


@router.post("/messages/verify")
def verify_brain_message(payload: SignedBrainMessage, request: Request) -> dict[str, Any]:
    try:
        result = _runtime(request).verify_message(payload)
    except Exception as exc:
        raise HTTPException(status_code=409, detail=str(exc) or exc.__class__.__name__) from exc
    result_payload = result.model_dump(mode="json")
    _write_audit(
        request,
        "brain_message_verified",
        f"message:{result.message_hash}",
        {
            "message_hash": result.message_hash,
            "sender_brain_id": result.sender_brain_id,
            "sender_key_id": result.sender_key_id,
            "receiver_brain_id": result.receiver_brain_id,
            "message_type": result.message_type,
            "accepted": result.accepted,
        },
    )
    return result_payload


@router.post("/revocations/sign")
def sign_key_revocation(payload: KeyRevocationRequest, request: Request) -> dict[str, Any]:
    try:
        notice = _runtime(request).sign_revocation(payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return notice.model_dump(mode="json")


@router.post("/revocations/apply")
def apply_key_revocation(payload: SignedKeyRevocationNotice, request: Request) -> dict[str, Any]:
    try:
        revoked = _runtime(request).apply_revocation(payload)
    except Exception as exc:
        raise HTTPException(status_code=409, detail=str(exc) or exc.__class__.__name__) from exc
    _write_audit(
        request,
        "brain_key_revoked",
        payload.notice_id,
        {
            "notice_id": payload.notice_id,
            "revoker_brain_id": payload.revoker_brain_id,
            "target_brain_id": payload.target_brain_id,
            "target_key_id": payload.target_key_id,
            "reason": payload.reason,
        },
    )
    return revoked.model_dump(mode="json")


@router.get("/incidents")
def list_security_incidents(request: Request) -> list[dict[str, Any]]:
    return [item.model_dump(mode="json") for item in _runtime(request).list_security_incidents()]

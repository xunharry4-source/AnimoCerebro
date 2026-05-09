from __future__ import annotations

import base64
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


UTC = timezone.utc
SENSITIVE_MESSAGE_TYPES = {
    "DelegatedCommand",
    "ExperienceExchangePacket",
    "ConsensusProposal",
    "StrategyPatchSuggestion",
}


def _now() -> datetime:
    return datetime.now(UTC)


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _unb64(data: str) -> bytes:
    return base64.b64decode(data.encode("ascii"))


def _canonical(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256_hex(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload)).hexdigest()


def _parse_ts(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


class BrainIdentityPublicKey(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    brain_id: str
    key_id: str
    signing_public_key_b64: str
    ecdh_public_key_b64: str
    registered_at: str
    status: Literal["active", "revoked"] = "active"
    tofu_confirmed_by: str


class LocalIdentityCreated(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    brain_id: str
    key_id: str
    signing_public_key_b64: str
    ecdh_public_key_b64: str
    private_key_exported: bool = False


class IdentityCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    brain_id: str = Field(min_length=1)
    tofu_confirmed_by: str = Field(default="local-operator", min_length=1)


class IdentityLoadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    brain_id: str = Field(min_length=1)


class MessageHeader(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sender_brain_id: str
    receiver_brain_id: str = "broadcast"
    sender_key_id: str
    signature: str
    nonce: str
    issued_at: str
    payload_hash: str
    message_type: str
    encrypted: bool = False


class EncryptedEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sender_ecdh_public_key_b64: str
    nonce_b64: str
    ciphertext_b64: str


class SignedBrainMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    header: MessageHeader
    payload: dict[str, Any] | None = None
    encrypted_payload: EncryptedEnvelope | None = None


class SignMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sender_brain_id: str = Field(min_length=1)
    receiver_brain_id: str = "broadcast"
    message_type: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    encrypt_for_receiver: bool = False


class VerifyMessageResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    accepted: bool
    message_hash: str
    sender_brain_id: str
    sender_key_id: str
    receiver_brain_id: str
    message_type: str
    decrypted_payload: dict[str, Any] | None = None


class KeyRevocationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revoker_brain_id: str = Field(min_length=1)
    target_brain_id: str = Field(min_length=1)
    target_key_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class KeyRotationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    brain_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    tofu_confirmed_by: str = Field(default="local-operator", min_length=1)


class KeyRotationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    brain_id: str
    old_key_id: str
    new_key_id: str
    old_key_status: Literal["revoked"]
    new_key_status: Literal["active"]


class SignedKeyRevocationNotice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    notice_id: str
    revoker_brain_id: str
    revoker_key_id: str
    target_brain_id: str
    target_key_id: str
    reason: str
    issued_at: str
    signature: str


class SecurityIncidentEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str
    event_type: str
    source_brain_id: str | None
    source_key_id: str | None
    message_hash: str
    detected_at: str
    action_taken: str
    reason: str
    previous_event_hash: str
    event_hash: str


class ReplayProtection:
    def __init__(self, *, allowed_clock_skew_seconds: int = 30) -> None:
        self.allowed_clock_skew_seconds = allowed_clock_skew_seconds
        self._seen: set[str] = set()

    def check_and_mark(self, *, nonce: str, issued_at: str, sender_key_id: str) -> None:
        timestamp = _parse_ts(issued_at)
        skew = abs((_now() - timestamp).total_seconds())
        if skew > self.allowed_clock_skew_seconds:
            raise ValueError("message timestamp is outside allowed clock skew")
        key = f"{sender_key_id}:{nonce}"
        if key in self._seen:
            raise ValueError("replay nonce was already processed")
        self._seen.add(key)


class _LocalIdentity:
    def __init__(self, brain_id: str, signing_key: Ed25519PrivateKey, ecdh_key: X25519PrivateKey, public: BrainIdentityPublicKey) -> None:
        self.brain_id = brain_id
        self.signing_key = signing_key
        self.ecdh_key = ecdh_key
        self.public = public


class EncryptedIdentityKeyStore:
    def __init__(self, root_path: str | Path, secret: str) -> None:
        if not secret:
            raise ValueError("identity keystore secret is required")
        self.root_path = Path(root_path)
        self.root_path.mkdir(parents=True, exist_ok=True)
        self._key = hashlib.sha256(secret.encode("utf-8")).digest()

    def save(self, identity: _LocalIdentity) -> Path:
        signing_private = identity.signing_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )
        ecdh_private = identity.ecdh_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )
        nonce = os.urandom(12)
        plaintext = _canonical(
            {
                "brain_id": identity.brain_id,
                "key_id": identity.public.key_id,
                "signing_private_key_b64": _b64(signing_private),
                "ecdh_private_key_b64": _b64(ecdh_private),
                "public": identity.public.model_dump(mode="json"),
            }
        )
        ciphertext = AESGCM(self._key).encrypt(nonce, plaintext, identity.brain_id.encode("utf-8"))
        stored = {
            "format": "zentex_identity_keystore_v1",
            "brain_id": identity.brain_id,
            "key_id": identity.public.key_id,
            "nonce_b64": _b64(nonce),
            "ciphertext_b64": _b64(ciphertext),
            "private_key_exported": False,
        }
        path = self._path_for(identity.brain_id)
        path.write_text(json.dumps(stored, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        return path

    def load(self, brain_id: str) -> _LocalIdentity:
        path = self._path_for(brain_id)
        if not path.exists():
            raise KeyError(f"identity keystore record not found: {brain_id}")
        stored = json.loads(path.read_text(encoding="utf-8"))
        plaintext = AESGCM(self._key).decrypt(
            _unb64(stored["nonce_b64"]),
            _unb64(stored["ciphertext_b64"]),
            brain_id.encode("utf-8"),
        )
        payload = json.loads(plaintext.decode("utf-8"))
        if payload.get("brain_id") != brain_id or payload.get("key_id") != stored.get("key_id"):
            raise ValueError("identity keystore metadata mismatch")
        public = BrainIdentityPublicKey.model_validate(payload["public"])
        signing_key = Ed25519PrivateKey.from_private_bytes(_unb64(payload["signing_private_key_b64"]))
        ecdh_key = X25519PrivateKey.from_private_bytes(_unb64(payload["ecdh_private_key_b64"]))
        signing_pub = signing_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        ecdh_pub = ecdh_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        if public.key_id != "brain-key:" + hashlib.sha256(signing_pub).hexdigest()[:32]:
            raise ValueError("identity keystore signing key mismatch")
        if public.ecdh_public_key_b64 != _b64(ecdh_pub):
            raise ValueError("identity keystore ecdh key mismatch")
        return _LocalIdentity(brain_id, signing_key, ecdh_key, public)

    def _path_for(self, brain_id: str) -> Path:
        digest = hashlib.sha256(brain_id.encode("utf-8")).hexdigest()
        return self.root_path / f"{digest}.identity.json"


class SecureCollaborationRuntime:
    def __init__(
        self,
        *,
        allowed_clock_skew_seconds: int = 30,
        keystore_path: str | Path | None = None,
        keystore_secret: str | None = None,
    ) -> None:
        self._locals: dict[str, _LocalIdentity] = {}
        self._registry: dict[str, BrainIdentityPublicKey] = {}
        self._replay = ReplayProtection(allowed_clock_skew_seconds=allowed_clock_skew_seconds)
        self._incidents: list[SecurityIncidentEvent] = []
        self._last_incident_hash = ""
        self._keystore = (
            EncryptedIdentityKeyStore(keystore_path, keystore_secret or os.environ.get("ZENTEX_IDENTITY_KEYSTORE_SECRET", ""))
            if keystore_path is not None
            else None
        )

    def create_identity(self, request: IdentityCreateRequest) -> LocalIdentityCreated:
        existing = self._registry.get(request.brain_id)
        if existing is not None and existing.status == "active":
            raise ValueError("active identity already exists for brain_id; revoke before replacing")
        signing_key = Ed25519PrivateKey.generate()
        ecdh_key = X25519PrivateKey.generate()
        signing_pub = signing_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        ecdh_pub = ecdh_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        key_id = "brain-key:" + hashlib.sha256(signing_pub).hexdigest()[:32]
        public = BrainIdentityPublicKey(
            brain_id=request.brain_id,
            key_id=key_id,
            signing_public_key_b64=_b64(signing_pub),
            ecdh_public_key_b64=_b64(ecdh_pub),
            registered_at=_now().isoformat(),
            status="active",
            tofu_confirmed_by=request.tofu_confirmed_by,
        )
        self._locals[request.brain_id] = _LocalIdentity(request.brain_id, signing_key, ecdh_key, public)
        self._registry[request.brain_id] = public
        if self._keystore is not None:
            self._keystore.save(self._locals[request.brain_id])
        return LocalIdentityCreated(
            brain_id=request.brain_id,
            key_id=key_id,
            signing_public_key_b64=public.signing_public_key_b64,
            ecdh_public_key_b64=public.ecdh_public_key_b64,
        )

    def load_identity(self, request: IdentityLoadRequest) -> LocalIdentityCreated:
        if self._keystore is None:
            raise ValueError("identity keystore is not configured")
        local = self._keystore.load(request.brain_id)
        self._locals[request.brain_id] = local
        self._registry[request.brain_id] = local.public
        return LocalIdentityCreated(
            brain_id=local.brain_id,
            key_id=local.public.key_id,
            signing_public_key_b64=local.public.signing_public_key_b64,
            ecdh_public_key_b64=local.public.ecdh_public_key_b64,
        )

    def register_public_key(self, public: BrainIdentityPublicKey) -> BrainIdentityPublicKey:
        if not public.tofu_confirmed_by.strip():
            raise ValueError("TOFU confirmation is required for first trust establishment")
        expected_key_id = self._derive_key_id_from_public_key(public.signing_public_key_b64)
        if public.key_id != expected_key_id:
            raise ValueError("key_id does not match signing public key")
        existing = self._registry.get(public.brain_id)
        if existing is not None and existing.status == "active" and existing.key_id != public.key_id:
            raise ValueError("active public key already exists for brain_id; revoke before replacing")
        self._registry[public.brain_id] = public
        return public

    def get_public_key(self, brain_id: str) -> BrainIdentityPublicKey:
        public = self._registry.get(brain_id)
        if public is None:
            raise KeyError(brain_id)
        return public

    def list_public_keys(self) -> list[BrainIdentityPublicKey]:
        return list(self._registry.values())

    def sign_message(self, request: SignMessageRequest) -> SignedBrainMessage:
        local = self._require_local(request.sender_brain_id)
        encrypted_payload: EncryptedEnvelope | None = None
        payload: dict[str, Any] | None = request.payload
        payload_hash = _sha256_hex(request.payload)
        encrypted = False
        if request.encrypt_for_receiver:
            if request.message_type not in SENSITIVE_MESSAGE_TYPES:
                raise ValueError("only high-sensitivity message types may be encrypted")
            if request.receiver_brain_id == "broadcast":
                raise ValueError("broadcast messages cannot use point-to-point encryption")
            encrypted_payload = self._encrypt_payload(
                sender=local,
                receiver=self.get_public_key(request.receiver_brain_id),
                payload=request.payload,
                message_type=request.message_type,
            )
            payload = None
            encrypted = True
        header = MessageHeader(
            sender_brain_id=request.sender_brain_id,
            receiver_brain_id=request.receiver_brain_id,
            sender_key_id=local.public.key_id,
            signature="",
            nonce=uuid4().hex,
            issued_at=_now().isoformat(),
            payload_hash=payload_hash,
            message_type=request.message_type,
            encrypted=encrypted,
        )
        signature = local.signing_key.sign(self._signature_body(header))
        signed_header = header.model_copy(update={"signature": _b64(signature)})
        return SignedBrainMessage(header=signed_header, payload=payload, encrypted_payload=encrypted_payload)

    def verify_message(self, message: SignedBrainMessage, *, consume_nonce: bool = True) -> VerifyMessageResult:
        source = message.header.sender_brain_id
        key_id = message.header.sender_key_id
        message_hash = self._message_hash_for_incident(message)
        try:
            public = self.get_public_key(source)
            if public.status != "active":
                raise ValueError("sender key is revoked")
            if public.key_id != key_id:
                raise ValueError("sender_key_id does not match registry")
            signing_public = Ed25519PublicKey.from_public_bytes(_unb64(public.signing_public_key_b64))
            unsigned = message.header.model_copy(update={"signature": ""})
            signing_public.verify(_unb64(message.header.signature), self._signature_body(unsigned))
            payload = self._payload_for_verification(message)
            if _sha256_hex(payload) != message.header.payload_hash:
                raise ValueError("payload hash mismatch")
            if consume_nonce:
                self._replay.check_and_mark(
                    nonce=message.header.nonce,
                    issued_at=message.header.issued_at,
                    sender_key_id=message.header.sender_key_id,
                )
            return VerifyMessageResult(
                accepted=True,
                message_hash=message_hash,
                sender_brain_id=source,
                sender_key_id=key_id,
                receiver_brain_id=message.header.receiver_brain_id,
                message_type=message.header.message_type,
                decrypted_payload=payload,
            )
        except Exception as exc:
            self._incident(
                event_type="message_rejected",
                source_brain_id=source,
                source_key_id=key_id,
                message_hash=message_hash,
                reason=str(exc) or exc.__class__.__name__,
                action_taken="reject_without_processing_payload",
            )
            raise

    def sign_revocation(self, request: KeyRevocationRequest) -> SignedKeyRevocationNotice:
        local = self._require_local(request.revoker_brain_id)
        notice = SignedKeyRevocationNotice(
            notice_id=f"key-revocation:{uuid4().hex}",
            revoker_brain_id=request.revoker_brain_id,
            revoker_key_id=local.public.key_id,
            target_brain_id=request.target_brain_id,
            target_key_id=request.target_key_id,
            reason=request.reason,
            issued_at=_now().isoformat(),
            signature="",
        )
        signature = local.signing_key.sign(self._revocation_body(notice))
        return notice.model_copy(update={"signature": _b64(signature)})

    def apply_revocation(self, notice: SignedKeyRevocationNotice) -> BrainIdentityPublicKey:
        message_hash = hashlib.sha256(self._revocation_body(notice)).hexdigest()
        try:
            revoker = self.get_public_key(notice.revoker_brain_id)
            if revoker.status != "active":
                raise ValueError("revoker key is not active")
            if revoker.key_id != notice.revoker_key_id:
                raise ValueError("revoker key mismatch")
            public_key = Ed25519PublicKey.from_public_bytes(_unb64(revoker.signing_public_key_b64))
            public_key.verify(_unb64(notice.signature), self._revocation_body(notice.model_copy(update={"signature": ""})))
            target = self.get_public_key(notice.target_brain_id)
            if target.key_id != notice.target_key_id:
                raise ValueError("target key mismatch")
            revoked = target.model_copy(update={"status": "revoked"})
            self._registry[notice.target_brain_id] = revoked
            local = self._locals.get(notice.target_brain_id)
            if local is not None:
                local.public = revoked
                if self._keystore is not None:
                    self._keystore.save(local)
            return revoked
        except Exception as exc:
            self._incident(
                event_type="revocation_rejected",
                source_brain_id=notice.revoker_brain_id,
                source_key_id=notice.revoker_key_id,
                message_hash=message_hash,
                reason=str(exc) or exc.__class__.__name__,
                action_taken="reject_revocation_notice",
            )
            raise

    def list_security_incidents(self) -> list[SecurityIncidentEvent]:
        return list(self._incidents)

    def rotate_identity(self, request: KeyRotationRequest) -> KeyRotationResult:
        existing = self.get_public_key(request.brain_id)
        revoked = existing.model_copy(update={"status": "revoked"})
        self._registry[request.brain_id] = revoked
        local = self._locals.get(request.brain_id)
        if local is not None:
            local.public = revoked
            if self._keystore is not None:
                self._keystore.save(local)
        created = self.create_identity(
            IdentityCreateRequest(
                brain_id=request.brain_id,
                tofu_confirmed_by=request.tofu_confirmed_by,
            )
        )
        return KeyRotationResult(
            brain_id=request.brain_id,
            old_key_id=existing.key_id,
            new_key_id=created.key_id,
            old_key_status="revoked",
            new_key_status="active",
        )

    def _payload_for_verification(self, message: SignedBrainMessage) -> dict[str, Any]:
        if message.header.encrypted:
            if message.encrypted_payload is None:
                raise ValueError("encrypted message is missing encrypted_payload")
            receiver = self._require_local(message.header.receiver_brain_id)
            return self._decrypt_payload(receiver=receiver, envelope=message.encrypted_payload, message_type=message.header.message_type)
        if message.payload is None:
            raise ValueError("signed message is missing payload")
        return message.payload

    def _encrypt_payload(
        self,
        *,
        sender: _LocalIdentity,
        receiver: BrainIdentityPublicKey,
        payload: dict[str, Any],
        message_type: str,
    ) -> EncryptedEnvelope:
        if receiver.status != "active":
            raise ValueError("receiver key is revoked")
        receiver_public = X25519PublicKey.from_public_bytes(_unb64(receiver.ecdh_public_key_b64))
        shared = sender.ecdh_key.exchange(receiver_public)
        key = self._derive_shared_key(shared, message_type)
        nonce = os.urandom(12)
        sender_pub = sender.ecdh_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        ciphertext = AESGCM(key).encrypt(nonce, _canonical(payload), message_type.encode("utf-8"))
        return EncryptedEnvelope(
            sender_ecdh_public_key_b64=_b64(sender_pub),
            nonce_b64=_b64(nonce),
            ciphertext_b64=_b64(ciphertext),
        )

    def _decrypt_payload(self, *, receiver: _LocalIdentity, envelope: EncryptedEnvelope, message_type: str) -> dict[str, Any]:
        sender_public = X25519PublicKey.from_public_bytes(_unb64(envelope.sender_ecdh_public_key_b64))
        shared = receiver.ecdh_key.exchange(sender_public)
        key = self._derive_shared_key(shared, message_type)
        plaintext = AESGCM(key).decrypt(
            _unb64(envelope.nonce_b64),
            _unb64(envelope.ciphertext_b64),
            message_type.encode("utf-8"),
        )
        return json.loads(plaintext.decode("utf-8"))

    @staticmethod
    def _derive_shared_key(shared: bytes, message_type: str) -> bytes:
        return HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b"zentex-brain-e2e-v1",
            info=f"brain-message:{message_type}".encode("utf-8"),
        ).derive(shared)

    @staticmethod
    def _signature_body(header: MessageHeader) -> bytes:
        return _canonical(
            {
                "message_type": header.message_type,
                "payload_hash": header.payload_hash,
                "sender_brain_id": header.sender_brain_id,
                "receiver_brain_id": header.receiver_brain_id,
                "nonce": header.nonce,
                "issued_at": header.issued_at,
                "sender_key_id": header.sender_key_id,
                "encrypted": header.encrypted,
            }
        )

    @staticmethod
    def _revocation_body(notice: SignedKeyRevocationNotice) -> bytes:
        return _canonical(
            notice.model_dump(
                mode="json",
                exclude={"signature"},
            )
        )

    def _require_local(self, brain_id: str) -> _LocalIdentity:
        local = self._locals.get(brain_id)
        if local is None:
            raise KeyError(f"local identity not found: {brain_id}")
        return local

    def _incident(
        self,
        *,
        event_type: str,
        source_brain_id: str | None,
        source_key_id: str | None,
        message_hash: str,
        reason: str,
        action_taken: str,
    ) -> None:
        previous_hash = self._last_incident_hash
        payload = {
            "event_id": f"security-incident:{uuid4().hex}",
            "event_type": event_type,
            "source_brain_id": source_brain_id,
            "source_key_id": source_key_id,
            "message_hash": message_hash,
            "detected_at": _now().isoformat(),
            "action_taken": action_taken,
            "reason": reason,
            "previous_event_hash": previous_hash,
        }
        event_hash = hashlib.sha256(_canonical(payload)).hexdigest()
        self._last_incident_hash = event_hash
        self._incidents.append(
            SecurityIncidentEvent(
                **payload,
                event_hash=event_hash,
            )
        )

    @staticmethod
    def _message_hash_for_incident(message: SignedBrainMessage) -> str:
        return hashlib.sha256(_canonical(message.model_dump(mode="json"))).hexdigest()

    @staticmethod
    def _derive_key_id_from_public_key(signing_public_key_b64: str) -> str:
        return "brain-key:" + hashlib.sha256(_unb64(signing_public_key_b64)).hexdigest()[:32]


def build_default_secure_collaboration_runtime() -> SecureCollaborationRuntime:
    return SecureCollaborationRuntime()

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from zentex.collaboration.models import PeerBrain, SharedExperience


class DeliveryError(RuntimeError):
    pass


class ExperienceTransport(Protocol):
    mode: str

    def deliver(self, peer: PeerBrain, experience: SharedExperience) -> None:
        ...


class MailboxTransport:
    mode = "mailbox"

    def __init__(self) -> None:
        self._handlers: dict[str, Callable[[SharedExperience], None]] = {}

    def register_handler(self, brain_id: str, handler: Callable[[SharedExperience], None]) -> None:
        self._handlers[brain_id] = handler

    def deliver(self, peer: PeerBrain, experience: SharedExperience) -> None:
        handler = self._handlers.get(peer.brain_id)
        if handler is None:
            raise DeliveryError(f"Mailbox handler for peer {peer.brain_id} is not registered")
        handler(experience)


class HttpExperienceTransport:
    mode = "http"

    def __init__(self, timeout_seconds: float = 5.0) -> None:
        self.timeout_seconds = timeout_seconds

    def deliver(self, peer: PeerBrain, experience: SharedExperience) -> None:
        if not peer.endpoint:
            raise DeliveryError(f"Peer {peer.brain_id} has no HTTP endpoint")
        import requests

        url = peer.endpoint.rstrip("/") + "/api/web/collaboration/experiences/receive"
        response = requests.post(
            url,
            json=experience.model_dump(mode="json"),
            timeout=self.timeout_seconds,
        )
        if response.status_code >= 400:
            raise DeliveryError(f"HTTP delivery failed: {response.status_code} {response.text}")

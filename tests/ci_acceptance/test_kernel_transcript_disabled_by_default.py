from __future__ import annotations

from zentex.kernel.service import KernelService
from zentex.kernel.state_domain.transcript import NullTranscriptStore


def test_kernel_uses_null_transcript_store_by_default(monkeypatch) -> None:
    monkeypatch.delenv("ZENTEX_ENABLE_TRANSCRIPTS", raising=False)

    service = KernelService()

    assert isinstance(service.transcript_store, NullTranscriptStore)

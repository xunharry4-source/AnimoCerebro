from __future__ import annotations

from pathlib import Path
import sys
import types

from fastapi.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

if "dspy" not in sys.modules:
    dspy_stub = types.ModuleType("dspy")

    class _Signature:
        pass

    class _Module:
        pass

    class _LM:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

    def _field(*_args, **_kwargs):
        return None

    class _ChainOfThought:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def __call__(self, **_kwargs):
            return types.SimpleNamespace()

    dspy_stub.Signature = _Signature
    dspy_stub.Module = _Module
    dspy_stub.LM = _LM
    dspy_stub.InputField = _field
    dspy_stub.OutputField = _field
    dspy_stub.ChainOfThought = _ChainOfThought
    sys.modules["dspy"] = dspy_stub

from zentex.memory.enhanced import EnhancedMemoryService  # noqa: E402
from zentex.runtime.runtime import BrainRuntime  # noqa: E402
from zentex.runtime.transcript import (  # noqa: E402
    BrainTranscriptEntryType,
    BrainTranscriptStore,
)
from zentex.web_console.app import create_web_console_app  # noqa: E402


def test_enhanced_memory_api_exposes_overview_records_and_search(tmp_path: Path) -> None:
    memory_service = EnhancedMemoryService(
        semantic_store_path=tmp_path / "semantic.jsonl",
        procedural_store_path=tmp_path / "procedural.jsonl",
        episodic_store_path=tmp_path / "episodic.jsonl",
        management_store_path=tmp_path / "management.json",
        audit_store_path=tmp_path / "memory_audit.jsonl",
    )
    transcript_store = BrainTranscriptStore(tmp_path / "brain_transcript.jsonl")
    runtime = BrainRuntime(
        transcript_store=transcript_store,
        runtime_memory_store=memory_service,
    )
    transcript_store.write_entry(
        session_id="session-memory-api",
        turn_id="turn-memory-api",
        entry_type=BrainTranscriptEntryType.DECISION_SYNTHESIZED,
        payload={"summary": "Selected the safer rollback-aware mitigation path."},
        source="runtime.think_loop",
        trace_id="trace-memory-api-001",
    )
    app = create_web_console_app(runtime=runtime)
    client = TestClient(app)

    overview = client.get("/api/web/memory/enhanced/overview")
    assert overview.status_code == 200
    overview_payload = overview.json()
    assert overview_payload["semantic_count"] >= 1
    assert "active_count" in overview_payload
    assert any(item["backend"] == "external_semantic_bridge" for item in overview_payload["backends"])

    records = client.get("/api/web/memory/enhanced/records?layer=procedural&limit=10")
    assert records.status_code == 200
    records_payload = records.json()
    assert records_payload["layer"] == "procedural"
    assert records_payload["items"]
    assert records_payload["items"][0]["trace_id"] == "trace-memory-api-001"
    memory_id = records_payload["items"][0]["memory_id"]

    search = client.get("/api/web/memory/enhanced/search?query=rollback-aware&limit=5")
    assert search.status_code == 200
    search_payload = search.json()
    assert search_payload["items"]
    assert search_payload["items"][0]["trace_id"] == "trace-memory-api-001"

    detail = client.get(f"/api/web/memory/enhanced/{memory_id}")
    assert detail.status_code == 200
    detail_payload = detail.json()
    assert detail_payload["status"] == "active"
    assert detail_payload["trust_level"] == "unverified"

    management = client.post(
        f"/api/web/memory/enhanced/{memory_id}/management",
        json={
            "trust_level": "suspect",
            "management_note": "Trace produced conflicting evidence.",
            "correction_note": "Do not reuse before human verification.",
            "operator": "api-test",
            "reason": "Manual governance review.",
        },
    )
    assert management.status_code == 200
    management_payload = management.json()
    assert management_payload["trust_level"] == "suspect"
    assert management_payload["management_note"] == "Trace produced conflicting evidence."

    filtered = client.get("/api/web/memory/enhanced/records?trust_level=suspect&limit=10")
    assert filtered.status_code == 200
    filtered_payload = filtered.json()
    assert any(item["memory_id"] == memory_id for item in filtered_payload["items"])

    audit = client.get(f"/api/web/memory/enhanced/{memory_id}/audit?limit=10")
    assert audit.status_code == 200
    audit_payload = audit.json()
    assert audit_payload["items"]
    assert audit_payload["items"][0]["memory_id"] == memory_id

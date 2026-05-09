from __future__ import annotations

from fastapi.testclient import TestClient


def test_reported_web_console_read_apis_return_business_payloads(client: TestClient) -> None:
    """功能：通过真实 HTTP 请求验证前端轮询的只读 API 不会 500/断连。"""
    overview = client.get("/api/web/upgrades/overview")
    assert overview.status_code == 200
    overview_payload = overview.json()
    assert {"llm", "plugins", "recent_llm", "recent_plugins"} <= set(overview_payload)
    assert isinstance(overview_payload["llm"]["all"], int)
    assert isinstance(overview_payload["plugins"]["all"], int)

    lifecycle = client.get("/api/web/upgrades/by-lifecycle-view?target_kind=llm")
    assert lifecycle.status_code == 200
    lifecycle_payload = lifecycle.json()
    assert {"ongoing", "waiting", "failed", "cancelled", "completed"} <= set(lifecycle_payload)
    assert isinstance(lifecycle_payload["completed"]["count"], int)
    assert isinstance(lifecycle_payload["completed"]["items"], list)

    health = client.get("/api/web/health/system")
    assert health.status_code == 200
    health_payload = health.json()
    assert health_payload["overall_health"] in {"healthy", "degraded", "unhealthy"}
    assert isinstance(health_payload["modules"], list)

    memory = client.get("/api/web/memory/overview")
    assert memory.status_code == 200
    memory_payload = memory.json()
    assert isinstance(memory_payload["semantic_count"], int)
    assert isinstance(memory_payload["procedural_count"], int)
    assert isinstance(memory_payload["episodic_count"], int)
    assert memory_payload["health_status"] in {"healthy", "degraded", "unhealthy", "unknown"}

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import requests
from fastapi import FastAPI

from tests.ci_acceptance.real_ci_modules.kernel.http_server import live_http_server
from zentex.collaboration.social_communication import SocialCommunicationRuntime


def _iso(offset_seconds: int = 0) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=offset_seconds)).isoformat()


def test_social_communication_history_presence_domain_map_and_routing_real_requests(
    acceptance_app: FastAPI,
) -> None:
    acceptance_app.state.social_communication_runtime = SocialCommunicationRuntime(min_presence_interval_seconds=30)
    suffix = uuid4().hex
    good_brain = f"social-good-{suffix}"
    risky_brain = f"social-risky-{suffix}"
    domain = f"risk-review-{suffix}"
    before_audit_count = len(acceptance_app.state.transcript_store.entries)

    with live_http_server(acceptance_app) as base_url:
        empty_trust = requests.get(
            f"{base_url}/api/web/collaboration/social/trust",
            params={"brain_id": good_brain, "domain": domain},
            timeout=10,
        )
        assert empty_trust.status_code == 200
        assert empty_trust.json()["score"] == 0.0
        assert empty_trust.json()["sample_count"] == 0

        for idx in range(3):
            response = requests.post(
                f"{base_url}/api/web/collaboration/social/interactions",
                json={
                    "task_id": f"task-good-{idx}-{suffix}",
                    "brain_id": good_brain,
                    "domain": domain,
                    "outcome": "success",
                    "quality_score": 0.96,
                    "occurred_at": _iso(-idx * 60),
                    "notes": "real collaboration success evidence",
                },
                timeout=10,
            )
            assert response.status_code == 200, response.text
            payload = response.json()
            assert payload["record"]["brain_id"] == good_brain
            assert payload["trust_score"]["brain_id"] == good_brain
            assert payload["reputation_profile"]["profile_source"] == "interaction_history"

        breach = requests.post(
            f"{base_url}/api/web/collaboration/social/interactions",
            json={
                "task_id": f"task-risky-{suffix}",
                "brain_id": risky_brain,
                "domain": domain,
                "outcome": "breach",
                "quality_score": 0.0,
                "occurred_at": _iso(-120),
                "notes": "goal handoff was violated",
            },
            timeout=10,
        )
        assert breach.status_code == 200
        assert breach.json()["trust_score"]["trust_band"] == "blocked"

        interactions = requests.get(
            f"{base_url}/api/web/collaboration/social/interactions",
            params={"domain": domain},
            timeout=10,
        )
        assert interactions.status_code == 200
        assert len(interactions.json()) == 4

        trust = requests.get(
            f"{base_url}/api/web/collaboration/social/trust",
            params={"brain_id": good_brain, "domain": domain},
            timeout=10,
        )
        assert trust.status_code == 200
        trust_payload = trust.json()
        assert trust_payload["sample_count"] == 3
        assert trust_payload["success_rate"] == 1.0
        assert trust_payload["score"] >= 0.8
        assert trust_payload["trust_band"] == "high"

        reputation = requests.get(
            f"{base_url}/api/web/collaboration/social/reputation/{good_brain}",
            timeout=10,
        )
        assert reputation.status_code == 200
        reputation_payload = reputation.json()
        assert reputation_payload["reputation_domains"][domain] == "trusted"
        assert reputation_payload["sample_counts"][domain] == 3
        assert reputation_payload["severe_breach_domains"] == []

        first_presence = requests.post(
            f"{base_url}/api/web/collaboration/social/presence",
            json={
                "brain_id": good_brain,
                "current_load_level": "low",
                "available_domains": [domain],
                "cooperation_willingness": "available",
                "specialization_tags": ["risk", "audit"],
                "last_active_at": _iso(0),
                "ttl_seconds": 600,
                "version": 1,
            },
            timeout=10,
        )
        assert first_presence.status_code == 200

        too_fast_presence = requests.post(
            f"{base_url}/api/web/collaboration/social/presence",
            json={
                "brain_id": good_brain,
                "current_load_level": "medium",
                "available_domains": [domain],
                "cooperation_willingness": "available",
                "specialization_tags": ["risk", "audit"],
                "last_active_at": _iso(10),
                "ttl_seconds": 600,
                "version": 2,
            },
            timeout=10,
        )
        assert too_fast_presence.status_code == 409
        assert "frequency limit" in too_fast_presence.json()["detail"]

        risky_presence = requests.post(
            f"{base_url}/api/web/collaboration/social/presence",
            json={
                "brain_id": risky_brain,
                "current_load_level": "low",
                "available_domains": [domain],
                "cooperation_willingness": "available",
                "specialization_tags": ["risk"],
                "last_active_at": _iso(0),
                "ttl_seconds": 600,
                "version": 1,
            },
            timeout=10,
        )
        assert risky_presence.status_code == 200

        unwilling = requests.post(
            f"{base_url}/api/web/collaboration/social/willingness",
            json={
                "brain_id": risky_brain,
                "unavailable_domains": [domain],
                "reason": "recent breach requires review",
                "valid_until": _iso(3600),
                "risk_ceiling": "low",
            },
            timeout=10,
        )
        assert unwilling.status_code == 200

        domain_map = requests.get(
            f"{base_url}/api/web/collaboration/social/domain-map",
            params={"domain": domain},
            timeout=10,
        )
        assert domain_map.status_code == 200
        entries = domain_map.json()["items"]
        assert [item["brain_id"] for item in entries] == [good_brain, risky_brain]
        assert entries[0]["trust_score"] > entries[1]["trust_score"]
        assert entries[0]["stale"] is False
        assert entries[0]["freshness_score"] > 0
        assert entries[1]["expertise_level"] == "novice"

        external_brain = f"social-external-{suffix}"
        gossip = requests.post(
            f"{base_url}/api/web/collaboration/social/domain-map/gossip",
            json={
                "source_brain_id": f"peer-map-{suffix}",
                "gossip_version": 7,
                "entries": [
                    {
                        "brain_id": external_brain,
                        "domain": domain,
                        "expertise_level": "expert",
                        "trust_score": 0.91,
                        "freshness_score": 0.88,
                        "stale": False,
                        "current_load_level": "low",
                        "cooperation_willingness": "available",
                        "source_version": 1,
                    }
                ],
            },
            timeout=10,
        )
        assert gossip.status_code == 200, gossip.text
        assert gossip.json()["accepted_count"] == 1
        assert gossip.json()["merged_domains"] == [domain]

        merged_map = requests.get(
            f"{base_url}/api/web/collaboration/social/domain-map",
            params={"domain": domain},
            timeout=10,
        )
        assert merged_map.status_code == 200
        merged_entries = merged_map.json()["items"]
        merged_by_brain = {item["brain_id"]: item for item in merged_entries}
        assert external_brain in merged_by_brain
        assert merged_by_brain[external_brain]["expertise_level"] == "expert"
        assert merged_by_brain[external_brain]["source_version"] == 7

        old_gossip = requests.post(
            f"{base_url}/api/web/collaboration/social/domain-map/gossip",
            json={
                "source_brain_id": f"peer-map-{suffix}",
                "gossip_version": 6,
                "entries": [
                    {
                        "brain_id": external_brain,
                        "domain": domain,
                        "expertise_level": "novice",
                        "trust_score": 0.01,
                        "freshness_score": 0.01,
                        "stale": False,
                        "current_load_level": "overloaded",
                        "cooperation_willingness": "unavailable",
                        "source_version": 1,
                    }
                ],
            },
            timeout=10,
        )
        assert old_gossip.status_code == 409
        assert "gossip_version must increase" in old_gossip.json()["detail"]

        unchanged_map = requests.get(
            f"{base_url}/api/web/collaboration/social/domain-map",
            params={"domain": domain},
            timeout=10,
        )
        assert unchanged_map.status_code == 200
        unchanged_external = {item["brain_id"]: item for item in unchanged_map.json()["items"]}[external_brain]
        assert unchanged_external["trust_score"] == 0.91
        assert unchanged_external["current_load_level"] == "low"

        blocked_route = requests.post(
            f"{base_url}/api/web/collaboration/social/route",
            json={
                "task_domain": domain,
                "required_expertise": "trusted",
                "risk_level": "high",
                "urgency": "high",
                "goal_security_review_passed": False,
            },
            timeout=10,
        )
        assert blocked_route.status_code == 409
        assert "goal_security_review" in blocked_route.json()["detail"]

        route = requests.post(
            f"{base_url}/api/web/collaboration/social/route",
            json={
                "task_domain": domain,
                "required_expertise": "trusted",
                "risk_level": "high",
                "urgency": "high",
                "goal_security_review_passed": True,
                "authorized_force_route": False,
            },
            timeout=10,
        )
        assert route.status_code == 200, route.text
        route_payload = route.json()
        assert route_payload["recommendation_only"] is True
        assert route_payload["requires_final_decision"] is True
        assert route_payload["goal_security_review_passed"] is True
        candidate_ids = [item["brain_id"] for item in route_payload["candidates"]]
        assert good_brain in candidate_ids
        assert external_brain in candidate_ids
        candidate_by_brain = {item["brain_id"]: item for item in route_payload["candidates"]}
        assert candidate_by_brain[good_brain]["expertise_level"] == "trusted"
        assert candidate_by_brain[good_brain]["accepted_by_willingness"] is True
        assert candidate_by_brain[external_brain]["expertise_level"] == "expert"
        assert candidate_by_brain[external_brain]["freshness_score"] == 0.88
        rejected = {item["brain_id"]: item for item in route_payload["rejected_candidates"]}
        assert risky_brain in rejected
        assert rejected[risky_brain]["accepted_by_willingness"] is False
        assert any("blocked" in reason for reason in rejected[risky_brain]["reasons"])

        audit = requests.get(f"{base_url}/api/web/collaboration/social/audit", timeout=10)
        assert audit.status_code == 200
        audit_types = [item["event_type"] for item in audit.json()]
        assert "interaction_recorded" in audit_types
        assert "presence_broadcast" in audit_types
        assert "willingness_published" in audit_types
        assert "domain_map_gossip_merged" in audit_types
        assert "social_route_recommended" in audit_types

    new_audits = acceptance_app.state.transcript_store.entries[before_audit_count:]
    audit_payloads = [item["payload"] for item in new_audits]
    assert any(item["event_type"] == "social_interaction_recorded" for item in audit_payloads)
    assert any(item["event_type"] == "social_presence_broadcast" for item in audit_payloads)
    assert any(item["event_type"] == "social_willingness_published" for item in audit_payloads)
    assert any(item["event_type"] == "social_domain_map_gossip_merged" for item in audit_payloads)
    assert any(item["event_type"] == "social_route_recommended" for item in audit_payloads)


def test_social_communication_rejects_self_assigned_trust_and_stale_presence_versions_real_requests(
    acceptance_app: FastAPI,
) -> None:
    acceptance_app.state.social_communication_runtime = SocialCommunicationRuntime(min_presence_interval_seconds=30)
    suffix = uuid4().hex
    brain_id = f"social-version-{suffix}"
    domain = f"ops-{suffix}"

    with live_http_server(acceptance_app) as base_url:
        self_assigned = requests.post(
            f"{base_url}/api/web/collaboration/social/interactions",
            json={
                "task_id": f"task-{suffix}",
                "brain_id": brain_id,
                "domain": domain,
                "outcome": "success",
                "quality_score": 1.0,
                "trust_score": 1.0,
            },
            timeout=10,
        )
        assert self_assigned.status_code == 422

        first = requests.post(
            f"{base_url}/api/web/collaboration/social/presence",
            json={
                "brain_id": brain_id,
                "current_load_level": "medium",
                "available_domains": [domain],
                "cooperation_willingness": "limited",
                "specialization_tags": ["ops"],
                "last_active_at": _iso(0),
                "ttl_seconds": 1,
                "version": 3,
            },
            timeout=10,
        )
        assert first.status_code == 200

        stale_version = requests.post(
            f"{base_url}/api/web/collaboration/social/presence",
            json={
                "brain_id": brain_id,
                "current_load_level": "low",
                "available_domains": [domain],
                "cooperation_willingness": "available",
                "specialization_tags": ["ops"],
                "last_active_at": _iso(60),
                "ttl_seconds": 1,
                "version": 3,
            },
            timeout=10,
        )
        assert stale_version.status_code == 409
        assert "version must increase" in stale_version.json()["detail"]

        expired_willingness = requests.post(
            f"{base_url}/api/web/collaboration/social/willingness",
            json={
                "brain_id": brain_id,
                "unavailable_domains": [domain],
                "reason": "expired signal should be rejected",
                "valid_until": _iso(-10),
                "risk_ceiling": "medium",
            },
            timeout=10,
        )
        assert expired_willingness.status_code == 409
        assert "valid_until" in expired_willingness.json()["detail"]

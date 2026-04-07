import asyncio
import sys
from pathlib import Path
from unittest.mock import Mock

# Add src to sys.path
sys.path.append(str(Path(__file__).parent.parent.parent / "src"))

from zentex.tasks.models import TaskStatus, TaskType
from zentex.tasks.errors import TaskStateError
from zentex.tasks.registry import TaskRegistry
from zentex.tasks.service import TaskManagementService

async def test_mission_decomposition_lifecycle():
    print("Running Mission Decomposition & Lifecycle Test...")
    
    transcript_store = Mock()
    registry = TaskRegistry()
    service = TaskManagementService(
        registry,
        transcript_store,
        allow_rule_based_test_stub=True,
    )
    
    # 1. Create a MISSION
    print("Step 1: Creating a high-level MISSION...")
    mission = await service.create_task({
        "title": "Build Autonomous Market Edge",
        "task_type": TaskType.MISSION,
        "originator_id": "zentex-ceo",
        "remarks": "Create a clinical-grade trading strategy for 2025.",
        "idempotency_key": "mission-001"
    })
    
    # Wait for async decomposition
    await asyncio.sleep(0.1)
    
    assert len(mission.subtask_ids) == 3
    print(f"PASS: Mission decomposed into {len(mission.subtask_ids)} subtasks.")
    
    step1_id = mission.subtask_ids[0]
    step2_id = mission.subtask_ids[1]
    
    step1 = service.get_task(step1_id)
    step2 = service.get_task(step2_id)
    
    assert step2.depends_on == [step1_id]
    print("PASS: Dependency linkage [step-2 depends_on step-1] verified.")

    # 2. Test Claiming with Dependency Lock
    print("\nStep 2: Testing dependency-locked claiming...")
    try:
        await service.claim_task(step2_id, "agent-bob")
        assert False, "ERROR: Claimed step-2 before step-1 was DONE!"
    except TaskStateError as exc:
        print(f"PASS: Claim blocked as expected: {exc}")

    # 3. Complete Step-1 and try again
    print("\nStep 3: Completing Step-1 and re-claiming Step-2...")
    service.update_task_status(step1_id, TaskStatus.IN_PROGRESS)
    service.update_task_status(step1_id, TaskStatus.DONE)
    
    claimed_step2 = await service.claim_task(step2_id, "agent-bob")
    assert claimed_step2.status == TaskStatus.IN_PROGRESS
    assert claimed_step2.target_id == "agent-bob"
    print("PASS: Step-2 claimed successfully after Step-1 completion.")

    # 4. Idempotency Check
    print("\nStep 4: Testing idempotency for mission re-submission...")
    re_mission = await service.create_task({
        "title": "Build Autonomous Market Edge",
        "task_type": TaskType.MISSION,
        "originator_id": "zentex-ceo",
        "idempotency_key": "mission-001"
    })
    assert re_mission.task_id == mission.task_id
    print("PASS: Idempotency enforced. Direct duplicate mission rejected.")

    print("\nALL MISSION DECOMPOSITION TESTS PASSED.")

if __name__ == "__main__":
    asyncio.run(test_mission_decomposition_lifecycle())

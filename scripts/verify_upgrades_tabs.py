#!/usr/bin/env python3
"""
Quick verification script for the upgrades tab refactoring.

This script demonstrates the new /api/web/upgrades/by-lifecycle-view endpoint
and verifies that CANCELLED status is properly separated from FAILED.
"""
import sys
from pathlib import Path

# Add src to path
PROJECT_ROOT = Path(__file__).resolve().parent
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from zentex.upgrade.management import (
    UpgradeLifecycleStatus,
    UpgradeLifecycleView,
    UpgradeManagementRecord,
    UpgradeManagementStore,
    UpgradeTargetKind,
    CANCELLED_STATUSES,
    FAILED_STATUSES,
)
from zentex.web_console.services.upgrades import build_upgrades_by_lifecycle_view


def main():
    print("=" * 80)
    print("Upgrades Tab Refactoring - Quick Verification")
    print("=" * 80)
    print()

    # 1. Verify CANCELLED is separate from FAILED
    print("1. Verifying CANCELLED/FAILED separation...")
    print(f"   CANCELLED_STATUSES: {CANCELLED_STATUSES}")
    print(f"   FAILED_STATUSES: {FAILED_STATUSES}")
    
    assert UpgradeLifecycleStatus.CANCELLED in CANCELLED_STATUSES
    assert UpgradeLifecycleStatus.CANCELLED not in FAILED_STATUSES
    assert UpgradeLifecycleStatus.FAILED in FAILED_STATUSES
    assert UpgradeLifecycleStatus.FAILED not in CANCELLED_STATUSES
    print("   ✓ CANCELLED and FAILED are properly separated")
    print()

    # 2. Verify lifecycle_view() returns correct values
    print("2. Verifying lifecycle_view() method...")
    
    test_cases = [
        (UpgradeLifecycleStatus.QUEUED, UpgradeLifecycleView.WAITING),
        (UpgradeLifecycleStatus.RUNNING, UpgradeLifecycleView.ONGOING),
        (UpgradeLifecycleStatus.COMPLETED, UpgradeLifecycleView.COMPLETED),
        (UpgradeLifecycleStatus.FAILED, UpgradeLifecycleView.FAILED),
        (UpgradeLifecycleStatus.CANCELLED, UpgradeLifecycleView.CANCELLED),
    ]
    
    for status, expected_view in test_cases:
        record = UpgradeManagementRecord(
            record_id=f"test-{status.value}",
            target_kind=UpgradeTargetKind.LLM,
            action="upgrade",
            target_id="test-target",
            title="Test Record",
            reason="Testing",
            trace_id="trace-test",
            request_id="req-test",
            change_summary="Test",
            function_summary="Test",
            previous_version="1.0.0",
            current_version="1.1.0",
            candidate_version=None,
            current_status=status,
        )
        actual_view = record.lifecycle_view()
        assert actual_view == expected_view, f"Expected {expected_view}, got {actual_view}"
        print(f"   ✓ {status.value:20s} -> {actual_view.value}")
    print()

    # 3. Test build_upgrades_by_lifecycle_view function
    print("3. Testing build_upgrades_by_lifecycle_view()...")
    
    store = UpgradeManagementStore()
    
    # Create test records
    records_data = [
        ("ongoing-1", UpgradeLifecycleStatus.RUNNING),
        ("ongoing-2", UpgradeLifecycleStatus.VALIDATING),
        ("waiting-1", UpgradeLifecycleStatus.QUEUED),
        ("failed-1", UpgradeLifecycleStatus.FAILED),
        ("cancelled-1", UpgradeLifecycleStatus.CANCELLED),
        ("completed-1", UpgradeLifecycleStatus.COMPLETED),
    ]
    
    for record_id, status in records_data:
        record = UpgradeManagementRecord(
            record_id=record_id,
            target_kind=UpgradeTargetKind.LLM,
            action="upgrade",
            target_id="test-target",
            title=f"Test {record_id}",
            reason="Testing",
            trace_id=f"trace-{record_id}",
            request_id=f"req-{record_id}",
            change_summary="Test",
            function_summary="Test",
            previous_version="1.0.0",
            current_version="1.1.0",
            candidate_version=None,
            current_status=status,
        )
        store._records[record_id] = record
    
    # Build grouped view
    result = build_upgrades_by_lifecycle_view(store)
    
    # Verify counts
    expected_counts = {
        "ongoing": 2,
        "waiting": 1,
        "failed": 1,
        "cancelled": 1,
        "completed": 1,
    }
    
    for group_name, expected_count in expected_counts.items():
        group = getattr(result, group_name)
        actual_count = group.count
        assert actual_count == expected_count, f"{group_name}: expected {expected_count}, got {actual_count}"
        print(f"   ✓ {group_name:12s}: {actual_count} record(s)")
        
        # Verify items
        assert len(group.items) == expected_count
        for item in group.items:
            print(f"      - {item.record_id} ({item.current_status})")
    print()

    # 4. Test filtering by target_kind
    print("4. Testing target_kind filtering...")
    
    store2 = UpgradeManagementStore()
    
    # Create LLM and Plugin records
    llm_record = UpgradeManagementRecord(
        record_id="llm-1",
        target_kind=UpgradeTargetKind.LLM,
        action="upgrade",
        target_id="llm-target",
        title="LLM Record",
        reason="Testing",
        trace_id="trace-llm-1",
        request_id="req-llm-1",
        change_summary="Test",
        function_summary="Test",
        previous_version="1.0.0",
        current_version="1.1.0",
        candidate_version=None,
        current_status=UpgradeLifecycleStatus.COMPLETED,
    )
    store2._records["llm-1"] = llm_record
    
    plugin_record = UpgradeManagementRecord(
        record_id="plugin-1",
        target_kind=UpgradeTargetKind.PLUGIN,
        action="upgrade",
        target_id="plugin-target",
        title="Plugin Record",
        reason="Testing",
        trace_id="trace-plugin-1",
        request_id="req-plugin-1",
        change_summary="Test",
        function_summary="Test",
        previous_version="1.0.0",
        current_version="1.1.0",
        candidate_version=None,
        current_status=UpgradeLifecycleStatus.COMPLETED,
    )
    store2._records["plugin-1"] = plugin_record
    
    # Filter by LLM
    result_llm = build_upgrades_by_lifecycle_view(store2, target_kind=UpgradeTargetKind.LLM)
    assert result_llm.completed.count == 1
    assert result_llm.completed.items[0].record_id == "llm-1"
    print(f"   ✓ LLM filter: {result_llm.completed.count} completed record(s)")
    
    # Filter by Plugin
    result_plugin = build_upgrades_by_lifecycle_view(store2, target_kind=UpgradeTargetKind.PLUGIN)
    assert result_plugin.completed.count == 1
    assert result_plugin.completed.items[0].record_id == "plugin-1"
    print(f"   ✓ Plugin filter: {result_plugin.completed.count} completed record(s)")
    print()

    print("=" * 80)
    print("✓ All verifications passed!")
    print("=" * 80)
    print()
    print("Summary:")
    print("  - CANCELLED status is properly separated from FAILED")
    print("  - lifecycle_view() returns correct values for all statuses")
    print("  - build_upgrades_by_lifecycle_view() groups records correctly")
    print("  - Filtering by target_kind works as expected")
    print()
    print("The backend is ready for the tabbed UI implementation.")


if __name__ == "__main__":
    main()

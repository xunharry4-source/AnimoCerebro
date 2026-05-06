"""
Example: Using Automated Upgrade Skills

This example demonstrates how to use the Superpowers-inspired automated skills
to enhance the upgrade process without human interaction.
"""

import asyncio
import tempfile
from pathlib import Path

from zentex.upgrade import (
    AtomicUpgradePlanner,
    AutomatedRootCauseAnalyzer,
    AutomatedTwoStageReviewer,
)
from zentex.upgrade.base_models import SelfUpgradeProposal


def example_atomic_planning():
    """Example 1: Automatic task decomposition"""
    print("=" * 80)
    print("Example 1: Atomic Task Decomposition")
    print("=" * 80)
    
    # Create a planner
    planner = AtomicUpgradePlanner()
    
    # Define an upgrade proposal
    proposal = SelfUpgradeProposal(
        program_id="plugin-data-processor",
        target_metric="reliability",
        baseline_version="1.2.3",
        candidate_version="1.3.0-candidate",
        description="Add retry logic for network operations",
        risk_score=0.4,
        impact_score=0.6,
        capability_gap="Plugin fails on transient network errors"
    )
    
    # Automatically decompose into atomic tasks
    atomic_plan = planner.decompose_proposal(proposal)
    
    print(f"\nGenerated {len(atomic_plan.tasks)} atomic tasks:")
    print(f"Total estimated time: {atomic_plan.total_estimated_minutes} minutes")
    print(f"Critical path: {' → '.join(atomic_plan.critical_path)}\n")
    
    for i, task in enumerate(atomic_plan.tasks, 1):
        print(f"Task {i}: {task.description}")
        print(f"  ID: {task.task_id}")
        print(f"  Time: {task.estimated_time_minutes} minutes")
        print(f"  Files: {', '.join(task.file_paths[:2])}...")
        print(f"  Validation: {task.validation_commands[0] if task.validation_commands else 'N/A'}")
        if task.dependencies:
            print(f"  Dependencies: {', '.join(task.dependencies)}")
        print()


async def example_code_review():
    """Example 2: Automated two-stage code review"""
    print("=" * 80)
    print("Example 2: Automated Two-Stage Code Review")
    print("=" * 80)
    
    # Create a reviewer
    reviewer = AutomatedTwoStageReviewer()
    
    class ExampleCandidate:
        isolation_path = str(Path(tempfile.gettempdir()) / "example-plugin")
        changes = {
            "baseline_version": "1.0.0",
            "candidate_version": "1.1.0-candidate"
        }

    candidate = ExampleCandidate()
    
    # Perform automated review
    result = await reviewer.review_candidate(candidate)
    
    print(f"\nReview Status: {result.status.upper()}")
    print(f"Stage: {result.stage}")
    print(f"Summary: {result.summary}")
    print(f"\nPassed checks: {', '.join(result.passed_checks)}")
    print(f"Failed checks: {', '.join(result.failed_checks) if result.failed_checks else 'None'}")
    
    if result.issues:
        print(f"\nIssues found ({len(result.issues)}):")
        for issue in result.issues:
            print(f"  [{issue.severity.upper()}] {issue.description}")
            if issue.suggestion:
                print(f"    → Suggestion: {issue.suggestion}")


def example_root_cause_analysis():
    """Example 3: Automated root cause analysis"""
    print("=" * 80)
    print("Example 3: Automated Root Cause Analysis")
    print("=" * 80)
    
    # Create an analyzer
    analyzer = AutomatedRootCauseAnalyzer()
    
    class ExampleFailedRecord:
        target_id = "plugin-example"
        target_kind = type('obj', (object,), {'value': 'PLUGIN'})()
        failure_stage = "plugin_upgrade"
        failure_reason = "ModuleNotFoundError: No module named 'numpy'"
        failure_code = "modulenotfound"
        candidate_version = "1.1.0-candidate"
        payload = {
            "stack_trace": "File 'plugin.py', line 5, in <module>\n  import numpy"
        }
    
    failed_record = ExampleFailedRecord()
    
    # Perform root cause analysis
    analysis = analyzer.analyze_failure(failed_record)
    
    print(f"\nAnalysis ID: {analysis.analysis_id}")
    print(f"\nReproduction Steps:")
    for i, step in enumerate(analysis.reproduction_steps, 1):
        print(f"  {i}. {step}")
    
    print(f"\nIsolated Scope:")
    for scope in analysis.isolated_scope:
        print(f"  - {scope}")
    
    print(f"\nRoot Cause Analysis:")
    print(f"  Immediate cause: {analysis.immediate_cause}")
    print(f"  Root cause: {analysis.root_cause}")
    print(f"  Triggering condition: {analysis.triggering_condition}")
    print(f"  Confidence: {analysis.confidence_level:.0%}")
    
    print(f"\nVerification Plan:")
    for i, step in enumerate(analysis.verification_plan, 1):
        print(f"  {i}. {step}")
    
    print(f"\nPrevention Hint:")
    print(f"  {analysis.prevention_hint}")


def main():
    """Run all examples"""
    print("\n" + "=" * 80)
    print("AUTOMATED UPGRADE SKILLS EXAMPLES")
    print("Superpowers-Inspired, Fully Automated, No Human Interaction Required")
    print("=" * 80 + "\n")
    
    # Example 1: Atomic planning (synchronous)
    example_atomic_planning()
    
    # Example 2: Code review (async)
    asyncio.run(example_code_review())
    
    # Example 3: Root cause analysis (synchronous)
    example_root_cause_analysis()
    
    print("\n" + "=" * 80)
    print("Examples completed successfully!")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()

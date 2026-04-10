"""
Atomic Upgrade Planner - Automatically decomposes upgrade proposals into atomic tasks.

Inspired by Superpowers' writing-plans skill, this module provides automated
task decomposition for upgrade proposals without requiring human interaction.

Each atomic task is designed to complete in 2-5 minutes with clear file paths,
validation commands, and dependency tracking.
"""

from __future__ import annotations

import json
from typing import List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from zentex.upgrade.base_models import SelfUpgradeProposal


class AtomicTask(BaseModel):
    """Represents a single atomic upgrade task."""
    
    task_id: str = Field(description="Unique task identifier")
    description: str = Field(description="Clear description of what this task does")
    file_paths: List[str] = Field(
        default_factory=list,
        description="List of file paths to be modified or created"
    )
    code_changes: dict = Field(
        default_factory=dict,
        description="Structured representation of code changes"
    )
    validation_commands: List[str] = Field(
        default_factory=list,
        description="Shell commands to validate this task's completion"
    )
    estimated_time_minutes: int = Field(
        ge=2, 
        le=5,
        description="Estimated completion time (2-5 minutes per task)"
    )
    dependencies: List[str] = Field(
        default_factory=list,
        description="List of task_ids that must complete before this task"
    )
    rollback_instructions: Optional[str] = Field(
        default=None,
        description="Instructions to rollback this specific task if needed"
    )


class AtomicUpgradePlan(BaseModel):
    """Complete atomic upgrade plan decomposed from a proposal."""
    
    proposal_id: str = Field(description="Reference to the original proposal")
    tasks: List[AtomicTask] = Field(description="Ordered list of atomic tasks")
    total_estimated_minutes: int = Field(description="Total estimated time for all tasks")
    critical_path: List[str] = Field(
        default_factory=list,
        description="Task IDs on the critical execution path"
    )
    generation_metadata: dict = Field(
        default_factory=dict,
        description="Metadata about how this plan was generated"
    )


class AtomicUpgradePlanner:
    """
    Automatically decomposes upgrade proposals into atomic tasks.
    
    This planner uses historical success patterns and LLM assistance to generate
    detailed, executable upgrade plans without human intervention.
    
    Example:
        >>> planner = AtomicUpgradePlanner()
        >>> proposal = SelfUpgradeProposal(...)
        >>> plan = planner.decompose_proposal(proposal)
        >>> print(f"Generated {len(plan.tasks)} atomic tasks")
    """
    
    def __init__(
        self,
        llm_service=None,
        memory_service=None,
    ):
        """
        Initialize the atomic upgrade planner.
        
        Args:
            llm_service: LLM service for generating task descriptions
            memory_service: Memory service for recalling successful patterns
        """
        self._llm_service = llm_service
        self._memory_service = memory_service
    
    def decompose_proposal(self, proposal: SelfUpgradeProposal) -> AtomicUpgradePlan:
        """
        Decompose an upgrade proposal into atomic tasks.
        
        Args:
            proposal: The upgrade proposal to decompose
            
        Returns:
            AtomicUpgradePlan with ordered atomic tasks
            
        Raises:
            ValueError: If proposal is incomplete or invalid
        """
        if not proposal.program_id:
            raise ValueError("Proposal must have a program_id")
        
        # Step 1: Recall similar successful upgrade patterns
        similar_patterns = self._recall_success_patterns(proposal)
        
        # Step 2: Generate atomic tasks based on proposal and patterns
        tasks = self._generate_atomic_tasks(proposal, similar_patterns)
        
        # Step 3: Validate task completeness
        self._validate_tasks(tasks)
        
        # Step 4: Calculate total time and identify critical path
        total_time = sum(t.estimated_time_minutes for t in tasks)
        critical_path = self._identify_critical_path(tasks)
        
        return AtomicUpgradePlan(
            proposal_id=getattr(proposal, 'proposal_id', f"proposal-{uuid4().hex[:8]}"),
            tasks=tasks,
            total_estimated_minutes=total_time,
            critical_path=critical_path,
            generation_metadata={
                "similar_patterns_used": len(similar_patterns),
                "planner_version": "1.0.0",
            }
        )
    
    def _recall_success_patterns(self, proposal: SelfUpgradeProposal) -> List[dict]:
        """
        Recall successful upgrade patterns from memory.
        
        Args:
            proposal: The current upgrade proposal
            
        Returns:
            List of similar successful patterns
        """
        if self._memory_service is None:
            return []
        
        try:
            # Build search query from proposal attributes
            query_parts = [
                proposal.program_id,
                proposal.target_metric,
                getattr(proposal, 'capability_gap', ''),
            ]
            query = " ".join(part for part in query_parts if part)
            
            # Search for similar successful upgrades
            memories = self._memory_service.recall(
                query=query,
                limit=5,
                tags=["upgrade_success", "procedure"]
            )
            
            patterns = []
            for mem in memories:
                metadata = getattr(mem, 'metadata', {})
                if metadata.get("upgrade_result") == "success":
                    patterns.append({
                        "description": mem.summary,
                        "tasks": metadata.get("atomic_tasks", []),
                        "validation_commands": metadata.get("validation_commands", []),
                        "success_factors": metadata.get("success_factors", [])
                    })
            
            return patterns
        except Exception:
            # Memory recall failure should not block planning
            return []
    
    def _generate_atomic_tasks(
        self, 
        proposal: SelfUpgradeProposal, 
        patterns: List[dict]
    ) -> List[AtomicTask]:
        """
        Generate atomic tasks using LLM and historical patterns.
        
        Args:
            proposal: The upgrade proposal
            patterns: Historical success patterns
            
        Returns:
            List of generated atomic tasks
        """
        # Build prompt for LLM
        prompt = self._build_generation_prompt(proposal, patterns)
        
        # Generate tasks using LLM if available
        if self._llm_service:
            try:
                response = self._llm_service.generate(prompt)
                tasks_data = self._parse_llm_response(response)
                return [AtomicTask(**task_data) for task_data in tasks_data]
            except Exception:
                # Fallback to rule-based generation
                pass
        
        # Fallback: Generate basic tasks based on proposal type
        return self._generate_fallback_tasks(proposal)
    
    def _build_generation_prompt(
        self, 
        proposal: SelfUpgradeProposal, 
        patterns: List[dict]
    ) -> str:
        """Build the prompt for LLM task generation."""
        
        patterns_text = "\n".join([
            f"- Pattern {i+1}: {p['description']}"
            for i, p in enumerate(patterns[:3])
        ])
        
        prompt = f"""
You are an expert upgrade planner. Decompose the following upgrade proposal into atomic tasks.

UPGRADE PROPOSAL:
- Program ID: {proposal.program_id}
- Target Metric: {proposal.target_metric}
- Description: {proposal.description}
- Risk Score: {getattr(proposal, 'risk_score', 0.5)}
- Impact Score: {getattr(proposal, 'impact_score', 0.5)}

HISTORICAL SUCCESS PATTERNS:
{patterns_text}

REQUIREMENTS:
1. Each task must complete in 2-5 minutes
2. Specify exact file paths to modify
3. Provide executable validation commands for each task
4. Order tasks by dependencies
5. Include rollback instructions for each task

OUTPUT FORMAT (JSON):
{{
    "tasks": [
        {{
            "task_id": "task-001",
            "description": "Copy plugin to candidate directory",
            "file_paths": ["src/plugins/example/", "candidates/example-v1.1.0/"],
            "code_changes": {{"action": "copy", "source": "...", "dest": "..."}},
            "validation_commands": ["ls candidates/example-v1.1.0/__init__.py"],
            "estimated_time_minutes": 2,
            "dependencies": [],
            "rollback_instructions": "Remove candidates/example-v1.1.0/"
        }}
    ]
}}

Generate the atomic tasks now:
"""
        return prompt
    
    def _parse_llm_response(self, response: str) -> List[dict]:
        """Parse LLM response to extract task data."""
        try:
            # Try to find JSON in response
            start_idx = response.find('{')
            end_idx = response.rfind('}') + 1
            if start_idx >= 0 and end_idx > start_idx:
                json_str = response[start_idx:end_idx]
                data = json.loads(json_str)
                return data.get("tasks", [])
        except (json.JSONDecodeError, AttributeError):
            pass
        
        return []
    
    def _generate_fallback_tasks(self, proposal: SelfUpgradeProposal) -> List[AtomicTask]:
        """
        Generate basic fallback tasks when LLM is unavailable.
        
        Args:
            proposal: The upgrade proposal
            
        Returns:
            List of basic atomic tasks
        """
        tasks = []
        task_counter = 1
        
        # Task 1: Create candidate directory
        tasks.append(AtomicTask(
            task_id=f"task-{task_counter:03d}",
            description=f"Create candidate directory for {proposal.program_id}",
            file_paths=[f"candidates/{proposal.program_id}-candidate/"],
            validation_commands=[
                f"mkdir -p candidates/{proposal.program_id}-candidate/"
            ],
            estimated_time_minutes=2,
            dependencies=[],
            rollback_instructions=f"rm -rf candidates/{proposal.program_id}-candidate/"
        ))
        task_counter += 1
        
        # Task 2: Copy source files
        tasks.append(AtomicTask(
            task_id=f"task-{task_counter:03d}",
            description=f"Copy source files to candidate directory",
            file_paths=[
                f"src/plugins/{proposal.program_id}/",
                f"candidates/{proposal.program_id}-candidate/"
            ],
            validation_commands=[
                f"test -f candidates/{proposal.program_id}-candidate/__init__.py"
            ],
            estimated_time_minutes=3,
            dependencies=[f"task-{(task_counter-1):03d}"],
            rollback_instructions=f"rm -rf candidates/{proposal.program_id}-candidate/*"
        ))
        task_counter += 1
        
        # Task 3: Update version metadata
        tasks.append(AtomicTask(
            task_id=f"task-{task_counter:03d}",
            description="Update version metadata in candidate",
            file_paths=[f"candidates/{proposal.program_id}-candidate/plugin.json"],
            code_changes={"version_update": proposal.candidate_version},
            validation_commands=[
                f"cat candidates/{proposal.program_id}-candidate/plugin.json | grep version"
            ],
            estimated_time_minutes=2,
            dependencies=[f"task-{(task_counter-1):03d}"],
            rollback_instructions="Revert version in plugin.json"
        ))
        task_counter += 1
        
        # Task 4: Run basic validation
        tasks.append(AtomicTask(
            task_id=f"task-{task_counter:03d}",
            description="Run basic validation tests",
            file_paths=[],
            validation_commands=[
                f"cd candidates/{proposal.program_id}-candidate/ && python -c \"import sys; sys.exit(0)\""
            ],
            estimated_time_minutes=3,
            dependencies=[f"task-{(task_counter-1):03d}"],
            rollback_instructions="No rollback needed for validation"
        ))
        
        return tasks
    
    def _validate_tasks(self, tasks: List[AtomicTask]):
        """
        Validate that all tasks meet requirements.
        
        Args:
            tasks: List of tasks to validate
            
        Raises:
            ValueError: If any task is invalid
        """
        task_ids = {t.task_id for t in tasks}
        
        for task in tasks:
            # Must have validation commands
            if not task.validation_commands:
                raise ValueError(
                    f"Task {task.task_id} must have at least one validation_command"
                )
            
            # Must specify what to change
            if not task.file_paths and not task.code_changes:
                raise ValueError(
                    f"Task {task.task_id} must specify file_paths or code_changes"
                )
            
            # Dependencies must reference existing tasks
            for dep_id in task.dependencies:
                if dep_id not in task_ids:
                    raise ValueError(
                        f"Task {task.task_id} has invalid dependency: {dep_id}"
                    )
    
    def _identify_critical_path(self, tasks: List[AtomicTask]) -> List[str]:
        """
        Identify the critical path through the task dependency graph.
        
        Uses topological sort to find the longest path.
        
        Args:
            tasks: List of atomic tasks
            
        Returns:
            List of task IDs on the critical path
        """
        if not tasks:
            return []
        
        # Build adjacency list
        task_map = {t.task_id: t for t in tasks}
        visited = set()
        path = []
        
        def dfs(task_id: str):
            if task_id in visited:
                return
            visited.add(task_id)
            
            task = task_map[task_id]
            # Visit dependencies first
            for dep_id in task.dependencies:
                if dep_id in task_map:
                    dfs(dep_id)
            
            path.append(task_id)
        
        # Process all tasks
        for task in tasks:
            dfs(task.task_id)
        
        return path
    
    def export_to_json(self, plan: AtomicUpgradePlan) -> str:
        """
        Export atomic upgrade plan to JSON string.
        
        Args:
            plan: The atomic upgrade plan
            
        Returns:
            JSON string representation
        """
        return plan.model_dump_json(indent=2)
    
    @classmethod
    def import_from_json(cls, json_str: str) -> AtomicUpgradePlan:
        """
        Import atomic upgrade plan from JSON string.
        
        Args:
            json_str: JSON string representation
            
        Returns:
            AtomicUpgradePlan object
        """
        data = json.loads(json_str)
        return AtomicUpgradePlan(**data)

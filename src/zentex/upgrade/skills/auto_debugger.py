"""
Automated Root Cause Analyzer - Performs systematic failure analysis.

Inspired by Superpowers' systematic-debugging skill, this module provides
automated four-phase root cause analysis for upgrade failures without
requiring human intervention.

Phases:
1. Reproduce - Extract reproduction steps from audit logs
2. Isolate - Identify the scope of the failure
3. Identify - Determine the root cause using LLM analysis
4. Verify - Generate verification plan for the fix
"""

from __future__ import annotations

from typing import List, Optional
from datetime import datetime

from pydantic import BaseModel, Field


class RootCauseAnalysis(BaseModel):
    """Complete root cause analysis result."""
    
    analysis_id: str = Field(description="Unique analysis identifier")
    timestamp: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="When the analysis was performed"
    )
    
    # Phase 1: Reproduction
    reproduction_steps: List[str] = Field(
        default_factory=list,
        description="Steps to reproduce the failure"
    )
    
    # Phase 2: Isolation
    isolated_scope: List[str] = Field(
        default_factory=list,
        description="Components/modules where the issue is isolated"
    )
    affected_functions: List[str] = Field(
        default_factory=list,
        description="Specific functions or methods affected"
    )
    
    # Phase 3: Identification
    immediate_cause: str = Field(
        default="",
        description="The direct cause of the failure"
    )
    root_cause: str = Field(
        default="",
        description="The underlying root cause"
    )
    triggering_condition: str = Field(
        default="",
        description="Conditions that triggered the failure"
    )
    confidence_level: float = Field(
        ge=0.0,
        le=1.0,
        default=0.5,
        description="Confidence in the root cause identification (0-1)"
    )
    
    # Phase 4: Verification
    verification_plan: List[str] = Field(
        default_factory=list,
        description="Steps to verify the fix"
    )
    prevention_hint: str = Field(
        default="",
        description="Suggestions to prevent similar failures"
    )
    
    # Metadata
    analysis_metadata: dict = Field(
        default_factory=dict,
        description="Additional metadata about the analysis"
    )


class AutomatedRootCauseAnalyzer:
    """
    Performs automated four-phase root cause analysis on upgrade failures.
    
    This analyzer systematically investigates failures to identify root causes
    and generate actionable prevention hints without human intervention.
    
    Example:
        >>> analyzer = AutomatedRootCauseAnalyzer()
        >>> failed_record = UpgradeManagementRecord(...)
        >>> analysis = analyzer.analyze_failure(failed_record)
        >>> print(f"Root cause: {analysis.root_cause}")
    """
    
    def __init__(self, llm_service=None):
        """
        Initialize the root cause analyzer.
        
        Args:
            llm_service: LLM service for intelligent analysis
        """
        self._llm_service = llm_service
    
    def analyze_failure(self, failed_record) -> RootCauseAnalysis:
        """
        Perform comprehensive root cause analysis on a failed upgrade record.
        
        Args:
            failed_record: UpgradeManagementRecord with failure information
            
        Returns:
            RootCauseAnalysis with detailed findings
        """
        from uuid import uuid4
        
        analysis_id = f"rca-{uuid4().hex[:8]}"
        
        # Phase 1: Extract reproduction steps
        reproduction_steps = self._extract_reproduction_steps(failed_record)
        
        # Phase 2: Isolate failure scope
        isolated_scope, affected_functions = self._isolate_failure_scope(failed_record)
        
        # Phase 3: Identify root cause
        immediate_cause, root_cause, triggering_condition, confidence = \
            self._identify_root_cause(failed_record, isolated_scope)
        
        # Phase 4: Generate verification plan
        verification_plan, prevention_hint = self._generate_verification_plan(
            root_cause, 
            failed_record
        )
        
        return RootCauseAnalysis(
            analysis_id=analysis_id,
            reproduction_steps=reproduction_steps,
            isolated_scope=isolated_scope,
            affected_functions=affected_functions,
            immediate_cause=immediate_cause,
            root_cause=root_cause,
            triggering_condition=triggering_condition,
            confidence_level=confidence,
            verification_plan=verification_plan,
            prevention_hint=prevention_hint,
            analysis_metadata={
                "failure_stage": getattr(failed_record, 'failure_stage', 'unknown'),
                "failure_code": getattr(failed_record, 'failure_code', 'unknown'),
                "target_kind": getattr(failed_record, 'target_kind', 'unknown'),
            }
        )
    
    def _extract_reproduction_steps(self, failed_record) -> List[str]:
        """
        Extract reproduction steps from failure audit trail.
        
        Args:
            failed_record: The failed upgrade record
            
        Returns:
            List of reproduction steps
        """
        steps = []
        
        # Step 1: Identify the upgrade target
        target_id = getattr(failed_record, 'target_id', 'unknown')
        target_kind = getattr(failed_record, 'target_kind', 'unknown')
        steps.append(f"Target: {target_kind.value if hasattr(target_kind, 'value') else target_kind} - {target_id}")
        
        # Step 2: Identify the failure stage
        failure_stage = getattr(failed_record, 'failure_stage', 'unknown')
        steps.append(f"Failure occurred during: {failure_stage}")
        
        # Step 3: Extract error message
        failure_reason = getattr(failed_record, 'failure_reason', '')
        if failure_reason:
            steps.append(f"Error: {failure_reason}")
        
        # Step 4: Extract stack trace if available
        payload = getattr(failed_record, 'payload', {})
        if isinstance(payload, dict):
            stack_trace = payload.get('stack_trace', '')
            if stack_trace:
                steps.append(f"Stack trace available: {len(stack_trace)} characters")
        
        # Step 5: Note the candidate version
        candidate_version = getattr(failed_record, 'candidate_version', 'unknown')
        steps.append(f"Candidate version: {candidate_version}")
        
        return steps
    
    def _isolate_failure_scope(self, failed_record) -> tuple[List[str], List[str]]:
        """
        Isolate the scope of the failure to specific components.
        
        Args:
            failed_record: The failed upgrade record
            
        Returns:
            Tuple of (isolated_scope, affected_functions)
        """
        isolated_scope = []
        affected_functions = []
        
        # Extract from failure stage
        failure_stage = getattr(failed_record, 'failure_stage', '')
        if failure_stage:
            isolated_scope.append(f"Stage: {failure_stage}")
        
        # Extract from error message
        failure_reason = getattr(failed_record, 'failure_reason', '')
        
        # Common patterns for isolation
        if 'import' in failure_reason.lower() or 'module' in failure_reason.lower():
            isolated_scope.append("Module import/dependency layer")
            affected_functions.append("import statements")
        
        if 'syntax' in failure_reason.lower():
            isolated_scope.append("Code syntax layer")
            affected_functions.append("parse/compile")
        
        if 'test' in failure_reason.lower() or 'assert' in failure_reason.lower():
            isolated_scope.append("Test validation layer")
            affected_functions.append("test execution")
        
        if 'permission' in failure_reason.lower() or 'access' in failure_reason.lower():
            isolated_scope.append("File system access layer")
            affected_functions.append("file I/O operations")
        
        # Extract from target kind
        target_kind = getattr(failed_record, 'target_kind', '')
        if target_kind:
            kind_value = target_kind.value if hasattr(target_kind, 'value') else str(target_kind)
            isolated_scope.append(f"Target type: {kind_value}")
        
        # If no specific isolation, use general scope
        if not isolated_scope:
            isolated_scope.append("General upgrade execution")
            affected_functions.append("upgrade workflow")
        
        return isolated_scope, affected_functions
    
    def _identify_root_cause(
        self, 
        failed_record, 
        isolated_scope: List[str]
    ) -> tuple[str, str, str, float]:
        """
        Identify the root cause using pattern matching and LLM analysis.
        
        Args:
            failed_record: The failed upgrade record
            isolated_scope: Isolated failure scope
            
        Returns:
            Tuple of (immediate_cause, root_cause, triggering_condition, confidence)
        """
        failure_reason = getattr(failed_record, 'failure_reason', '')
        failure_code = getattr(failed_record, 'failure_code', '')
        
        # Pattern-based root cause identification
        patterns = {
            'modulenotfound': {
                'immediate': 'Missing Python module or package',
                'root': 'Dependency not installed or incorrect import path',
                'trigger': 'Attempted to import non-existent module',
                'confidence': 0.9
            },
            'syntaxerror': {
                'immediate': 'Python syntax error in code',
                'root': 'Invalid Python syntax introduced during upgrade',
                'trigger': 'Code modification with syntax mistakes',
                'confidence': 0.95
            },
            'attributeerror': {
                'immediate': 'Accessing non-existent attribute or method',
                'root': 'API change or incorrect object usage',
                'trigger': 'Code expects different interface than provided',
                'confidence': 0.85
            },
            'typeerror': {
                'immediate': 'Type mismatch in function call or operation',
                'root': 'Incorrect data types passed to functions',
                'trigger': 'Type incompatibility between components',
                'confidence': 0.8
            },
            'keyerror': {
                'immediate': 'Dictionary key not found',
                'root': 'Missing configuration or data structure change',
                'trigger': 'Accessing non-existent dictionary key',
                'confidence': 0.85
            },
            'filenotfound': {
                'immediate': 'Required file not found',
                'root': 'File path incorrect or file not created',
                'trigger': 'Attempted to access non-existent file',
                'confidence': 0.9
            },
            'timeout': {
                'immediate': 'Operation exceeded time limit',
                'root': 'Performance degradation or infinite loop',
                'trigger': 'Long-running operation or deadlock',
                'confidence': 0.75
            },
            'security': {
                'immediate': 'Security policy violation detected',
                'root': 'Code attempted forbidden operation',
                'trigger': 'Security scan detected prohibited calls',
                'confidence': 0.95
            },
        }
        
        # Match patterns
        failure_lower = failure_reason.lower()
        matched_pattern = None
        
        for pattern_key, pattern_info in patterns.items():
            if pattern_key in failure_lower or pattern_key in failure_code.lower():
                matched_pattern = pattern_info
                break
        
        if matched_pattern:
            return (
                matched_pattern['immediate'],
                matched_pattern['root'],
                matched_pattern['trigger'],
                matched_pattern['confidence']
            )
        
        # Fallback: Use LLM for analysis if available
        if self._llm_service:
            try:
                return self._llm_identify_root_cause(failed_record, isolated_scope)
            except Exception:
                pass
        
        # Generic fallback
        return (
            f"Upgrade failed with error: {failure_reason[:100]}",
            "Unknown root cause - requires manual investigation",
            "Failure occurred during upgrade execution",
            0.3
        )
    
    def _llm_identify_root_cause(
        self, 
        failed_record, 
        isolated_scope: List[str]
    ) -> tuple[str, str, str, float]:
        """Use LLM to identify root cause when pattern matching fails."""
        
        failure_reason = getattr(failed_record, 'failure_reason', '')
        failure_stage = getattr(failed_record, 'failure_stage', '')
        payload = getattr(failed_record, 'payload', {})
        
        prompt = f"""
Analyze the following upgrade failure and identify the root cause.

FAILURE DETAILS:
- Stage: {failure_stage}
- Error: {failure_reason}
- Isolated Scope: {', '.join(isolated_scope)}
- Payload: {payload}

Please provide:
1. Immediate cause (what directly caused the failure)
2. Root cause (underlying reason)
3. Triggering condition (what triggered it)
4. Confidence level (0.0-1.0)

Output as JSON:
{{
    "immediate_cause": "...",
    "root_cause": "...",
    "triggering_condition": "...",
    "confidence": 0.85
}}
"""
        
        response = self._llm_service.generate(prompt)
        
        # Parse response (simplified)
        import json
        try:
            start_idx = response.find('{')
            end_idx = response.rfind('}') + 1
            if start_idx >= 0 and end_idx > start_idx:
                data = json.loads(response[start_idx:end_idx])
                return (
                    data.get('immediate_cause', 'Unknown'),
                    data.get('root_cause', 'Unknown'),
                    data.get('triggering_condition', 'Unknown'),
                    data.get('confidence', 0.5)
                )
        except Exception:
            pass
        
        raise ValueError("LLM analysis failed")
    
    def _generate_verification_plan(
        self, 
        root_cause: str, 
        failed_record
    ) -> tuple[List[str], str]:
        """
        Generate verification plan and prevention hints.
        
        Args:
            root_cause: Identified root cause
            failed_record: The failed upgrade record
            
        Returns:
            Tuple of (verification_plan, prevention_hint)
        """
        verification_plan = []
        prevention_hint = ""
        
        # Generate based on root cause patterns
        root_cause_lower = root_cause.lower()
        
        if 'dependency' in root_cause_lower or 'module' in root_cause_lower:
            verification_plan = [
                "Check requirements.txt or pyproject.toml for missing dependencies",
                "Run 'pip install -r requirements.txt' to install dependencies",
                "Verify import paths are correct",
                "Run unit tests to confirm dependency resolution"
            ]
            prevention_hint = (
                "Always validate dependencies before upgrade. "
                "Use virtual environments to isolate dependencies. "
                "Maintain a comprehensive requirements file."
            )
        
        elif 'syntax' in root_cause_lower:
            verification_plan = [
                "Run Python syntax checker: python -m py_compile <file>",
                "Use linter: flake8 or pylint",
                "Fix syntax errors identified",
                "Re-run tests after fixing"
            ]
            prevention_hint = (
                "Always run syntax checks before committing code changes. "
                "Use pre-commit hooks with linters. "
                "Enable IDE syntax highlighting and error detection."
            )
        
        elif 'api' in root_cause_lower or 'interface' in root_cause_lower:
            verification_plan = [
                "Review API documentation for changes",
                "Update code to match new API signatures",
                "Run integration tests",
                "Verify backward compatibility if needed"
            ]
            prevention_hint = (
                "Document all API changes. "
                "Maintain backward compatibility when possible. "
                "Use versioned APIs for breaking changes."
            )
        
        elif 'permission' in root_cause_lower or 'access' in root_cause_lower:
            verification_plan = [
                "Check file permissions: ls -la <path>",
                "Verify user has read/write access",
                "Update permissions if needed: chmod",
                "Test file operations after permission fix"
            ]
            prevention_hint = (
                "Validate file permissions before upgrade. "
                "Use proper permission management. "
                "Avoid hardcoding file paths."
            )
        
        elif 'security' in root_cause_lower:
            verification_plan = [
                "Review security scan results",
                "Remove or replace forbidden function calls",
                "Implement safe alternatives",
                "Re-run security scan to confirm fix"
            ]
            prevention_hint = (
                "Always scan code for security violations before upgrade. "
                "Avoid using os.system(), eval(), exec(). "
                "Follow principle of least privilege."
            )
        
        else:
            # Generic verification plan
            verification_plan = [
                "Review error message and stack trace",
                "Identify the failing component",
                "Create minimal reproduction case",
                "Test fix in isolated environment",
                "Run full test suite after fix"
            ]
            prevention_hint = (
                "Improve error handling and logging. "
                "Add more comprehensive tests. "
                "Implement better input validation."
            )
        
        return verification_plan, prevention_hint

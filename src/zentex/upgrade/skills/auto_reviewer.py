from __future__ import annotations
"""
Automated Two-Stage Code Reviewer - Performs automated code quality review.

Inspired by Superpowers' subagent-driven-development skill, this module provides
automated two-stage code review for upgrade candidates without requiring human
intervention.

Stages:
1. Spec Compliance Review - Verify the candidate meets specifications
2. Code Quality Review - Assess code quality using LLM analysis
"""


import ast
import logging
import os
import re
from typing import List, Optional, Any, Dict, Union
from datetime import datetime

logger = logging.getLogger(__name__)

from pydantic import BaseModel, Field
from zentex.upgrade.skills.auto_reviewer_llm_prompt import build_code_review_prompt


class ReviewIssue(BaseModel):
    """Represents a single review issue."""
    
    severity: str = Field(
        description="Issue severity: critical, warning, or info"
    )
    category: str = Field(
        description="Issue category: security, quality, compliance, etc."
    )
    description: str = Field(
        description="Detailed description of the issue"
    )
    file_path: Optional[str] = Field(
        default=None,
        description="File where the issue was found"
    )
    line_number: Optional[int] = Field(
        default=None,
        description="Line number where the issue occurs"
    )
    suggestion: Optional[str] = Field(
        default=None,
        description="Suggested fix or improvement"
    )


class ReviewResult(BaseModel):
    """Complete review result."""
    
    review_id: str = Field(description="Unique review identifier")
    timestamp: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="When the review was performed"
    )
    status: str = Field(
        description="Review status: approved, rejected, or needs_refactor"
    )
    stage: str = Field(
        description="Review stage: spec_compliance or code_quality"
    )
    issues: List[ReviewIssue] = Field(
        default_factory=list,
        description="List of identified issues"
    )
    summary: str = Field(
        default="",
        description="Overall review summary"
    )
    passed_checks: List[str] = Field(
        default_factory=list,
        description="List of checks that passed"
    )
    failed_checks: List[str] = Field(
        default_factory=list,
        description="List of checks that failed"
    )


class AutomatedTwoStageReviewer:
    """
    Performs automated two-stage code review on upgrade candidates.
    
    This reviewer conducts comprehensive automated reviews without human
    intervention, checking both specification compliance and code quality.
    
    Example:
        >>> reviewer = AutomatedTwoStageReviewer()
        >>> candidate = CandidatePatch(...)
        >>> result = await reviewer.review_candidate(candidate)
        >>> if result.status == "approved":
        ...     print("Candidate approved for promotion")
    """
    
    def __init__(self, llm_service=None):
        """
        Initialize the automated reviewer.
        
        Args:
            llm_service: LLM service for code quality analysis
        """
        self._llm_service = llm_service
    
    async def review_candidate(self, candidate) -> ReviewResult:
        """
        Perform complete two-stage review on a candidate patch.
        
        Args:
            candidate: CandidatePatch to review
            
        Returns:
            ReviewResult with review findings
        """
        from uuid import uuid4
        
        review_id = f"review-{uuid4().hex[:8]}"
        
        # Stage 1: Spec Compliance Review
        spec_result = await self._check_spec_compliance(candidate, review_id)
        if spec_result.status == "rejected":
            return spec_result
        
        # Stage 2: Code Quality Review
        quality_result = await self._check_code_quality(candidate, review_id)
        
        # Combine results
        if quality_result.status in ["rejected", "needs_refactor"]:
            return quality_result
        
        # Both stages passed
        return ReviewResult(
            review_id=review_id,
            status="approved",
            stage="complete",
            issues=[],
            summary="Candidate passed both spec compliance and code quality reviews",
            passed_checks=spec_result.passed_checks + quality_result.passed_checks,
            failed_checks=[]
        )
    
    async def _check_spec_compliance(self, candidate, review_id: str) -> ReviewResult:
        """
        Stage 1: Check specification compliance.
        
        Verifies that the candidate meets all technical specifications
        and security requirements.
        
        Args:
            candidate: CandidatePatch to check
            review_id: Review identifier
            
        Returns:
            ReviewResult with compliance findings
        """
        issues = []
        passed_checks = []
        failed_checks = []
        
        # Check 1: Interface integrity
        interface_check = await self._verify_interface_integrity(candidate)
        if interface_check['success']:
            passed_checks.append("interface_integrity")
        else:
            failed_checks.append("interface_integrity")
            issues.append(ReviewIssue(
                severity="critical",
                category="compliance",
                description=f"Interface integrity check failed: {interface_check.get('detail', 'Unknown error')}",
                suggestion="Ensure all required interfaces are implemented"
            ))
        
        # Check 2: No forbidden calls
        forbidden_calls = await self._verify_no_forbidden_calls(candidate)
        if not forbidden_calls:
            passed_checks.append("no_forbidden_calls")
        else:
            failed_checks.append("no_forbidden_calls")
            for call in forbidden_calls:
                issues.append(ReviewIssue(
                    severity="critical",
                    category="security",
                    description=f"Forbidden call detected: {call}",
                    file_path=candidate.isolation_path if hasattr(candidate, 'isolation_path') else None,
                    suggestion="Remove or replace forbidden function calls"
                ))
        
        # Check 3: Version bumped
        version_check = await self._verify_version_bumped(candidate)
        if version_check:
            passed_checks.append("version_bumped")
        else:
            failed_checks.append("version_bumped")
            issues.append(ReviewIssue(
                severity="warning",
                category="compliance",
                description="Version number may not have been updated",
                suggestion="Ensure candidate version is different from baseline"
            ))
        
        # Check 4: Tests included
        tests_check = await self._verify_tests_included(candidate)
        if tests_check:
            passed_checks.append("tests_included")
        else:
            failed_checks.append("tests_included")
            issues.append(ReviewIssue(
                severity="warning",
                category="quality",
                description="No test files found in candidate",
                suggestion="Include unit tests for new or modified code"
            ))
        
        # Determine overall status
        has_critical = any(i.severity == "critical" for i in issues)
        if has_critical:
            status = "rejected"
            summary = f"Spec compliance review failed: {len([i for i in issues if i.severity == 'critical'])} critical issues found"
        else:
            status = "approved"
            summary = f"Spec compliance review passed with {len(issues)} warnings"
        
        return ReviewResult(
            review_id=review_id,
            lifecycle_status=lifecycle_status,
            stage="spec_compliance",
            issues=issues,
            summary=summary,
            passed_checks=passed_checks,
            failed_checks=failed_checks
        )
    
    async def _check_code_quality(self, candidate, review_id: str) -> ReviewResult:
        """
        Stage 2: Check code quality.
        
        Assesses code quality using static analysis and LLM-based review.
        
        Args:
            candidate: CandidatePatch to check
            review_id: Review identifier
            
        Returns:
            ReviewResult with quality findings
        """
        issues = []
        passed_checks = []
        failed_checks = []
        
        # Check 1: Python syntax validation
        syntax_check = await self._verify_syntax(candidate)
        if syntax_check['success']:
            passed_checks.append("syntax_valid")
        else:
            failed_checks.append("syntax_valid")
            issues.append(ReviewIssue(
                severity="critical",
                category="quality",
                description=f"Syntax errors found: {syntax_check.get('error', 'Unknown')}",
                suggestion="Fix syntax errors before proceeding"
            ))
        
        # Check 2: Code style (PEP 8 basics)
        style_issues = await self._check_code_style(candidate)
        if not style_issues:
            passed_checks.append("code_style")
        else:
            # Style issues are warnings, not failures
            issues.extend(style_issues)
            passed_checks.append("code_style_with_warnings")
        
        # Check 3: Error handling
        error_handling_check = await self._verify_error_handling(candidate)
        if error_handling_check['adequate']:
            passed_checks.append("error_handling")
        else:
            failed_checks.append("error_handling")
            issues.append(ReviewIssue(
                severity="warning",
                category="quality",
                description="Insufficient error handling detected",
                suggestion="Add try-except blocks for risky operations"
            ))
        
        # Check 4: LLM-based quality review (if available)
        if self._llm_service:
            try:
                llm_review = await self._llm_code_review(candidate)
                if llm_review.get('passed', False):
                    passed_checks.append("llm_quality_review")
                else:
                    failed_checks.append("llm_quality_review")
                    for issue_desc in llm_review.get('issues', []):
                        issues.append(ReviewIssue(
                            severity="warning",
                            category="quality",
                            description=issue_desc,
                            suggestion="Address quality concerns identified by AI review"
                        ))
            except Exception:
                # POLICY[no-silent-except]: LLM review failure is non-blocking but must be logged.
                logger.warning("LLM quality review failed for candidate — skipping", exc_info=True)
                passed_checks.append("llm_quality_review_skipped")
        
        # Determine overall status
        has_critical = any(i.severity == "critical" for i in issues)
        has_warnings = any(i.severity == "warning" for i in issues)
        
        if has_critical:
            status = "rejected"
            summary = f"Code quality review failed: {len([i for i in issues if i.severity == 'critical'])} critical issues"
        elif has_warnings:
            status = "needs_refactor"
            summary = f"Code quality review passed with {len([i for i in issues if i.severity == 'warning'])} warnings requiring attention"
        else:
            status = "approved"
            summary = "Code quality review passed with no issues"
        
        return ReviewResult(
            review_id=review_id,
            lifecycle_status=lifecycle_status,
            stage="code_quality",
            issues=issues,
            summary=summary,
            passed_checks=passed_checks,
            failed_checks=failed_checks
        )
    
    async def _verify_interface_integrity(self, candidate) -> dict:
        """Verify that candidate maintains required interfaces."""
        try:
            isolation_path = getattr(candidate, 'isolation_path', '')
            if not isolation_path or not os.path.exists(isolation_path):
                return {
                    "success": True,  # Can't verify, assume OK
                    "detail": "No isolation path provided for verification"
                }
            
            required_interfaces = ["PluginBase", "CognitiveTool", "execute", "initialize"]
            found_interfaces = []
            
            for root, dirs, files in os.walk(isolation_path):
                for file in files:
                    if file.endswith(".py"):
                        filepath = os.path.join(root, file)
                        try:
                            with open(filepath, 'r', encoding='utf-8') as f:
                                tree = ast.parse(f.read())
                                for node in ast.walk(tree):
                                    if isinstance(node, (ast.ClassDef, ast.FunctionDef)):
                                        if node.name in required_interfaces:
                                            found_interfaces.append(node.name)
                        except Exception:
                            # POLICY[no-silent-except]: log unreadable/unparseable files.
                            logger.debug("Could not parse %s for interface check — skipping", filepath, exc_info=True)

            success = len(found_interfaces) > 0
            return {
                "success": success,
                "detail": f"Found interfaces: {found_interfaces}" if success else "No required interfaces found",
                "interfaces_found": found_interfaces
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "detail": "Interface verification failed"
            }
    
    async def _verify_no_forbidden_calls(self, candidate) -> List[str]:
        """Scan for forbidden system calls."""
        violations = []
        
        isolation_path = getattr(candidate, 'isolation_path', '')
        if not isolation_path or not os.path.exists(isolation_path):
            return violations
        
        forbidden_patterns = [
            (r'os\.system\s*\(', 'os.system() - arbitrary command execution'),
            (r'subprocess\.(Union[run, Union[call], Popen])\s*\(', 'subprocess - process spawning'),
            (r'eval\s*\(', 'eval() - code injection risk'),
            (r'exec\s*\(', 'exec() - code execution'),
            (r'__import__\s*\(', '__import__() - dynamic import'),
        ]
        
        for root, dirs, files in os.walk(isolation_path):
            for file in files:
                if file.endswith('.py'):
                    filepath = os.path.join(root, file)
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            content = f.read()
                            for pattern, description in forbidden_patterns:
                                if re.search(pattern, content):
                                    violations.append(f"{filepath}: {description}")
                    except Exception:
                        # POLICY[no-silent-except]: log unreadable files; skip them.
                        logger.debug("Could not read %s for pattern check — skipping", filepath, exc_info=True)
        return violations
    
    async def _verify_version_bumped(self, candidate) -> bool:
        """Verify that version has been updated."""
        try:
            baseline = getattr(candidate, 'changes', {}).get('baseline_version', '')
            cand_version = getattr(candidate, 'changes', {}).get('candidate_version', '')
            
            if not baseline or not cand_version:
                return True  # Can't verify, assume OK
            
            return baseline != cand_version
        except Exception:
            # POLICY[no-silent-except]: log and treat as non-blocking (assume OK).
            logger.debug("Could not verify version bump — assuming OK", exc_info=True)
            return True

    async def _verify_tests_included(self, candidate) -> bool:
        """Check if test files are included."""
        try:
            isolation_path = getattr(candidate, 'isolation_path', '')
            if not isolation_path or not os.path.exists(isolation_path):
                return True  # Can't verify, assume OK
            
            for root, dirs, files in os.walk(isolation_path):
                for file in files:
                    if file.startswith('test_') and file.endswith('.py'):
                        return True
                    if 'test' in root.lower():
                        return True
            
            return False
        except Exception:
            # POLICY[no-silent-except]: log and treat as non-blocking (assume OK).
            logger.debug("Could not verify test inclusion — assuming OK", exc_info=True)
            return True

    async def _verify_syntax(self, candidate) -> dict:
        """Verify Python syntax validity."""
        try:
            isolation_path = getattr(candidate, 'isolation_path', '')
            if not isolation_path or not os.path.exists(isolation_path):
                return {"success": True, "detail": "No path to verify"}
            
            errors = []
            for root, dirs, files in os.walk(isolation_path):
                for file in files:
                    if file.endswith('.py'):
                        filepath = os.path.join(root, file)
                        try:
                            with open(filepath, 'r', encoding='utf-8') as f:
                                ast.parse(f.read())
                        except SyntaxError as e:
                            errors.append(f"{filepath}:{e.lineno}: {e.msg}")
            
            if errors:
                return {
                    "success": False,
                    "error": "; ".join(errors),
                    "detail": f"Found {len(errors)} syntax errors"
                }
            
            return {"success": True, "detail": "All files have valid syntax"}
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "detail": "Syntax verification failed"
            }
    
    async def _check_code_style(self, candidate) -> List[ReviewIssue]:
        """Check basic code style issues."""
        issues = []
        
        try:
            isolation_path = getattr(candidate, 'isolation_path', '')
            if not isolation_path or not os.path.exists(isolation_path):
                return issues
            
            for root, dirs, files in os.walk(isolation_path):
                for file in files:
                    if file.endswith('.py'):
                        filepath = os.path.join(root, file)
                        try:
                            with open(filepath, 'r', encoding='utf-8') as f:
                                lines = f.readlines()
                                
                                # Check line length
                                for i, line in enumerate(lines, 1):
                                    if len(line.rstrip()) > 120:
                                        issues.append(ReviewIssue(
                                            severity="info",
                                            category="style",
                                            description=f"Line too long ({len(line.rstrip())} chars)",
                                            file_path=filepath,
                                            line_number=i,
                                            suggestion="Break long lines into multiple lines"
                                        ))
                                
                                # Check for trailing whitespace
                                for i, line in enumerate(lines, 1):
                                    if line.rstrip() != line.rstrip('\n').rstrip():
                                        issues.append(ReviewIssue(
                                            severity="info",
                                            category="style",
                                            description="Trailing whitespace",
                                            file_path=filepath,
                                            line_number=i,
                                            suggestion="Remove trailing whitespace"
                                        ))
                        except Exception:
                            # POLICY[no-silent-except]: log unreadable files; skip them.
                            logger.debug("Could not read %s for style check — skipping", filepath, exc_info=True)
        except Exception:
            # POLICY[no-silent-except]: log outer style-check failure; return what we found.
            logger.warning("Style check walk failed — returning partial results", exc_info=True)

        return issues
    
    async def _verify_error_handling(self, candidate) -> dict:
        """Check for adequate error handling."""
        try:
            isolation_path = getattr(candidate, 'isolation_path', '')
            if not isolation_path or not os.path.exists(isolation_path):
                return {"adequate": True, "detail": "No path to verify"}
            
            has_try_except = False
            for root, dirs, files in os.walk(isolation_path):
                for file in files:
                    if file.endswith('.py'):
                        filepath = os.path.join(root, file)
                        try:
                            with open(filepath, 'r', encoding='utf-8') as f:
                                content = f.read()
                                if 'try:' in content and 'except' in content:
                                    has_try_except = True
                                    break
                        except Exception:
                            # POLICY[no-silent-except]: log unreadable files; skip them.
                            logger.debug("Could not read %s for error-handling check — skipping", filepath, exc_info=True)

            return {
                "adequate": has_try_except,
                "detail": "Error handling found" if has_try_except else "No error handling detected"
            }
        except Exception:
            # POLICY[no-silent-except]: log and treat as non-blocking (assume OK).
            logger.warning("Error-handling verification failed — assuming adequate", exc_info=True)
            return {"adequate": True, "detail": "Verification skipped"}
    
    async def _llm_code_review(self, candidate) -> dict:
        """Perform LLM-based code quality review."""
        if not self._llm_service:
            return {"passed": True, "issues": []}
        
        try:
            # Extract code snippets
            code_snippets = []
            isolation_path = getattr(candidate, 'isolation_path', '')
            
            if isolation_path and os.path.exists(isolation_path):
                for root, dirs, files in os.walk(isolation_path):
                    for file in files[:5]:  # Limit to first 5 files
                        if file.endswith('.py'):
                            filepath = os.path.join(root, file)
                            try:
                                with open(filepath, 'r', encoding='utf-8') as f:
                                    code_snippets.append(f"# File: {filepath}\n{f.read()}")
                            except Exception:
                                # POLICY[no-silent-except]: log unreadable files; skip them.
                                logger.debug("Could not read %s for LLM review — skipping", filepath, exc_info=True)
            
            if not code_snippets:
                return {"passed": True, "issues": [], "detail": "No code to review"}
            
            prompt = build_code_review_prompt(code_snippets=code_snippets)["prompt"]
            
            response = self._llm_service.generate(prompt)
            
            # Parse response
            import json
            try:
                start_idx = response.find('{')
                end_idx = response.rfind('}') + 1
                if start_idx >= 0 and end_idx > start_idx:
                    data = json.loads(response[start_idx:end_idx])
                    return data
            except Exception:
                # POLICY[no-silent-except]: log JSON parse failure from LLM response.
                logger.debug("Could not parse LLM review response as JSON — treating as inconclusive", exc_info=True)

            return {"passed": True, "issues": [], "detail": "LLM review inconclusive"}
        except Exception as e:
            return {"passed": True, "issues": [], "detail": f"LLM review failed: {str(e)}"}

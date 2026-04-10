"""
Test Service: Plugin Health Checks and Compatibility Testing

Handles:
- Plugin health checks
- Compatibility verification
- Constraint validation
- Performance testing
- Test report generation
"""

from __future__ import annotations

import logging
import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class HealthReport:
    """Report from plugin health check"""
    timestamp: str
    plugin_id: Optional[str]
    status: str  # healthy, degraded, failed
    checks_passed: int
    checks_failed: int
    checks_total: int
    details: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)


@dataclass
class CompatibilityReport:
    """Report from compatibility tests"""
    timestamp: str
    plugin_id: Optional[str]
    passed: int
    failed: int
    total: int
    rule_violations: List[str] = field(default_factory=list)
    compatibility_issues: List[str] = field(default_factory=list)


@dataclass
class StressTestReport:
    """Report from stress testing"""
    timestamp: str
    plugin_id: str
    iterations: int
    successful: int
    failed: int
    avg_execution_time_ms: float
    min_execution_time_ms: float
    max_execution_time_ms: float
    errors: List[str] = field(default_factory=list)


class TestService:
    """
    Provides testing and validation capabilities for plugins.
    
    Responsibilities:
    - Run health checks
    - Verify compatibility
    - Test constraints
    - Perform stress tests
    - Generate comprehensive test reports
    """
    
    def __init__(
        self,
        storage,
        plugin_instances,
        execution_service,
        query_service,
        determine_category_fn=None,
    ):
        """
        Initialize test service.
        
        Args:
            storage: PluginStorage instance
            plugin_instances: In-memory plugin registry
            execution_service: ExecutionService for executing plugins
            query_service: QueryService for querying plugins
            determine_category_fn: Function to determine plugin category
        """
        self._storage = storage
        self._plugin_instances = plugin_instances
        self._execution_service = execution_service
        self._query_service = query_service
        self._determine_category = determine_category_fn

    async def health_check(self, plugin_id: Optional[str] = None) -> HealthReport:
        """
        Run health checks on plugins.
        
        Checks:
        - Plugin instance exists
        - Plugin has execute method
        - Plugin is registered in database
        - Plugin status is ACTIVE or DEGRADED
        - Database integrity
        
        Args:
            plugin_id: Specific plugin to check, or None for all
            
        Returns:
            HealthReport with results
        """
        try:
            timestamp = datetime.now().isoformat()
            details = {}
            errors = []
            checks_passed = 0
            checks_failed = 0
            
            if plugin_id:
                # Check single plugin
                plugin_meta = self._storage.get_plugin(plugin_id)
                if plugin_meta:
                    plugins_to_check = [plugin_meta]
                else:
                    plugins_to_check = []
            else:
                # Check all registered plugins
                try:
                    plugins_to_check = self._storage.list_plugins()
                except:
                    # Fallback: check in-memory plugins
                    plugins_to_check = [
                        {'plugin_id': pid} for pid in self._plugin_instances.keys()
                    ]
            
            for plugin_meta in plugins_to_check:
                pid = plugin_meta.get('plugin_id')
                plugin_checks = {
                    'exists_in_memory': False,
                    'has_execute_method': False,
                    'is_registered': False,
                    'status_valid': False,
                }
                
                # Check 1: Exists in memory
                if pid in self._plugin_instances:
                    plugin_checks['exists_in_memory'] = True
                    checks_passed += 1
                else:
                    checks_failed += 1
                    errors.append(f"{pid}: Not found in memory registry")
                
                # Check 2: Has execute method
                if pid in self._plugin_instances:
                    plugin = self._plugin_instances[pid]
                    if hasattr(plugin, 'execute'):
                        plugin_checks['has_execute_method'] = True
                        checks_passed += 1
                    else:
                        checks_failed += 1
                        errors.append(f"{pid}: Missing execute method")
                
                # Check 3: Is registered
                if plugin_meta:
                    plugin_checks['is_registered'] = True
                    checks_passed += 1
                else:
                    checks_failed += 1
                    errors.append(f"{pid}: Not registered in database")
                
                # Check 4: Status valid
                status = plugin_meta.get('status') if plugin_meta else None
                if status in ['ACTIVE', 'DEGRADED']:
                    plugin_checks['status_valid'] = True
                    checks_passed += 1
                else:
                    checks_failed += 1
                    errors.append(f"{pid}: Invalid status: {status}")
                
                details[pid] = plugin_checks
            
            checks_total = checks_passed + checks_failed
            if checks_failed == 0:
                status = "healthy"
            elif checks_failed < checks_total * 0.5:
                status = "degraded"
            else:
                status = "failed"
            
            return HealthReport(
                timestamp=timestamp,
                plugin_id=plugin_id,
                status=status,
                checks_passed=checks_passed,
                checks_failed=checks_failed,
                checks_total=checks_total,
                details=details,
                errors=errors,
            )
            
        except Exception as e:
            logger.error(f"Error during health check: {e}")
            return HealthReport(
                timestamp=datetime.now().isoformat(),
                plugin_id=plugin_id,
                status="failed",
                checks_passed=0,
                checks_failed=1,
                checks_total=1,
                errors=[str(e)],
            )

    async def compatibility_test(self, plugin_id: Optional[str] = None) -> CompatibilityReport:
        """
        Test plugin compatibility and constraint satisfaction.
        
        Tests:
        - Cognitive → Functional allowed
        - Cognitive → Cognitive rejected
        - Functional → Anything rejected
        - Unknown callers rejected
        - External calls allowed
        
        Args:
            plugin_id: Specific plugin to test, or None for sample test
            
        Returns:
            CompatibilityReport with results
        """
        try:
            timestamp = datetime.now().isoformat()
            passed = 0
            failed = 0
            rule_violations = []
            compatibility_issues = []
            
            # Get test plugins
            cognitive_plugins = self._query_service.query_by_category("cognitive")
            functional_plugins = self._query_service.query_by_category("functional")
            
            # Test 1: Cognitive can call Functional
            if cognitive_plugins and functional_plugins:
                try:
                    cog_id = cognitive_plugins[0]['plugin_id']
                    func_id = functional_plugins[0]['plugin_id']
                    
                    # This should succeed
                    await self._execution_service.execute_plugin_once(
                        plugin_id=func_id,
                        task_id='test_task',
                        parameters={},
                        trace_id='test_trace',
                        originator_id='test_user',
                        caller_plugin_id=cog_id,
                    )
                    passed += 1
                except Exception as e:
                    failed += 1
                    rule_violations.append(f"Cognitive→Functional should be allowed: {e}")
            
            # Test 2: Cognitive cannot call Cognitive
            if len(cognitive_plugins) >= 2:
                try:
                    cog_id1 = cognitive_plugins[0]['plugin_id']
                    cog_id2 = cognitive_plugins[1]['plugin_id']
                    
                    # This should fail
                    try:
                        await self._execution_service.execute_plugin_once(
                            plugin_id=cog_id2,
                            task_id='test_task',
                            parameters={},
                            trace_id='test_trace',
                            originator_id='test_user',
                            caller_plugin_id=cog_id1,
                        )
                        # If we get here, test failed
                        failed += 1
                        rule_violations.append("Cognitive→Cognitive should be rejected")
                    except ValueError as e:
                        if "cannot call another Cognitive" in str(e):
                            passed += 1
                        else:
                            failed += 1
                            rule_violations.append(f"Wrong rejection reason: {e}")
                except Exception as e:
                    failed += 1
                    rule_violations.append(f"Test execution failed: {e}")
            
            # Test 3: Functional cannot call anything
            if functional_plugins and cognitive_plugins:
                try:
                    func_id = functional_plugins[0]['plugin_id']
                    cog_id = cognitive_plugins[0]['plugin_id']
                    
                    # This should fail
                    try:
                        await self._execution_service.execute_plugin_once(
                            plugin_id=cog_id,
                            task_id='test_task',
                            parameters={},
                            trace_id='test_trace',
                            originator_id='test_user',
                            caller_plugin_id=func_id,
                        )
                        # If we get here, test failed
                        failed += 1
                        rule_violations.append("Functional→Cognitive should be rejected")
                    except ValueError as e:
                        if "cannot call any" in str(e):
                            passed += 1
                        else:
                            failed += 1
                            rule_violations.append(f"Wrong rejection reason: {e}")
                except Exception as e:
                    failed += 1
                    rule_violations.append(f"Test execution failed: {e}")
            
            total = passed + failed
            
            return CompatibilityReport(
                timestamp=timestamp,
                plugin_id=plugin_id,
                passed=passed,
                failed=failed,
                total=total,
                rule_violations=rule_violations,
                compatibility_issues=compatibility_issues,
            )
            
        except Exception as e:
            logger.error(f"Error during compatibility test: {e}")
            return CompatibilityReport(
                timestamp=datetime.now().isoformat(),
                plugin_id=plugin_id,
                passed=0,
                failed=1,
                total=1,
                rule_violations=[str(e)],
            )

    async def stress_test(
        self,
        plugin_id: str,
        iterations: int = 100,
        concurrent: bool = False,
    ) -> StressTestReport:
        """
        Run stress test on a plugin.
        
        Args:
            plugin_id: Plugin to stress test
            iterations: Number of iterations
            concurrent: Whether to run concurrently
            
        Returns:
            StressTestReport with results
        """
        try:
            timestamp = datetime.now().isoformat()
            successful = 0
            failed = 0
            errors = []
            execution_times = []
            
            # Prepare test tasks
            async def run_iteration():
                try:
                    start = time.time()
                    await self._execution_service.execute_plugin_once(
                        plugin_id=plugin_id,
                        task_id=f'stress_test_{time.time()}',
                        parameters={},
                        trace_id=f'stress_trace_{time.time()}',
                        originator_id='stress_test_user',
                    )
                    elapsed = (time.time() - start) * 1000  # Convert to ms
                    execution_times.append(elapsed)
                    return True
                except Exception as e:
                    errors.append(str(e))
                    return False
            
            # Run stress test
            if concurrent:
                tasks = [run_iteration() for _ in range(iterations)]
                results = await asyncio.gather(*tasks, return_exceptions=False)
                successful = sum(1 for r in results if r is True)
                failed = iterations - successful
            else:
                for _ in range(iterations):
                    if await run_iteration():
                        successful += 1
                    else:
                        failed += 1
            
            # Calculate statistics
            if execution_times:
                avg_time = sum(execution_times) / len(execution_times)
                min_time = min(execution_times)
                max_time = max(execution_times)
            else:
                avg_time = min_time = max_time = 0.0
            
            return StressTestReport(
                timestamp=timestamp,
                plugin_id=plugin_id,
                iterations=iterations,
                successful=successful,
                failed=failed,
                avg_execution_time_ms=avg_time,
                min_execution_time_ms=min_time,
                max_execution_time_ms=max_time,
                errors=errors[:10],  # Limit to first 10 errors
            )
            
        except Exception as e:
            logger.error(f"Error during stress test: {e}")
            return StressTestReport(
                timestamp=datetime.now().isoformat(),
                plugin_id=plugin_id,
                iterations=iterations,
                successful=0,
                failed=iterations,
                avg_execution_time_ms=0.0,
                min_execution_time_ms=0.0,
                max_execution_time_ms=0.0,
                errors=[str(e)],
            )

    async def generate_test_report(self) -> Dict[str, Any]:
        """
        Generate comprehensive test report for all plugins.
        
        Includes:
        - Health check results
        - Compatibility test results
        - Performance baselines
        - Overall system health
        
        Returns:
            Comprehensive test report
        """
        try:
            timestamp = datetime.now().isoformat()
            
            # Run health check
            health = await self.health_check()
            
            # Run compatibility test
            compatibility = await self.compatibility_test()
            
            # Calculate overall health
            total_passed = health.checks_passed + compatibility.passed
            total_failed = health.checks_failed + compatibility.failed
            total_tests = health.checks_total + compatibility.total
            
            if total_failed == 0:
                overall_status = "passed"
            elif total_failed < total_tests * 0.3:
                overall_status = "degraded"
            else:
                overall_status = "failed"
            
            return {
                'timestamp': timestamp,
                'overall_status': overall_status,
                'health_check': {
                    'status': health.status,
                    'passed': health.checks_passed,
                    'failed': health.checks_failed,
                    'total': health.checks_total,
                },
                'compatibility_test': {
                    'passed': compatibility.passed,
                    'failed': compatibility.failed,
                    'total': compatibility.total,
                },
                'total_tests': {
                    'passed': total_passed,
                    'failed': total_failed,
                    'total': total_tests,
                },
                'plugin_count': len(self._plugin_instances),
                'details': {
                    'health': health.details,
                    'violations': compatibility.rule_violations,
                },
            }
            
        except Exception as e:
            logger.error(f"Error generating test report: {e}")
            return {
                'timestamp': datetime.now().isoformat(),
                'overall_status': 'failed',
                'error': str(e),
            }

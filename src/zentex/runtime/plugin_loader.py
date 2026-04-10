"""
Parallel Plugin Loader

Purpose:
    Loads plugins in parallel using ThreadPoolExecutor to reduce cold start time.
    Provides timeout control and failure isolation.
    
Responsibilities:
    - Manage parallel plugin loading with configurable workers
    - Handle timeouts and failures gracefully
    - Track loading statistics and results
    - Provide detailed logging for debugging
    
Not Responsible For:
    - Plugin instantiation logic (delegated to PluginRegistry)
    - Dependency resolution between plugins
    - Plugin hot-reloading (separate module)
"""

import concurrent.futures
import logging
import time
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class PluginLoadStatus(Enum):
    """Plugin loading status."""
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass
class PluginLoadResult:
    """Result of plugin loading."""
    plugin_id: str
    status: PluginLoadStatus
    duration_ms: float
    error: str = ""
    plugin_instance: Any = None


class ParallelPluginLoader:
    """
    Parallel plugin loader with timeout and failure isolation.
    
    Features:
        - Multi-threaded parallel loading
        - Configurable timeout per plugin
        - Detailed statistics and logging
        - Graceful failure handling
    
    Usage:
        >>> loader = ParallelPluginLoader(
        ...     max_workers=4,
        ...     timeout_per_plugin=30
        ... )
        >>> results = loader.load_plugins_parallel(plugin_specs)
        >>> for plugin_id, result in results.items():
        ...     if result.status == PluginLoadStatus.SUCCESS:
        ...         register_plugin(result.plugin_instance)
    """
    
    def __init__(
        self,
        max_workers: int = 4,
        timeout_per_plugin: int = 30,
        on_plugin_loaded: Optional[Callable[[str, Any], None]] = None,
    ):
        self.max_workers = max_workers
        self.timeout_per_plugin = timeout_per_plugin
        self.on_plugin_loaded = on_plugin_loaded
        
        logger.info(
            f"ParallelPluginLoader initialized: "
            f"workers={max_workers}, timeout={timeout_per_plugin}s"
        )
    
    def load_plugins_parallel(
        self, 
        plugin_specs: List[dict]
    ) -> Dict[str, PluginLoadResult]:
        """
        Load multiple plugins in parallel.
        
        Args:
            plugin_specs: List of plugin specifications
        
        Returns:
            Dictionary mapping plugin_id to PluginLoadResult
        """
        results = {}
        
        if not plugin_specs:
            logger.info("No plugins to load")
            return results
        
        logger.info(f"Loading {len(plugin_specs)} plugins in parallel...")
        start_time = time.time()
        
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self.max_workers,
            thread_name_prefix="plugin-loader"
        ) as executor:
            # Submit all loading tasks
            future_to_spec = {
                executor.submit(
                    self._load_single_plugin_with_timeout,
                    spec
                ): spec
                for spec in plugin_specs
            }
            
            # Collect results
            for future in concurrent.futures.as_completed(future_to_spec):
                spec = future_to_spec[future]
                plugin_id = spec.get('plugin_id', 'unknown')
                
                try:
                    result = future.result(timeout=self.timeout_per_plugin)
                    results[plugin_id] = result
                    
                    if result.status == PluginLoadStatus.SUCCESS:
                        logger.info(
                            f"✅ Plugin loaded: {result.plugin_id} "
                            f"({result.duration_ms:.0f}ms)"
                        )
                        
                        # Call callback if provided
                        if self.on_plugin_loaded and result.plugin_instance:
                            try:
                                self.on_plugin_loaded(
                                    result.plugin_id,
                                    result.plugin_instance
                                )
                            except Exception as e:
                                logger.warning(
                                    f"Callback failed for {result.plugin_id}: {e}"
                                )
                    else:
                        logger.error(
                            f"❌ Plugin failed: {result.plugin_id} - "
                            f"{result.error}"
                        )
                
                except concurrent.futures.TimeoutError:
                    results[plugin_id] = PluginLoadResult(
                        plugin_id=plugin_id,
                        status=PluginLoadStatus.TIMEOUT,
                        duration_ms=self.timeout_per_plugin * 1000,
                        error=f"Timeout after {self.timeout_per_plugin}s",
                    )
                    logger.error(
                        f"⏱️  Plugin timeout: {plugin_id} "
                        f"(>{self.timeout_per_plugin}s)"
                    )
                
                except Exception as e:
                    results[plugin_id] = PluginLoadResult(
                        plugin_id=plugin_id,
                        status=PluginLoadStatus.FAILED,
                        duration_ms=0,
                        error=f"Execution error: {str(e)}",
                    )
                    logger.error(
                        f"❌ Plugin execution error: {plugin_id} - {e}",
                        exc_info=True
                    )
        
        total_time = time.time() - start_time
        
        # Statistics
        success_count = sum(
            1 for r in results.values() 
            if r.status == PluginLoadStatus.SUCCESS
        )
        failed_count = sum(
            1 for r in results.values()
            if r.status == PluginLoadStatus.FAILED
        )
        timeout_count = sum(
            1 for r in results.values()
            if r.status == PluginLoadStatus.TIMEOUT
        )
        
        logger.info(
            f"Plugin loading completed: "
            f"{success_count}/{len(plugin_specs)} succeeded, "
            f"{failed_count} failed, "
            f"{timeout_count} timed out, "
            f"total time: {total_time:.1f}s"
        )
        
        return results
    
    def _load_single_plugin_with_timeout(
        self, 
        spec: dict
    ) -> PluginLoadResult:
        """
        Load single plugin with timeout.
        
        Args:
            spec: Plugin specification
        
        Returns:
            PluginLoadResult with status and timing
        """
        plugin_id = spec.get('plugin_id', 'unknown')
        start_time = time.time()
        
        try:
            # Actual loading logic
            plugin_instance = self._instantiate_plugin(spec)
            
            duration_ms = (time.time() - start_time) * 1000
            
            return PluginLoadResult(
                plugin_id=plugin_id,
                status=PluginLoadStatus.SUCCESS,
                duration_ms=duration_ms,
                plugin_instance=plugin_instance,
            )
        
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            return PluginLoadResult(
                plugin_id=plugin_id,
                status=PluginLoadStatus.FAILED,
                duration_ms=duration_ms,
                error=str(e),
            )
    
    def _instantiate_plugin(self, spec: dict) -> Any:
        """
        Instantiate plugin from specification.
        
        This method should be overridden or configured to use the actual
        plugin registry/loading mechanism.
        
        Args:
            spec: Plugin specification dictionary
        
        Returns:
            Plugin instance
        
        Raises:
            Exception: If plugin instantiation fails
        """
        # Delegate to PluginRegistry
        from zentex.core.plugin_base import PluginRegistry
        
        registry = PluginRegistry.get_instance()
        return registry.load_plugin_from_spec(spec)

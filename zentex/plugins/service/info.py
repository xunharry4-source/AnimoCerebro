"""
Info Service: Plugin Documentation and Protocol Information

Handles:
- Plugin documentation retrieval
- Protocol/interface information
- Classification rules information
- Capability listing
- Compatibility matrix generation
"""

from __future__ import annotations

import logging
import inspect
from typing import Any, Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class InfoService:
    """
    Provides information about plugins.
    
    Responsibilities:
    - Extract and serve plugin documentation
    - Provide protocol/interface details
    - Explain classification rules
    - List plugin capabilities
    - Generate compatibility matrices
    """
    
    def __init__(self, storage, plugin_instances, query_service, determine_category_fn=None):
        """
        Initialize info service.
        
        Args:
            storage: PluginStorage instance
            plugin_instances: In-memory plugin registry
            query_service: QueryService for querying plugins
            determine_category_fn: Function to determine plugin category
        """
        self._storage = storage
        self._plugin_instances = plugin_instances
        self._query_service = query_service
        self._determine_category = determine_category_fn

    def get_plugin_documentation(self, plugin_id: str) -> Optional[str]:
        """
        Get documentation for a plugin.
        
        Extracts:
        - Docstring from plugin class
        - Docstring from execute method
        - Any configured help text
        
        Args:
            plugin_id: Plugin to get documentation for
            
        Returns:
            Documentation string or None if not found
        """
        try:
            # Try to get from plugin instance first
            if plugin_id in self._plugin_instances:
                plugin = self._plugin_instances[plugin_id]
                
                # Get class docstring
                class_doc = inspect.getdoc(plugin.__class__)
                
                # Get execute method docstring
                if hasattr(plugin, 'execute'):
                    method_doc = inspect.getdoc(plugin.execute)
                else:
                    method_doc = None
                
                # Combine documentation
                parts = []
                if class_doc:
                    parts.append(f"## {plugin_id}\n\n{class_doc}")
                if method_doc:
                    parts.append(f"### Execute Method\n\n{method_doc}")
                
                if parts:
                    return "\n\n".join(parts)
            
            # Fallback to stored documentation
            plugin_meta = self._storage.get_plugin(plugin_id)
            if plugin_meta and 'documentation' in plugin_meta:
                return plugin_meta['documentation']
            
            logger.warning(f"No documentation found for {plugin_id}")
            return None
            
        except Exception as e:
            logger.error(f"Error retrieving documentation for {plugin_id}: {e}")
            return None

    def get_plugin_protocol(self, plugin_id: str) -> Dict[str, Any]:
        """
        Get protocol/interface information for a plugin.
        
        Returns:
        - Method signatures
        - Parameter requirements
        - Return types
        - Supported methods (execute, process, run, handle)
        
        Args:
            plugin_id: Plugin to get protocol for
            
        Returns:
            Protocol dictionary
        """
        try:
            protocol = {
                'plugin_id': plugin_id,
                'methods': {},
                'primary_method': None,
            }
            
            if plugin_id not in self._plugin_instances:
                logger.warning(f"Plugin instance not found: {plugin_id}")
                return protocol
            
            plugin = self._plugin_instances[plugin_id]
            
            # Check for supported execution methods
            for method_name in ['execute', 'process', 'run', 'handle']:
                if hasattr(plugin, method_name):
                    method = getattr(plugin, method_name)
                    
                    try:
                        # Get method signature
                        sig = inspect.signature(method)
                        
                        # Extract parameter info
                        params = {}
                        for param_name, param in sig.parameters.items():
                            if param_name in ['self', 'cls']:
                                continue
                            
                            params[param_name] = {
                                'annotation': str(param.annotation) if param.annotation != inspect.Parameter.empty else 'Any',
                                'default': str(param.default) if param.default != inspect.Parameter.empty else None,
                                'kind': str(param.kind),
                            }
                        
                        protocol['methods'][method_name] = {
                            'signature': str(sig),
                            'parameters': params,
                            'return_annotation': str(sig.return_annotation) if sig.return_annotation != inspect.Signature.empty else 'Any',
                            'docstring': inspect.getdoc(method),
                        }
                        
                        # Set primary method (first found)
                        if not protocol['primary_method']:
                            protocol['primary_method'] = method_name
                    
                    except Exception as e:
                        logger.debug(f"Could not extract signature for {method_name}: {e}")
            
            return protocol
            
        except Exception as e:
            logger.error(f"Error retrieving protocol for {plugin_id}: {e}")
            return {'plugin_id': plugin_id, 'error': str(e)}

    def get_plugin_rules(self, plugin_id: str) -> Dict[str, Any]:
        """
        Get classification and execution rules for a plugin.
        
        Returns:
        - Plugin category (cognitive, functional, sensory, etc.)
        - Who can call this plugin
        - Who this plugin can call
        - Behavior constraints
        
        Args:
            plugin_id: Plugin to get rules for
            
        Returns:
            Rules dictionary
        """
        try:
            rules = {
                'plugin_id': plugin_id,
                'category': None,
                'callers': {
                    'cognitive': False,
                    'functional': False,
                    'sensory': False,
                    'external': False,
                },
                'callees': {
                    'cognitive': False,
                    'functional': False,
                    'sensory': False,
                },
            }
            
            # Determine category
            if self._determine_category:
                category = self._determine_category(plugin_id)
                rules['category'] = category
                
                # Define caller/callee rules based on category
                if category == 'cognitive':
                    # Cognitive plugins can be called by external/tasks only
                    rules['callers']['external'] = True
                    # Cognitive plugins can only call functional
                    rules['callees']['functional'] = True
                
                elif category == 'functional':
                    # Functional plugins can be called by cognitive
                    rules['callers']['cognitive'] = True
                    # Functional plugins cannot call anything
                    rules['callees'] = {k: False for k in rules['callees']}
                
                elif category == 'sensory':
                    # Sensory plugins can be called by anyone
                    rules['callers'] = {k: True for k in rules['callers']}
                    # Sensory plugins cannot call anything
                    rules['callees'] = {k: False for k in rules['callees']}
            
            # Add metadata from storage
            plugin_meta = self._storage.get_plugin(plugin_id)
            if plugin_meta:
                rules['status'] = plugin_meta.get('status')
                rules['version'] = plugin_meta.get('version')
                rules['is_active'] = plugin_meta.get('is_active', False)
                rules['behavior_key'] = plugin_meta.get('behavior_key')
            
            return rules
            
        except Exception as e:
            logger.error(f"Error retrieving rules for {plugin_id}: {e}")
            return {'plugin_id': plugin_id, 'error': str(e)}

    def get_plugin_capabilities(self, plugin_id: str) -> List[str]:
        """
        List capabilities of a plugin.
        
        Args:
            plugin_id: Plugin to get capabilities for
            
        Returns:
            List of capability descriptions
        """
        try:
            capabilities = []
            
            if plugin_id not in self._plugin_instances:
                logger.warning(f"Plugin instance not found: {plugin_id}")
                return capabilities
            
            plugin = self._plugin_instances[plugin_id]
            
            # Check for method capabilities
            if hasattr(plugin, 'execute'):
                capabilities.append("Can execute with execute()")
            if hasattr(plugin, 'process'):
                capabilities.append("Can process with process()")
            if hasattr(plugin, 'run'):
                capabilities.append("Can run with run()")
            if hasattr(plugin, 'handle'):
                capabilities.append("Can handle with handle()")
            
            # Check for async capability
            if hasattr(plugin, 'execute'):
                import inspect
                if inspect.iscoroutinefunction(plugin.execute):
                    capabilities.append("Supports async execution")
            
            # Check for concurrency safety
            plugin_meta = self._storage.get_plugin(plugin_id)
            if plugin_meta:
                if plugin_meta.get('is_concurrency_safe'):
                    capabilities.append("Thread-safe for concurrent execution")
            
            return capabilities
            
        except Exception as e:
            logger.error(f"Error retrieving capabilities for {plugin_id}: {e}")
            return []

    def get_compatibility_matrix(self) -> Dict[str, Dict[str, Any]]:
        """
        Generate compatibility matrix for all plugins.
        
        Shows which plugins can call which other plugins based on
        classification rules.
        
        Returns:
            Matrix of compatibilities
        """
        try:
            matrix = {}
            
            # Get all plugins organized by category
            cognitive_plugins = self._query_service.query_by_category("cognitive")
            functional_plugins = self._query_service.query_by_category("functional")
            sensory_plugins = self._query_service.query_by_category("sensory")
            
            # Build matrix entry for each plugin
            all_plugins = cognitive_plugins + functional_plugins + sensory_plugins
            
            for plugin in all_plugins:
                plugin_id = plugin['plugin_id']
                category = plugin.get('category', 'unknown')
                
                compatibility = {
                    'id': plugin_id,
                    'category': category,
                    'can_call': [],
                    'can_be_called_by': [],
                }
                
                # Determine what this plugin can call
                if category == 'cognitive':
                    # Cognitive can only call functional
                    compatibility['can_call'] = [p['plugin_id'] for p in functional_plugins]
                    compatibility['can_be_called_by'] = ['external', 'task_system']
                
                elif category == 'functional':
                    # Functional cannot call anything
                    compatibility['can_call'] = []
                    compatibility['can_be_called_by'] = [p['plugin_id'] for p in cognitive_plugins]
                
                elif category == 'sensory':
                    # Sensory cannot call anything
                    compatibility['can_call'] = []
                    compatibility['can_be_called_by'] = ['external', 'any_plugin']
                
                matrix[plugin_id] = compatibility
            
            logger.debug(f"Generated compatibility matrix for {len(matrix)} plugins")
            return matrix
            
        except Exception as e:
            logger.error(f"Error generating compatibility matrix: {e}")
            return {}

    def get_plugin_summary(self, plugin_id: str) -> Dict[str, Any]:
        """
        Get complete summary of plugin information.
        
        Combines:
        - Basic metadata
        - Documentation
        - Protocol
        - Rules
        - Capabilities
        
        Args:
            plugin_id: Plugin to summarize
            
        Returns:
            Complete plugin summary
        """
        try:
            summary = {
                'plugin_id': plugin_id,
                'timestamp': datetime.now().isoformat(),
            }
            
            # Get metadata
            plugin_meta = self._storage.get_plugin(plugin_id)
            if plugin_meta:
                summary['metadata'] = {
                    'version': plugin_meta.get('version'),
                    'status': plugin_meta.get('status'),
                    'is_active': plugin_meta.get('is_active'),
                    'behavior_key': plugin_meta.get('behavior_key'),
                    'created_at': plugin_meta.get('created_at'),
                }
            
            # Get documentation
            summary['documentation'] = self.get_plugin_documentation(plugin_id)
            
            # Get protocol
            summary['protocol'] = self.get_plugin_protocol(plugin_id)
            
            # Get rules
            summary['rules'] = self.get_plugin_rules(plugin_id)
            
            # Get capabilities
            summary['capabilities'] = self.get_plugin_capabilities(plugin_id)
            
            return summary
            
        except Exception as e:
            logger.error(f"Error generating summary for {plugin_id}: {e}")
            return {'plugin_id': plugin_id, 'error': str(e)}

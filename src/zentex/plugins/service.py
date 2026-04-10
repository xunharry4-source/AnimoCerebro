"""
⚠️ DEPRECATED: This file structure is deprecated.

The plugin service has been refactored into modular components.
All existing code will continue to work through backward compatibility re-exports.

New modular structure:
  src/zentex/plugins/service/
  ├── base.py         (initialization, bootstrap)
  ├── query.py        (discovery, queries)
  ├── execute.py      (execution, validation)
  ├── manage.py       (lifecycle management)
  └── manager.py      (unified entry point)
"""

from __future__ import annotations

# Re-export from new modular structure for backward compatibility
from zentex.plugins.service.manager import SystemPluginService, PluginGovernanceService


def get_default_provider_key() -> str:
    """
    Get the default LLM provider key from environment or config.
    
    This is the ONLY way external modules should access provider configuration.
    Never import zentex.plugins.provider_tools directly.
    
    Returns:
        Provider key string (e.g., 'openai', 'anthropic', etc.)
        
    Example:
        from zentex.plugins.service import get_default_provider_key
        provider = get_default_provider_key()
    """
    from zentex.plugins.provider_tools import get_default_provider_key as _get_key
    return _get_key()


__all__ = ['SystemPluginService', 'PluginGovernanceService', 'get_default_provider_key']

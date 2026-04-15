from __future__ import annotations

import logging
from typing import List, Optional

from zentex.common.plugin_registry import AbstractPluginRegistry
from zentex.plugins.models import BasePluginSpec, PluginLayer

logger = logging.getLogger(__name__)

class UnifiedPluginBus(AbstractPluginRegistry[BasePluginSpec]):
    """
    The central runtime bus for all registered and active plugins.
    
    It unifies Cognitive and Functional plugins into a single registry,
    allowing Cognitive plugins to orchestrate Functional ones, while
    ensuring Functional plugins remain isolated.
    """

    def __init__(self, transcript_store: Optional[any] = None) -> None:
        super().__init__(BasePluginSpec)
        self.transcript_store = transcript_store

    def list_all_active(self) -> List[BasePluginSpec]:
        """
        List all active plugins regardless of layer.
        """
        return [p for p in self._plugins.values() if p.lifecycle_status == "active" and p.operational_status == "enabled"]

    def get_by_category(self, category: str) -> List[BasePluginSpec]:
        """
        Filter plugins by category (cognitive or functional).
        """
        layer_target = (
            PluginLayer.LOGICAL_COGNITIVE 
            if category.lower() == "cognitive" 
            else PluginLayer.FUNCTIONAL
        )
        return [p for p in self._plugins.values() if p.plugin_layer == layer_target]

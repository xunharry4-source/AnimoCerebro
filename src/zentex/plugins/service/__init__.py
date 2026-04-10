"""
Plugin Service Module: Unified plugin governance system.

Sub-services:
- base: Initialization and bootstrap
- query: Plugin discovery and queries
- execute: Plugin execution with validation
- manage: Lifecycle management
- upgrade: Version management and upgrades
- info: Documentation and protocol information
- test: Health checks and compatibility testing
- manager: Unified entry point
"""

from .manager import SystemPluginService, PluginGovernanceService
from .base import BasePluginService
from .query import QueryService
from .execute import ExecutionService
from .manage import ManagementService
from .upgrade import UpgradeService
from .info import InfoService
from .test import TestService

__all__ = [
    'SystemPluginService',
    'PluginGovernanceService',
    'BasePluginService',
    'QueryService',
    'ExecutionService',
    'ManagementService',
    'UpgradeService',
    'InfoService',
    'TestService',
]

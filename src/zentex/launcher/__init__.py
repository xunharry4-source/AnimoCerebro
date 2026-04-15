"""
Launcher module — pure startup and service assembly layer for zentex.

RESPONSIBILITY:
This module orchestrates system startup by reading configuration, assembling all
services in dependency order, wiring cross-service references, and exposing
service accessors for the application layer. It contains zero business logic.

PROVIDES:
- Configuration loading (from environment or explicit StartupConfig)
- Configuration validation with warnings/errors
- Service initialization in topological dependency order (dependency_graph)
- Service registry and health tracking
- Web entrypoint (start_web() → FastAPI application)
- Daemon entrypoint (start_daemon() → persistent background service)
- Service getter methods (get_foundation_service, get_kernel_service, etc.)
- Graceful shutdown with error resilience

DOES NOT:
- Execute turns or manage sessions (kernel's responsibility)
- Define protocols or capabilities (foundation's responsibility)
- Contain any business logic whatsoever
- Import foundation or kernel internals (only via public get_service() calls)
- Expose any __runtime, __core, __boot internal modules

ARCHITECTURE:
- LauncherService: public entry point (service-only boundary)
- config: configuration loading, reading, and validation
- assembly: service dependency graph, registry, and assembler
- entrypoints: web app creation (FastAPI) and daemon creation (background loop)

MODULE STARTUP SEQUENCE:
1. Read configuration (StartupConfig) from environment
2. Validate configuration (check all required fields, emit warnings)
3. Topologically sort services using dependency_graph
4. Initialize each service in order (with graceful error handling)
5. Connect cross-module references (foundation → kernel, etc.)
6. Register each service in registry for access
7. Create entrypoint (web app or daemon) and return to caller

PUBLIC API:
Only import LauncherService and get_launcher() from this module.
All other submodules (config, assembly, entrypoints) are internal to launcher.
"""

from zentex.launcher.service import LauncherService, get_launcher

__all__ = ["LauncherService", "get_launcher"]

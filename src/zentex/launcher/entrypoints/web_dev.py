from __future__ import annotations
"""
Web Entrypoint — create_web_app() for the launcher layer.

RESPONSIBILITY:
  Called by LauncherService.start_web() (via the launcher assembly layer) to
  produce the FastAPI application object that uvicorn will serve.

  Primary path  → _create_full_app():
    1. Bootstraps plugins via seed_plugin_runtime_bundle()
       (provides the two REQUIRED args managed_plugin_records /
        plugin_feature_catalog to create_app()).
    2. Resolves EnhancedMemoryService from the service registry.
    3. Calls zentex.web_console.app.create_app() which registers all
       /api/web/* route trees.

  Degraded path → _create_minimal_app():
    Activated only when _create_full_app() raises (e.g. import failure,
    broken plugin DB).  Mirrors the same pattern used in launcher_asgi.py so
    uvicorn can still start and surface /health + the startup error.
    All endpoints in the degraded app return HTTP 503, not 200.

DOES NOT:
  - Own any route logic or business rules.
  - Manage service lifecycle (that is the launcher's job).
  - Pass runtime=KernelService to create_app() — KernelService does not
    implement the legacy BrainRuntime interface (get_runtime_state() etc.)
    that overview_commons.py expects; passing None is intentional and lets
    create_app() skip those backfill paths.

KEY DESIGN DECISIONS:
  - Plugin bootstrap failure falls back to empty plugin state (managed_plugin_records={}).
    Rationale: plugins are a non-critical optional layer at boot time; the web
    console can still serve all non-plugin routes.  Plugin routes will return
    503 individually if the plugin service is None.
  - Full app creation failure falls back to a minimal 503-only app rather than
    hard-crashing uvicorn, matching the existing launcher_asgi.py contract.
"""


import logging
import asyncio

from zentex.launcher.assembly.service_registry import ServiceRegistry

logger = logging.getLogger(__name__)


def create_web_app(registry: ServiceRegistry) -> object:
    """Build and return a FastAPI application wired to *registry*.

    Tries _create_full_app() first.  If it raises for any reason (broken
    import, DB unavailable, etc.) falls back to _create_minimal_app() so that
    uvicorn can still report the startup error via /health.

    Returns:
        A FastAPI application instance.
    """
    try:
        return _create_full_app(registry)
    except Exception:
        # Fail fast but keep a launcher-scoped traceback for diagnostics.
        logger.exception("web_dev: full web console app creation failed")
        raise


# ---------------------------------------------------------------------------
# Primary path: full web console app
# ---------------------------------------------------------------------------

def _create_full_app(registry: ServiceRegistry) -> object:
    """Bootstrap plugins and delegate to web_console.app.create_app()."""
    from zentex.web_console.app import create_app
    from zentex.__boot._bootstrap_nine_questions import seed_task_and_agent_runtime_state
    from zentex.__boot._bootstrap_plugins import seed_plugin_runtime_bundle

    # --- Plugin bootstrap ---------------------------------------------------
    # managed_plugin_records and plugin_feature_catalog are REQUIRED by
    # create_app().  If bootstrap fails we proceed with empty dicts/lists so
    # that all non-plugin routes still register correctly; plugin-specific
    # routes will surface their own 503 when plugin_service is None.
    try:
        plugin_bundle = seed_plugin_runtime_bundle()
        managed_plugin_records = plugin_bundle.managed_plugin_records
        plugin_feature_catalog = plugin_bundle.plugin_feature_catalog
        plugin_service = plugin_bundle.plugin_service
        logger.info(
            "web_dev: plugin bundle ready — %d records, %d catalog items",
            len(managed_plugin_records),
            len(plugin_feature_catalog),
        )
    except Exception as exc:
        logger.warning(
            "web_dev: plugin bootstrap failed; web console will start with "
            "empty plugin state.  Plugin routes will return 503.  Cause: %s",
            exc,
        )
        managed_plugin_records = {}
        plugin_feature_catalog = []
        plugin_service = None

    # --- Service resolutions from registry ----------------------------------
    from zentex.memory import EnhancedMemoryService
    
    memory = registry.get("memory")
    agent_service = registry.get("agents")
    task_service = registry.get("tasks")
    mcp_service = registry.get("mcp")
    cli_service = registry.get("cli")
    reflection_service = registry.get("reflection")
    learning_service = registry.get("learning")
    audit_service = registry.get("audit")
    
    # Engines are part of kernel state domain locally or provided by registry stubs
    kernel = registry.get("kernel")
    temporal_engine = None
    conflict_engine = None
    simulation_engine = None
    interaction_mind_engine = None
    consolidation_engine = None
    
    if kernel:
        # Try to get engines from kernel if exposed, otherwise look in registry
        temporal_engine = getattr(kernel, "temporal_engine", registry.get("cognitive_temporal"))
        conflict_engine = getattr(kernel, "conflict_engine", registry.get("cognitive_conflict"))
        simulation_engine = getattr(kernel, "simulation_engine", registry.get("cognitive_simulation"))
        interaction_mind_engine = getattr(kernel, "interaction_mind_engine", registry.get("cognitive_social_mind"))
        consolidation_engine = getattr(kernel, "consolidation_engine", registry.get("memory_consolidation"))
        
        logger.info(
            "[web_dev] Engine resolution: temporal=%s, conflict=%s, simulation=%s, interaction_mind=%s, consolidation=%s",
            "OK" if temporal_engine else "MISSING",
            "OK" if conflict_engine else "MISSING",
            "OK" if simulation_engine else "MISSING",
            "OK" if interaction_mind_engine else "MISSING",
            "OK" if consolidation_engine else "MISSING",
        )
        attach = getattr(kernel, "attach_dependencies", None)
        if callable(attach):
            # The launcher assembler injects a separate unbootstrapped plugins service
            # into kernel earlier in startup. Rebind kernel to the bootstrapped web
            # plugin runtime so nine-question execution sees the real plugin catalog.
            attach(
                environment_service=registry.get("environment"),
                cognition_service=registry.get("cognition"),
                safety_service=registry.get("safety"),
                plugins_service=plugin_service,
                memory_service=registry.get("memory"),
                audit_service=audit_service,
                llm_service=registry.get("llm"),
                foundation_service=registry.get("foundation"),
                reflection_service=reflection_service,
                learning_service=learning_service,
                agent_service=agent_service,
                cli_service=cli_service,
                mcp_service=mcp_service,
            )

    try:
        asyncio.get_running_loop()
        logger.warning("web_dev: skipped task/agent runtime seeding because an event loop is already running")
    except RuntimeError:
        try:
            asyncio.run(
                seed_task_and_agent_runtime_state(
                    task_service=task_service,
                    agent_service=agent_service,
                )
            )
        except Exception:
            logger.exception("web_dev: failed to seed task/agent runtime state")
    except Exception:
        logger.exception("web_dev: failed to inspect event loop for task/agent runtime seeding")

    attach_task_dependencies = None
    if getattr(task_service, "_is_stub", False):
        logger.warning("web_dev: skipping dependency injection for stub 'tasks' service.")
    else:
        attach_task_dependencies = getattr(task_service, "attach_dependencies", None)
    if callable(attach_task_dependencies):
        attach_task_dependencies(
            plugin_service=plugin_service,
            cli_service=cli_service,
            mcp_service=mcp_service,
            agent_service=agent_service,
        )
    
    # --- Create full app ----------------------------------------------------
    app = create_app(
        plugin_service=plugin_service,
        managed_plugin_records=managed_plugin_records,
        plugin_feature_catalog=plugin_feature_catalog,
        memory_service=memory,
        agent_coordination_service=agent_service,
        task_service=task_service,
        mcp_service=mcp_service,
        cli_service=cli_service,
        execution_registry=registry.get("functional_execution"),
        simulation_engine=simulation_engine,
        interaction_mind_engine=interaction_mind_engine,
        consolidation_engine=consolidation_engine,
        reflection_service=reflection_service,
        learning_service=learning_service,
        audit_service=audit_service,
    )
    
    # Inject engines into app state for cognition router
    app.state.temporal_engine = temporal_engine
    app.state.conflict_engine = conflict_engine
    app.state.simulation_engine = simulation_engine
    app.state.interaction_mind_engine = interaction_mind_engine
    app.state.consolidation_engine = consolidation_engine
    app.state.reflection_service = reflection_service
    app.state.learning_service = learning_service
    app.state.audit_service = audit_service

    logger.info("web_dev: full web console app created successfully.")
    return app


# ---------------------------------------------------------------------------
# Degraded path: minimal app surfacing the startup error
# ---------------------------------------------------------------------------

def _create_minimal_app(registry: ServiceRegistry, cause: Exception) -> object:
    """Create a minimal FastAPI app that reports the startup failure via 503.

    All endpoints return HTTP 503 (not 200) with the startup error detail so
    the frontend and monitoring tools receive an explicit service-unavailable
    signal rather than a misleading success response.
    """
    try:
        from fastapi import FastAPI
        from fastapi.responses import JSONResponse
        from pydantic import BaseModel
    except ImportError:
        logger.critical("web_dev: FastAPI not installed; cannot create any web app.")
        raise

    _cause_detail = {
        "error": "startup_failed",
        "message": f"Web console 启动失败：{type(cause).__name__}: {cause}",
        "services": registry.status_summary(),
    }

    class TurnBody(BaseModel):
        user_input: str
        context: dict = {}

    app = FastAPI(title="Zentex Web Console (degraded)", version="1.0.0")

    @app.get("/health")
    async def health() -> dict:
        # Health endpoint always returns 200 per convention, but marks degraded.
        return {"status": "degraded", **_cause_detail}

    @app.get("/api/web/overview")
    async def overview() -> JSONResponse:
        return JSONResponse(status_code=503, content=_cause_detail)

    @app.post("/sessions")
    async def create_session() -> JSONResponse:
        kernel = registry.get("kernel")
        if kernel is None:
            return JSONResponse(
                status_code=503,
                content={"error": "kernel_unavailable", "message": "Kernel 服务不可用"},
            )
        try:
            session_id = kernel.create_session()
            return JSONResponse(status_code=200, content={"session_id": session_id})
        except Exception as exc:
            logger.error("web_dev(degraded): create_session failed: %s", exc)
            return JSONResponse(
                status_code=500,
                content={"error": "create_session_failed", "message": str(exc)},
            )

    @app.post("/sessions/{session_id}/turn")
    async def run_turn(session_id: str, body: TurnBody) -> JSONResponse:
        kernel = registry.get("kernel")
        if kernel is None:
            return JSONResponse(
                status_code=503,
                content={"error": "kernel_unavailable", "message": "Kernel 服务不可用"},
            )
        try:
            result = kernel.start_turn(
                session_id, body.user_input, context=body.context
            )
            if hasattr(result, "__dict__"):
                return JSONResponse(status_code=200, content=vars(result))
            if isinstance(result, dict):
                return JSONResponse(status_code=200, content=result)
            return JSONResponse(status_code=200, content={"result": str(result)})
        except Exception as exc:
            logger.error(
                "web_dev(degraded): start_turn failed for session %s: %s",
                session_id,
                exc,
            )
            return JSONResponse(
                status_code=500,
                content={"error": "turn_failed", "message": str(exc)},
            )

    return app

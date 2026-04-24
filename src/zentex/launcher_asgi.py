"""
ASGI application factory for uvicorn startup.

This module is used by dev_all.sh and is invoked by uvicorn as:
    uvicorn zentex.launcher_asgi:app

The app object is created by starting the LauncherService.start_web() with 
the default (environment-based) configuration.
"""

import logging
import os
import re
import traceback
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Ensure a console handler exists for INFO logs (startup markers, etc.)
try:
    from zentex.common.startup_markers import ensure_console_logging_configured

    ensure_console_logging_configured()
except Exception:
    # Never block startup on logging bootstrap.
    pass


_ACCESS_STATUS_RE = re.compile(r'"\s(\d{3})\s')


class _AccessLogMiddleware:
    """ASGI middleware that logs HTTP access at appropriate levels.
    
    - 2xx-3xx → INFO
    - 4xx → WARNING
    - 5xx → ERROR
    
    This ensures 503 and other server errors are visible as ERROR level in logs,
    not hidden behind INFO level logging.
    """
    
    def __init__(self, app, logger_instance):
        self.app = app
        self.logger = logger_instance
    
    async def __call__(self, scope, receive, send):
        """ASGI interface."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        # Capture response status code
        status_code = 200
        
        async def send_with_logging(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)
        
        # Call the app
        await self.app(scope, receive, send_with_logging)
        
        # Log with appropriate level
        method = scope["method"]
        path = scope.get("path", "")
        client_host = scope.get("client", ("unknown", 0))[0]
        log_message = f'{client_host} - "{method} {path} HTTP/1.1" {status_code}'
        
        if status_code >= 500:
            self.logger.error(log_message)
        elif status_code >= 400:
            self.logger.warning(log_message)
        else:
            self.logger.info(log_message)


def _is_development_mode() -> bool:
    return os.environ.get("ZENTEX_ENV", "development").strip().lower() == "development"


def _persist_startup_traceback(traceback_text: str) -> Path:
    from zentex.common.storage_paths import get_storage_paths

    log_dir = get_storage_paths().app_data_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "startup_error.log"
    timestamp = datetime.now().isoformat(timespec="seconds")
    log_path.write_text(
        f"[{timestamp}] Zentex startup failure\n\n{traceback_text}\n",
        encoding="utf-8",
    )
    return log_path

# Create and start the app at module import time.
# This happens when uvicorn loads this module.
from zentex.launcher import get_launcher

try:
    # Disable uvicorn's default access logging before starting the app
    # We'll use our own ASGI middleware instead
    logging.getLogger("uvicorn.access").disabled = True
    
    launcher_svc = get_launcher()
    app = launcher_svc.start_web()  # Load config from env, assemble services
    logger.info("ASGI app created successfully via launcher")
    
    # Configure our custom access logger
    access_log_logger = logging.getLogger("zentex.access_log")
    access_log_logger.setLevel(logging.DEBUG)
    
    # Add console handler if not already present
    if not access_log_logger.handlers:
        handler = logging.StreamHandler()
        handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter("%(levelname)s:     %(message)s")
        handler.setFormatter(formatter)
        access_log_logger.addHandler(handler)
        access_log_logger.propagate = False
    
    # Wrap app with our access log middleware
    # This ensures 5xx errors are logged as ERROR, not INFO
    app = _AccessLogMiddleware(app, access_log_logger)
    logger.info("[✓ ACCESS_LOG MIDDLEWARE] Installed — 5xx→ERROR, 4xx→WARNING, 2xx-3xx→INFO")
    
except Exception:
    startup_traceback = traceback.format_exc()
    logger.critical("ASGI startup failed with uncaught exception", exc_info=True)
    if _is_development_mode():
        path = _persist_startup_traceback(startup_traceback)
        logger.critical("Full startup traceback saved to %s", path)
    raise

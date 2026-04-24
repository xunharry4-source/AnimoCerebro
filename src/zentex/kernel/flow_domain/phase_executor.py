"""PhaseExecutor — runs a single phase function with timeout and error handling."""

import concurrent.futures
import time
from collections.abc import Callable
from typing import Any

from zentex.foundation.contracts import PhaseResult
from zentex.kernel.flow_domain.phase_registry import PhaseConfig


class PhaseExecutor:
    """Executes a phase function with timeout enforcement and error handling.

    Standard Redline (Fail-Closed):
    - The callable is run inside a ThreadPoolExecutor with a hard timeout.
    - If the call returns a dict it is wrapped in PhaseResult.
    - If the call raises and the phase is *skippable*: returns a skipped PhaseResult.
    - If the call *times out* and the phase is *degradable*: returns an empty-output PhaseResult.
    - If the call *crashes* (raises Exception): always propagates unless *skippable*.
      (Degradable is for environmental timeouts, not for masking code bugs).
    """

    def __init__(self, config: PhaseConfig) -> None:
        self._config = config

    def execute(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> PhaseResult:
        """Run *fn* with *args*/*kwargs* and return a PhaseResult.

        Args:
            fn:      The phase function to execute.
            *args:   Positional arguments forwarded to *fn*.
            **kwargs: Keyword arguments forwarded to *fn*.
        """
        config = self._config
        start_ms = time.perf_counter() * 1000.0

        def _run() -> Any:
            return fn(*args, **kwargs)

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_run)
            try:
                result = future.result(timeout=config.timeout_seconds)
            except concurrent.futures.TimeoutError as exc:
                duration_ms = time.perf_counter() * 1000.0 - start_ms
                if config.skippable:
                    return PhaseResult(
                        phase_name=config.name,
                        skipped=True,
                        error="Phase timed out",
                        duration_ms=0.0,
                    )
                if config.degradable:
                    logger.warning(f"Phase '{config.name}' timed out; degrading to empty result (G33).")
                    return PhaseResult(
                        phase_name=config.name,
                        output={},
                        error=f"Phase timed out after {config.timeout_seconds}s",
                        duration_ms=duration_ms,
                    )
                raise TimeoutError(
                    f"Phase '{config.name}' timed out after {config.timeout_seconds}s"
                ) from exc
            except Exception as exc:  # noqa: BLE001
                duration_ms = time.perf_counter() * 1000.0 - start_ms
                if config.skippable:
                    logger.info(f"Phase '{config.name}' failed; skipping per config.")
                    return PhaseResult(
                        phase_name=config.name,
                        skipped=True,
                        error=str(exc),
                        duration_ms=0.0,
                    )
                
                # G33 Resiliency Redline: Never swallow code crashes into 'degradation'.
                # A code crash is a bug, not a degradable environmental condition.
                raise exc

        duration_ms = time.perf_counter() * 1000.0 - start_ms

        # Normalise the return value to a dict
        if isinstance(result, dict):
            output = result
        elif result is None:
            output = {}
        else:
            output = {"value": result}

        return PhaseResult(
            phase_name=config.name,
            output=output,
            duration_ms=duration_ms,
        )

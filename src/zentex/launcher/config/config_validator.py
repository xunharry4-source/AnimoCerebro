from __future__ import annotations
"""
ConfigValidator — validates a StartupConfig and returns a ValidationResult.

Errors block startup; warnings are advisory only.
"""


from dataclasses import dataclass, field

from zentex.launcher.config.startup_config import StartupConfig


@dataclass
class ValidationResult:
    """Result returned by ConfigValidator.validate()."""

    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class ConfigValidator:
    """Validates a StartupConfig, collecting errors and warnings."""

    def validate(self, config: StartupConfig) -> ValidationResult:
        """Validate *config* and return a ValidationResult.

        The result's ``valid`` flag is True only when no errors were found.
        Warnings are always collected independently of errors.
        """
        errors: list[str] = []
        warnings: list[str] = []

        # --- port ---
        if not (1 <= config.web.port <= 65535):
            errors.append(
                f"web.port must be between 1 and 65535, got {config.web.port}"
            )

        # --- working_memory_slots ---
        if not (1 <= config.kernel.working_memory_slots <= 1024):
            errors.append(
                f"kernel.working_memory_slots must be between 1 and 1024, "
                f"got {config.kernel.working_memory_slots}"
            )

        # --- session_timeout_seconds ---
        if config.kernel.session_timeout_seconds <= 0:
            errors.append(
                f"kernel.session_timeout_seconds must be > 0, "
                f"got {config.kernel.session_timeout_seconds}"
            )

        # --- turn_max_concurrency ---
        if not (1 <= config.kernel.turn_max_concurrency <= 100):
            errors.append(
                f"kernel.turn_max_concurrency must be between 1 and 100, "
                f"got {config.kernel.turn_max_concurrency}"
            )

        # --- llm.timeout_seconds ---
        if config.llm.timeout_seconds <= 0:
            errors.append(
                f"llm.timeout_seconds must be > 0, got {config.llm.timeout_seconds}"
            )

        # --- environment ---
        if config.environment not in {"development", "production"}:
            errors.append(
                f"environment must be 'development' or 'production', "
                f"got '{config.environment}'"
            )

        # --- warnings ---
        if config.environment == "production" and config.web.debug:
            warnings.append(
                "web.debug is True in a production environment — "
                "this may expose sensitive information."
            )

        if config.environment == "production" and config.web.cors_origins == ["*"]:
            warnings.append(
                "web.cors_origins is set to ['*'] in a production environment — "
                "consider restricting allowed origins."
            )

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

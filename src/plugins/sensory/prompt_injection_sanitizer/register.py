from __future__ import annotations

PLUGIN_ID = "sensory_injection_sanitizer"


def get_plugin_id() -> str:
    return PLUGIN_ID


def resolve_factory(factory_catalog: dict[str, object]) -> object:
    if PLUGIN_ID not in factory_catalog:
        raise KeyError(f"Factory not found for plugin_id={PLUGIN_ID}")
    return factory_catalog[PLUGIN_ID]

from __future__ import annotations

PLUGIN_ID = "cognitive_failure_cluster"


def startup(factory_catalog: dict[str, object]) -> tuple[str, object]:
    if PLUGIN_ID not in factory_catalog:
        raise KeyError(f"Factory not found for plugin_id={PLUGIN_ID}")
    return PLUGIN_ID, factory_catalog[PLUGIN_ID]

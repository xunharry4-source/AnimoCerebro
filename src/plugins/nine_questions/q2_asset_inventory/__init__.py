__all__ = ["build_q2_asset_inventory_plugin"]


def build_q2_asset_inventory_plugin(*args, **kwargs):
    from plugins.nine_questions.q2_asset_inventory.q2_asset_inventory_plugin import (
        build_q2_asset_inventory_plugin as _build,
    )

    return _build(*args, **kwargs)

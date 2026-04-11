from __future__ import annotations

# Conservative weight plugin re-exports the default factory from the assembler.
# The SubjectiveWeightPlugin class and all weight factories live in assembler/
# to keep them co-located with the WeightPluginAssembler that manages them.

from plugins.weights.assembler.weight_assembler_plugin import (  # noqa: F401
    SubjectiveWeightPlugin,
    build_default_conservative_weight,
)

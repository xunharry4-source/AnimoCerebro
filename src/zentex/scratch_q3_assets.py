import asyncio
from zentex.boot.web_dev import build_default_local_system_executor, _seed_managed_plugins
from zentex.core.plugin_base import PluginLifecycleStatus
from zentex.runtime.nine_questions.startup_snapshot import build_runtime_workspace_snapshot

# Simulate the registry setup
executor = build_default_local_system_executor()

# Let's seed managed plugins
plugins = _seed_managed_plugins()
print(f"Total managed plugins seeded: {len(plugins)}")

# Iterate and find cognitive/execution
cog_count = 0
exec_count = 0
active_cog = 0
active_exec = 0

for p in plugins:
    kind = getattr(p.plugin, "plugin_kind", lambda: "")()
    status = getattr(p.plugin, "status", None)
    
    if kind == "cognitive_tool":
        cog_count += 1
        if status == PluginLifecycleStatus.ACTIVE:
            active_cog += 1
    elif kind == "execution_domain":
        exec_count += 1
        if status == PluginLifecycleStatus.ACTIVE:
            active_exec += 1

print(f"Cognitive Tools: total={cog_count}, active={active_cog}")
print(f"Execution Domains: total={exec_count}, active={active_exec}")


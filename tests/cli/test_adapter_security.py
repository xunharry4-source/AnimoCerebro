import pytest
from unittest.mock import MagicMock
from zentex.cli.adapter import CliAdapterPlugin, SubprocessCliTransport
from zentex.core.cli import CliToolRegistrationConfig
from zentex.core.plugin_base import PluginHealthStatus, PluginLifecycleStatus

def test_privilege_isolation_enforcement():
    """
    越权隔离 (Privilege Isolation) 断言:
    试图将具备删除或写入能力的 CLI 工具注册为只读 (read_only_flag=True)。
    系统校验器必须立即抛出 ValueError (ValidationError 模拟)，阻断逻辑启动。
    """
    plugin = CliAdapterPlugin(
        plugin_id="test_cli_adapter",
        version="1.0.0",
        is_concurrency_safe=True,
        status=PluginLifecycleStatus.ACTIVE,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["test_rollback"],
        revocation_reasons=[],
    )
    # Mock 依赖注入
    plugin.attach_runtime(
        transport=MagicMock(),
        transcript_store=MagicMock(),
        cognitive_registry=MagicMock(),
        execution_registry=MagicMock(),
    )
    
    # 构造恶意注册配置：执行 'rm' 但声明为 'read_only'
    config = CliToolRegistrationConfig(
        tool_name="malicious_cleaner",
        command_executable="rm -rf /data",
        description="Attempts to bypass domain isolation",
        read_only_flag=True  # 试图绕过
    )
    
    # 断言系统抛出 ValueError 且包含 ValidationError 关键字
    with pytest.raises(ValueError, match="ValidationError"):
        plugin.register_tool(config)


def test_crash_isolation_and_degradation():
    """
    崩溃隔离 (Crash Isolation) 断言:
    Mock 宿主环境缺失 CLI 命令或探针失败。
    断言适配器抛出异常并拒绝注册，而非拖垮主脑。
    """
    transport = SubprocessCliTransport()
    
    # 提供一个绝对不存在的可执行文件路径
    config = CliToolRegistrationConfig(
        tool_name="ghost_tool",
        command_executable="/usr/bin/this_binary_does_not_exist_zentex",
        description="Missing binary test",
        read_only_flag=True
    )
    
    plugin = CliAdapterPlugin(
        plugin_id="test_cli_adapter_crash",
        version="1.0.0",
        is_concurrency_safe=True,
        status=PluginLifecycleStatus.ACTIVE,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["test_rollback"],
        revocation_reasons=[],
    )
    plugin.attach_runtime(
        transport=transport,
        transcript_store=MagicMock(),
        cognitive_registry=MagicMock(),
        execution_registry=MagicMock(),
    )
    
    # 断言注册阶段因健康探测失败而受阻
    with pytest.raises(FileNotFoundError, match="health probe failed"):
        plugin.register_tool(config)
        
    # 模拟已注册工具检查
    assert plugin.health_probe() == PluginHealthStatus.HEALTHY

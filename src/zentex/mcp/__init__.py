__all__ = [
    "McpAdapterPlugin",
    "McpCognitiveToolPlugin",
    "McpExecutionDomainPlugin",
    "McpIntegrationService",
    "OfficialMcpSdkTransportClient",
    "McpTransportClient",
    "build_official_mcp_client_factory",
]


def __getattr__(name: str):
    if name in {
        "McpAdapterPlugin",
        "McpCognitiveToolPlugin",
        "McpExecutionDomainPlugin",
    }:
        from zentex.mcp import adapter as _adapter

        return getattr(_adapter, name)
    if name in {"OfficialMcpSdkTransportClient", "build_official_mcp_client_factory", "McpTransportClient"}:
        from zentex.mcp import sdk_transport as _sdk_transport

        return getattr(_sdk_transport, name)
    if name == "McpIntegrationService":
        from zentex.mcp import service as _service

        return getattr(_service, name)
    raise AttributeError(name)


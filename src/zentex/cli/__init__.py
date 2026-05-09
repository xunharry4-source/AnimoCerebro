__all__ = [
    "CliAdapterPlugin",
    "CliCognitiveToolPlugin",
    "CliExecutionDomainPlugin",
    "CliIntegrationService",
    "CliTransportClient",
    "SubprocessCliTransport",
]


def __getattr__(name: str):
    if name in {
        "CliAdapterPlugin",
        "CliCognitiveToolPlugin",
        "CliExecutionDomainPlugin",
        "CliTransportClient",
        "SubprocessCliTransport",
    }:
        from zentex.cli import adapter as _adapter

        return getattr(_adapter, name)
    if name == "CliIntegrationService":
        from zentex.cli import service as _service

        return getattr(_service, name)
    raise AttributeError(name)

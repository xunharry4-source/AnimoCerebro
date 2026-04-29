# External Plugins Directory

## Overview

This directory (`plugins/` at the repository root) holds **external plugins** for the AnimoCerebro project.

## Key Principles

### Standalone Architecture
- External plugins are **fully standalone and dedicated**
- They **must not depend** on code under `src/` (including but not limited to `src/zentex`)
- Each plugin operates independently with clear boundaries

### What to Place Here
You may place the following in this directory:
- Third-party packages
- Separate processes
- Independent scripts
- External resources and assets
- Custom integrations

### Integration Guidelines

Integration with the main Zentex project should use:
- ✅ Agreed APIs and protocols
- ✅ Configuration files
- ✅ Inter-process communication (IPC)
- ✅ Standard interfaces

**Do NOT use**:
- ❌ Python imports from `src/`
- ❌ Direct code dependencies on `src/zentex`
- ❌ Tight coupling with core modules

## Plugin Types

### External Plugins vs Internal Plugins

**External Plugins** (`plugins/`):
- Connect external functionalities as components
- Serve as bridges between external systems and the brain
- **STRICT RULE**: Cannot import or call any code from `src/` directory
- Must interact with the brain exclusively through defined APIs and protocols
- Designed for third-party integrations and custom extensions

**Internal Plugins** (`src/plugins/`):
- Part of the core system's self-evolution mechanism
- Can access and interact with `src/zentex/` core modules
- Support hot-reload and dynamic upgrading
- Implement core cognitive functions (e.g., Q1-Q9 nine questions)
- Managed by the internal plugin registry system

## Example Use Cases

### External Plugin Examples
- Custom data source connectors
- Third-party service integrations
- Specialized tool adapters
- External API wrappers
- Legacy system bridges

### Integration Patterns

#### Pattern 1: API-Based Integration
```python
# External plugin communicates via HTTP/gRPC
import requests

def call_zentex_api(endpoint, data):
    response = requests.post(
        f"http://localhost:8000/api/{endpoint}",
        json=data
    )
    return response.json()
```

#### Pattern 2: Configuration-Based
```yaml
# plugin_config.yml
plugin:
  name: my_external_plugin
  api_endpoint: http://zentex:8000/api/v1
  authentication: bearer_token
```

#### Pattern 3: Message Queue
```python
# Using RabbitMQ/Kafka for async communication
import pika

def send_to_zentex(message):
    connection = pika.BlockingConnection(
        pika.ConnectionParameters('localhost')
    )
    channel = connection.channel()
    channel.basic_publish(
        exchange='zentex',
        routing_key='plugin.input',
        body=message
    )
```

## Development Guidelines

### Independence Requirements
1. **No src/ imports**: Never import from `src/` directory
2. **Self-contained**: All dependencies must be declared in plugin's requirements
3. **Clear interfaces**: Define explicit API contracts
4. **Error handling**: Handle all edge cases gracefully
5. **Logging**: Use standard logging for debugging

### Best Practices
- Document your plugin's API and usage
- Provide example configurations
- Include unit tests for your plugin
- Follow semantic versioning
- Maintain backward compatibility when possible

## Directory Structure Example

```
plugins/
├── README.md              # This file (English)
├── README_ZH.md           # Chinese version
├── .gitkeep               # Keep directory in git
├── my_custom_plugin/
│   ├── __init__.py
│   ├── main.py
│   ├── config.yml
│   ├── requirements.txt
│   └── README.md
└── another_plugin/
    ├── __init__.py
    ├── service.py
    └── README.md
```

## Getting Started

1. Create a new directory for your plugin
2. Define your plugin's interface and capabilities
3. Implement using only external dependencies
4. Test independently from the main codebase
5. Document integration points with Zentex
6. Submit for review

## Support

For questions about external plugin development:
- Check [PLUGIN_GUIDES.md](../docs/operability/PLUGIN_GUIDES.md)
- Review [FUNCTION_MODULES.md](../docs/operability/FUNCTION_MODULES.md)
- Open an issue on GitHub
- Join GitHub Discussions

---

**Last Updated**: April 29, 2026  
**Maintained by**: AnimoCerebro Development Team

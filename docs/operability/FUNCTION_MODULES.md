# Function Modules Documentation

This document explains the responsibilities and technical architecture of the functional modules in the `src` directory, facilitating unified boundaries for future development, collaboration, and deployment.

For plugin development guidelines organized by function, see:
- [PLUGIN_GUIDES.md](/Users/harry/Documents/git/AnimoCerebro/docs/operability/PLUGIN_GUIDES.md)

## One-Click Development Commands (Most Commonly Used)

This repository provides front-end and back-end联动 "one-click start / one-click restart" entry points to ensure that Web pages bind to real backend services (not mock).

- One-click start: `make dev` (equivalent to `./scripts/dev_all.sh`, default uses `websockets-sansio`)
- One-click restart: `make restart-dev` (equivalent to `./scripts/restart_dev.sh`, will first clean up port occupancy before pulling up)

For more complete startup, port override, and testing instructions, see:
- [STARTUP_AND_TEST.md](/Users/harry/Documents/git/AnimoCerebro/docs/operability/STARTUP_AND_TEST.md)

## Directory List

### `src/plugins`

Tool capability directory, used to carry third-party model and external capability call method encapsulation.

Scope of application:
- Third-party model call encapsulation
- External platform HTTP call methods
- Unified request body and response body standardization
- Provide tool methods that can be directly accessed by the runtime

Suggested content:
- Tool call entry point
- Provider configuration model
- Request body and response body encapsulation
- External call method description

Current key files:
- `src/plugins/provider_tools.py`
  Responsible for encapsulating OpenAI, ChatGPT, Gemini, and Claude call methods.

Plugin development guidelines:
- First check the function-organized general index `docs/operability/PLUGIN_GUIDES.md`
- Then enter the corresponding plugin directory to view the family-level `DEVELOPMENT_GUIDE.md`
- `src/plugins/model_providers/DEVELOPMENT_GUIDE.md`
- `src/plugins/cognitive/DEVELOPMENT_GUIDE.md`
- `src/plugins/execution/DEVELOPMENT_GUIDE.md`
- `src/plugins/sensory/DEVELOPMENT_GUIDE.md`
- `src/plugins/simulation/DEVELOPMENT_GUIDE.md`
- `src/plugins/weights/DEVELOPMENT_GUIDE.md`

### `src/admin-portal`

Web management portal directory, providing visual operation interface for Zentex system.

Main functions:
- System status monitoring
- Agent management
- Task tracking
- Plugin management
- MCP management
- Real-time event streaming display

Technology stack:
- React + Vite + TypeScript
- WebSocket real-time communication
- RESTful API interaction

### `src/zentex`

Core business logic directory, containing all core modules of Zentex system.

#### Core Modules:

1. **Cognition Module** (`src/zentex/cognition/`)
   - Nine Questions cognitive loop implementation
   - Decision reasoning engine
   - Goal generation and planning

2. **Memory Module** (`src/zentex/memory/`)
   - Memory storage and retrieval
   - Experience accumulation
   - Knowledge consolidation

3. **Safety Module** (`src/zentex/safety/`)
   - Safety gate mechanisms
   - Risk assessment
   - Conflict detection and resolution

4. **Tasks Module** (`src/zentex/tasks/`)
   - Task decomposition engine
   - Task execution management
   - Verification and validation

5. **Upgrade Module** (`src/zentex/upgrade/`)
   - System upgrade framework
   - AI-driven executors
   - Skills-based debugging and reviewing

6. **Environment Module** (`src/zentex/environment/`)
   - Environmental awareness
   - Sensory processing
   - Context interpretation

7. **Web Console** (`src/zentex/web_console/`)
   - API endpoints
   - WebSocket services
   - Real-time monitoring

8. **Plugins Module** (`src/zentex/plugins/`)
   - Plugin registry
   - Plugin lifecycle management
   - Hot-reload support

9. **Agents Module** (`src/zentex/agents/`)
   - Agent management
   - Agent coordination
   - Communication protocols

10. **Learning Module** (`src/zentex/learning/`)
    - Learning mechanisms
    - Experience exchange
    - Knowledge evolution

11. **Supervision Module** (`src/zentex/supervision/`)
    - AI supervisor integration
    - Oversight mechanisms
    - Audit trails

12. **Reflection Module** (`src/zentex/reflection/`)
    - Self-reflection capabilities
    - Performance analysis
    - Improvement suggestions

## Architecture Overview

Zentex follows a layered architecture design:

1. **Perception Layer**: Environmental sensing and data ingestion
2. **Cognitive Layer**: Nine Questions reasoning and decision-making
3. **Orchestration Layer**: Task planning and coordination
4. **Execution Layer**: Action execution and result collection
5. **Reflection Layer**: Self-evaluation and improvement

## Key Design Principles

1. **Modularity**: Each module has clear boundaries and responsibilities
2. **Plugin-Based**: Extensible through plugin architecture
3. **Autonomy**: Enables AI autonomous decision-making
4. **Safety**: Built-in safety mechanisms and risk control
5. **Observability**: Comprehensive logging and monitoring
6. **Evolution**: Self-upgrading and learning capabilities

## Integration Points

- External agents connect through standardized protocols
- Plugins extend functionality without modifying core code
- Web console provides real-time monitoring and control
- API endpoints enable programmatic access

## Testing Strategy

- Unit tests for individual components
- Integration tests for module interactions
- E2E tests for complete workflows
- Performance tests for critical paths

## Deployment Considerations

- Support for local, distributed, and cloud deployments
- Configuration-driven behavior customization
- Health check and monitoring endpoints
- Graceful shutdown and restart mechanisms

# ADR-012: Ecosystem State and Context Subsystem Architecture

## Status
Accepted

## Context
Across S8–S11, Shyam developed individual capabilities for discovery, routing/navigation, sequential workflow execution, and multi-step composition. However, the runtime lacked a unified observational layer capable of answering: *"What is the current state of the ecosystem right now, and what context should Shyam have about it?"*

Discovery (EcosystemSnapshot) provided point-in-time facts about reachable nodes and capabilities, while the Workflow Engine (S10) managed local lifecycle execution without persisting global visibility over in-flight tasks.

## Decision
We introduced a dedicated shyam.context subsystem that acts as an in-memory, observational state aggregator without violating Single Responsibility:

1. **Observational Aggregation (EcosystemStateStore)**:
   - Subscribes to S8 discovery events (EcosystemNodeDiscoveredEvent, EcosystemNodeUpdatedEvent, EcosystemNodeStaleEvent, EcosystemNodeLostEvent).
   - Subscribes to S10 workflow lifecycle events (WorkflowStartedEvent, WorkflowCompletedEvent, WorkflowFailedEvent, WorkflowCancelledEvent, WorkflowStepStartedEvent).
   - Maintains an in-memory index of active work items (ActiveWorkItem) and a bounded ring buffer of recent activity (RecentActivityEntry).
   - Tracks a local monotonic sequence revision version number (ersion: int).

2. **Immutable Snapshots (EcosystemState & EcosystemContext)**:
   - All state retrieval methods return frozen, validated Pydantic models.
   - S8 discovery snapshot serves as the underlying node fact representation. S12 does not create a competing discovery registry.

3. **Runtime Surface Integration**:
   - Exposed untime.get_ecosystem_state() and untime.get_ecosystem_context().
   - Lifecycle-coordinated via EcosystemContextService.

## Consequences
- **Positive**: Clean separation between execution authorities (WorkflowEngine) and observational awareness (EcosystemStateStore).
- **Positive**: Zero modifications to existing S8/S9/S10/S11 execution mechanisms or EventBus protocols.
- **Positive**: Local state representation is fully deterministic and ready for future peer state synchronization (S14).
- **Deferred**: Peer synchronization, distributed consensus, persistent storage (Postgres/Redis/SQLite), device identity/trust enrollment (S13), and cross-device continuity (S16) remain out of scope for S12.

# ADR-010: Workflow Engine Architecture and Capability Execution Boundary

## Status
Accepted

## Context
Across previous sprints, Shyam established:
1. **S4/S5 Provider Fabric**: `Provider` metadata descriptors and local provider lifecycle.
2. **S6/S7 Remote Integrations**: `ZaryaProvider` and `FluxProvider` representing sovereign agents and network connectivity.
3. **S8 Ecosystem Discovery**: Normalized multi-node topology and capability state (`EcosystemSnapshot`).
4. **S9 Hybrid Navigator**: Deterministic target resolution (`NavigationRequest` -> `NavigationResult`).

While S9 answers **"Which node/provider should satisfy this capability?"**, Shyam previously had no coordination layer to answer:
> **"How do I orchestrate a sequence of work across the selected targets and track execution state?"**

Additionally, existing providers expose heterogeneous interfaces:
- `LocalFilesystemProvider` declares capabilities (`file.read`, `file.write`, `file.list`) but deliberately defers execution.
- `ZaryaProvider` exposes a generic `execute(tool, args)` method.
- `FluxProvider` exposes granular per-capability methods (`discover_peers`, `transfer`, etc.).
- `Provider` base model is strictly metadata-only (ADR-004: *Capability != Provider != Node != Execution*).

## Decision

### 1. Architectural Layering
We introduce `shyam.workflow` as a distinct orchestration layer sitting strictly above S9 Hybrid Navigation:
```text
  Workflow Definition (S10)
          │
          ▼
   Workflow Engine (S10)
          │ (per step: NavigationRequest)
          ▼
   Hybrid Navigator (S9)
          │ (returns NavigationResult.selected)
          ▼
   Capability Execution Boundary (S10)
          │ (dispatches to target-specific executor)
          ▼
     Provider Layer (Local / Zarya / Flux)
```

### 2. Domain Models & Immutability

- `Workflow` and `WorkflowStep` define the intent and structured step inputs as immutable frozen Pydantic models.
- Step targets are resolved strictly through S9 `NavigationRequest`. Direct hard-coded provider invocations 
  or capability-only executions that bypass navigation are forbidden.
- `WorkflowResult` and `StepResult` represent immutable execution outcomes with explicit status, outputs, 
  errors, and timing metadata.

### 3. State Machine & Transitions

We define strict, deterministic lifecycle states mirroring shyam.core.lifecycle:

- Workflow Lifecycle: `PENDING -> RUNNING -> {COMPLETED, FAILED, CANCELLED}`
- Step Lifecycle: `PENDING -> RUNNING -> {COMPLETED, FAILED, SKIPPED, CANCELLED}`
- Invalid transitions raise `InvalidWorkflowStateTransitionError`. Terminal states cannot be re-entered.

### 4. Normalized Execution Boundary (CapabilityExecutor & ExecutorRegistry)

To prevent the workflow engine from knowing provider-specific transport or method details, we introduce:

- `CapabilityExecutor` Protocol: `async execute(target: NavigationCandidate, input_data: dict[str, Any]) -> StepResult`
- `ExecutorRegistry`: Maps `provider_id` to its corresponding provider adapter 
   `(LocalFilesystemExecutor, ZaryaExecutor FluxExecutor).`   
- Providers retain their encapsulation. The executor layer adapts normalized workflow step payloads into native provider calls.

### 5. Execution Model (Sequential First)

S10 adopts a strict sequential execution model. Step N begins only after Step N−1 succeeds.
DAG scheduling, parallel branch execution, and distributed worker queues are deferred to prevent premature synchronization complexity.

### 6. Failure & Cancellation Semantics 

- Fail-Fast: If step k fails, steps  k + 1 ... N transition to `SKIPPED`. The overall workflow transitions to `FAILED`.
- Preserved Causes: Exceptions and error diagnostics are preserved in `StepResult.error` and `WorkflowResult.error_detail`.
- Cooperative Cancellation: Workflows check for cancellation requests prior to invoking each step. Active step completion 
  or cooperative cancellation transitions subsequent steps to `SKIPPED` / `CANCELLED`.

### 7. Deferred Concerns

- No Automatic Retries: Retries without idempotency classifications risk duplicating side-effects across external providers.
- No Persistent Storage: In-memory execution satisfies S10 orchestration baseline; persistent workflows will 
  align with S12/S16 state continuity.
- No AI / LLM Planners: Workflows are structured deterministic contracts.

### 8. Event Integration

All lifecycle transitions emit typed events onto Shyam's existing EventBus (`WorkflowStartedEvent`, `WorkflowStepStartedEvent`, `WorkflowStepCompletedEvent`, `WorkflowStepFailedEvent`, `WorkflowCompletedEvent`, `WorkflowFailedEvent`, `WorkflowCancelledEvent`).

## Consequences

### Positive

- Strict separation between target selection (S9) and step orchestration (S10).
- Provider internals remain encapsulated behind adapter executors.
- Fully testable in-memory with deterministic state verification.
- Clear foundation for S11 Composite Capabilities.

### Negative / Trade-offs

- Adding new provider types requires registering a corresponding `CapabilityExecutor` adapter.
- In-memory execution state is lost if the host runtime process terminates abruptly.

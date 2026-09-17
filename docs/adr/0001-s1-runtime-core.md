# ADR-001: S1 Runtime Core Architecture

## Status
Accepted

## Context
As specified in the Shyam S1 Brief, we need a robust, local-first, standalone core runtime execution layer. It must manage component lifecycles, configuration boundaries, state tracking, and in-process message dispatch, while fully respecting the frozen S0 baseline without introducing external dependencies (like networking, databases, or third-party agent/orchestration systems prematurely).

## Decisions

### 1. Unified Config Layer
Implemented a frozen, validated configuration structure using `Pydantic` models (`ShyamSettings`), which handles local default data directories and structured log tiers without future speculative fields.

### 2. Strict State Transition Validation
Implemented a bounded state machine via a `StrEnum` (`LifecycleState`) and explicit mapping. Transitions like `STOPPED` directly to `RUNNING` or `CREATED` directly to `RUNNING` are rejected explicitly to prevent corrupt execution paths.

### 3. Isolated In-Process Asynchronous Event Bus
Created an event broker (`EventBus`) implementing concurrent asynchronous dispatch. Handler exceptions are isolated to prevent any failing subscriber from crashing concurrent operations or interrupting runtime execution.

### 4. Structured Namespace Logging
Set up dedicated logging namespace `shyam` configured relative to the settings, establishing structured stdout formats.

## Consequences
- Enables robust local-first integration testing without external brokers or complex network mockups.
- Establishes a predictable foundation for subsequent sprints (S2 Node, S3 Capabilities, S4 Providers).
- Keeps the system lightweight, secure, and easily testable.
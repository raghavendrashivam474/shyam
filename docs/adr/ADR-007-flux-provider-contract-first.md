# ADR-007: Flux Provider Integration — Contract-First Approach

## Status
Proposed (S7)

## Context

Aryntra Flux v2.3.0 is a Rust workspace (flux-core + flux-node) providing
adaptive multi-path P2P data transfer. It exposes:

- PeerId (UUID-v4) identity
- mDNS + UDP heartbeat discovery
- Multi-path connectivity (TCP, relay)
- Session management
- Chunked transfer with SHA-256 verification and resume

However, Flux has **no external API boundary**. The flux-node binary is a
CLI tool (listen/connect/send) using a custom binary protocol (bincode +
4-byte length prefix over TCP). There is no HTTP server, no IPC socket,
no gRPC service, and no Python SDK.

Shyam cannot consume Flux capabilities without a defined cross-process
contract.

## Decision

We adopt a **contract-first** approach:

1. Define the minimal HTTP API that Flux should expose (Flux Gateway API v1)
2. Build the complete Shyam FluxProvider stack against this contract using
   mock responses
3. Deliver the contract specification to the Flux team for implementation
4. When Flux implements the gateway, Shyam's provider works without changes

### Proposed Flux Gateway API v1

Base URL: `http://127.0.0.1:9100/flux/v1`

| Method | Path | Purpose |
|--------|------|---------|
| GET | /identity | PeerId, version, protocol |
| GET | /status | Node state, connectivity summary |
| GET | /peers | Discovered peers list |
| GET | /peers/{peer_id} | Peer detail + paths + connectivity |
| POST | /connect | Establish connectivity to peer |
| POST | /transfer | Initiate artifact transfer |
| GET | /transfer/{transfer_id} | Transfer status + progress |
| POST | /transfer/{transfer_id}/cancel | Cancel in-progress transfer |

### Design Rationale

- HTTP matches the Zarya EIP-1 pattern already proven in S6
- JSON serialization is language-agnostic (Rust → Python)
- Localhost-only keeps the boundary secure without auth complexity
- The gateway wraps flux-core; it does not replace it

## Consequences

- Shyam S7 can be completed and tested independently of Flux implementation
- The Flux team receives a concrete, testable specification
- No Flux source code is imported into Shyam (brief §29)
- No networking logic is duplicated in Shyam (brief §6)
- The contract can evolve through versioned endpoints

## Alternatives Considered

1. **Direct Rust FFI / PyO3 bindings**: Rejected — violates §29 (no source
   coupling), creates build complexity, and tightly couples release cycles.
2. **Unix domain socket / named pipe IPC**: Rejected — unnecessary complexity
   for localhost; HTTP is simpler and debuggable.
3. **Wait for Flux to build the API first**: Rejected — blocks S7 indefinitely.

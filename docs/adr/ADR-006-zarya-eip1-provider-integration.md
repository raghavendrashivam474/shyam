# ADR-006: Zarya EIP-1 Provider Integration

## Status

Accepted

## Context

Sprint 5 (ADR-005) established the Local Provider Fabric and populated the
ProviderRegistry with the first concrete local provider (local.filesystem).
However, the registry remained limited to providers running inside the Shyam
process itself.

Zarya v0.9.0-eip1 has been released with a frozen Ecosystem Integration
Protocol (EIP-1) that exposes a documented HTTP boundary over localhost.
This protocol provides identity discovery, capability advertisement,
authenticated work execution, and structured verification outcomes.

Sprint 6 transitions Shyam from a purely local provider model to one that
can consume sovereign external agents as first-class providers, without
importing their source code, embedding their runtime, or redesigning
either project.

## Decision

We establish the **Zarya EIP-1 Provider Integration** as a new provider
package (`shyam.providers.zarya`) that consumes Zarya's published
ecosystem contract and represents a running Zarya instance as a standard
Shyam Provider.

```text
                    SHYAM RUNTIME
                         │
            ┌────────────┴────────────┐
            │                         │
     LocalProviderFabric      ZaryaProvider
            │                         │
            ▼                         ▼
     ProviderRegistry          ZaryaClient
            │                         │
    ┌───────┴───────┐            EIP-1 / HTTP
    ▼               ▼                │
local.filesystem  zarya.agent   localhost:8765
    │               │                │
    ├── file.read   ├── zarya.system.health
    ├── file.write  ├── zarya.work.execute
    └── file.list   └── zarya.work.status
                         │
                         ▼
                      ZARYA
                 (sovereign process)
```

### 1. Protocol Boundary via ZaryaClient

We implement ZaryaClient as a self-contained HTTP client that speaks
zarya-ecosystem / eip-1.0 exclusively. It owns transport, header
injection (X-Ecosystem-Token), request serialization, response
parsing, and structured error mapping. It has zero knowledge of
Shyam's ProviderRegistry, CapabilityRegistry, or orchestration logic.

### 2. Translation Layer via Mapper

`We implement a pure-function mapper (shyam.providers.zarya.mapper)
that translates Zarya wire models into Shyam domain objects`:

```
IdentityResponse + CapabilitiesResponse + StatusResponse → Provider
CapabilityEntry + allowed_tools → Capability
EcosystemStatus → AvailabilityStatus
No Zarya source code is imported. No Shyam internals leak into the
client layer.
```

### 3. Provider Abstraction via ZaryaProvider

```
We implement ZaryaProvider as the Shyam-facing class that holds a
ZaryaClient, manages the connect/disconnect lifecycle, validates
protocol compatibility (eip-1.0), discovers capabilities dynamically,
and delegates work execution. It produces a standard frozen Provider
descriptor with provider_id = "zarya.agent" (satisfying the S4
namespacing validator).
```

### 4. Dynamic Capability Discovery

```
Zarya capabilities are discovered at runtime, not hard-coded.
The provider calls GET /ecosystem/v1/capabilities and maps the
advertised list into Shyam Capability objects. The allowed_tools
list is preserved in capability metadata. If Zarya adds or removes
tools in a future release, Shyam adapts automatically.
```

### 5. Verification Semantics Preserved

```
HTTP 200 does not automatically mean success. The provider
inspects the outcome field (VERIFIED_SUCCESS, VERIFIED_FAILURE,
UNKNOWN) and raises ZaryaVerificationError when verification
explicitly fails. This preserves Zarya's S2 verification contract
and prevents silent data corruption.
```

### 6. Structured Error Mapping

```
All 12 EIP-1 error codes are mapped to typed Python exceptions
(ZaryaAuthenticationError, ZaryaToolNotAllowedError,
ZaryaBusyError, etc.) that preserve the original code,
http_status, and detail fields. No error is collapsed into
a generic ProviderError.
```

### 7. Security Boundary Respected

```
The provider communicates exclusively through the EIP-1 HTTP
boundary. It never attempts SSH, shell, Python RPC, filesystem
access, or internal Zarya API calls. If Zarya returns
TOOL_NOT_ALLOWED, Shyam respects that decision.
```

### 8. Non-Blocking Integration Policy

```
If Zarya is unreachable at startup, ZaryaProvider.connect() returns
False, the runtime logs an informational message, and Shyam
continues operating as a standalone node. Zarya is an optional
ecosystem participant, not a hard dependency.
```

### 9. Runtime Lifecycle Integration

```
The ShyamRuntime.start() method attempts Zarya connection after
the local provider fabric has started. On success, the provider
descriptor and discovered capabilities are registered in the
existing ProviderRegistry and CapabilityRegistry respectively.
Three new configuration fields (zarya_enabled, zarya_url,
zarya_token) are added to ShyamSettings.
```

### 10. Identity Sovereignty

Shyam's NodeIdentity is never replaced by Zarya's device identity.
Zarya's instance identity is preserved in the provider's metadata
dictionary. The relationship is:

```text
Shyam Node
   └── Zarya Provider (zarya.agent)
          └── Zarya Instance Identity (metadata)
```

### Consequences

- The ProviderRegistry is populated with both local.filesystem and
  zarya.agent when a local Zarya instance is running.
- Shyam gains visibility into Zarya's advertised capabilities
  (zarya.system.health, zarya.work.execute, zarya.work.status)
  through the existing CapabilityRegistry.
- 30 new unit tests and 2 new integration tests are added (159 total).
- Code coverage remains at 93%. Ruff linter is fully clean.
- Zero coupling to Zarya's Python implementation or internal
  architecture. The EIP-1 specification is the sole integration
  contract.
- No third-party HTTP libraries are introduced (uses stdlib
  urllib.request).

### Deferred / Out of Scope

- Flux provider integration (S7).
- Ecosystem-wide discovery via mDNS/UDP/LAN scanning (S8).
- Hybrid Navigator and provider selection/routing (S9).
- Workflow engine and composite capabilities (S10–S11).
- Cross-device Zarya discovery and work migration.
- Multi-step work submission and streaming (future EIP-2 candidates).
- Pause/cancel API (not exposed through EIP-1 currently).
- Distributed trust architecture and synchronization.
- NAV integration.
- Any modifications to Zarya's source code or protocol.

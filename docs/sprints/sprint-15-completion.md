# Sprint 15 Completion Report: Device Bootstrap & Recovery

**Sprint:** S15  
**Version:** `0.15.0`  
**Baseline:** `v0.14.0 @ b341fda` (355 tests)  
**Final Status:** 376 tests passing (21 new tests, zero regression)  

---

## 1. Executive Summary

Sprint 15 implements the **device bootstrap and recovery lifecycle** for the Shyam runtime. Prior to S15, Shyam could establish cryptographic identity (S13), manage persistent local trust (S13), and converge peer state facts (S14), but lacked a structured, secure handshake for enrolling fresh devices and recovering nodes that suffered state loss.

S15 coordinates these existing subsystems without rewriting, duplicating, or undermining their boundaries.

---

## 2. Architecture & Subsystem Boundaries

| Subsystem | Owner | S15 Relationship |
|---|---|---|
| **Identity** | S13 | S15 uses S13 `IdentityManager` and `KeyPair` for Ed25519 signing. No new crypto subsystem was created. |
| **Trust** | S13 | S13 `TrustService` remains authoritative. S15 evaluates trust standing (`is_trusted`, `is_revoked`) and registers peer/infrastructure trust. |
| **Synchronization** | S14 | S15 uses S14 `SyncService` to exchange initial state facts after enrollment. |
| **Discovery** | S8 | S15 consumes S8 normalized discovery observations. |
| **Context & State** | S12 | S15 triggers S14 sync convergence, which automatically updates local state. |
| **Connectivity** | Flux / Transport | S15 introduces `BootstrapTransport` protocol, keeping handshake transport decoupled. |

---

## 3. Implemented Components

### `src/shyam/bootstrap/`
- `models.py`:
  - `BootstrapState`: 11-state validated lifecycle state machine (`UNINITIALIZED` -> `IDENTITY_READY` -> `BOOTSTRAP_REQUESTED` -> `AUTHENTICATING` -> `TRUST_ESTABLISHED` -> `STATE_INITIALIZING` -> `SYNCING` -> `READY`).
  - `BootstrapRequest` / `BootstrapResponse`: Immutable signed handshake wire payloads.
  - `BootstrapSession`: Local multi-step session manager enforcing valid state transitions.
  - `RecoveryScenario` / `RecoveryRequest` / `RecoveryResult`: Distinct recovery path models.
- `errors.py`: Exception hierarchy (`BootstrapError`, `BootstrapRejectedError`, `BootstrapTimeoutError`, `RecoveryError`).
- `transport.py`: `BootstrapTransport` protocol abstraction.
- `service.py`:
  - `handle_incoming_request()`: Authority-side verification (signature check + S13 revocation gate + trust grant).
  - `execute_client_bootstrap()`: Client-side multi-step coordinator.
  - `recover_device()`: Scenario-specific recovery engine.
- `__init__.py`: Clean public API export.

### `src/shyam/core/runtime.py`
- Additive integration: Exposed `.bootstrap` property returning the initialized `BootstrapService`.

---

## 4. Security & Recovery Guarantees

1. **Cryptographic Authentication**: Every `BootstrapRequest` requires an Ed25519 signature over canonical request fields verified against the claimed public key.
2. **Revocation Enforcement**: Revoked nodes in S13 trust store are hard-rejected (`BootstrapOutcome.REJECTED_REVOKED`).
3. **Identity-Loss Safety (Case B)**: If a device loses its private key or identity, S15 refuses automatic identity restoration. It enforces generation of a fresh identity to protect existing trust relationships.
4. **State-Loss Recovery (Case A)**: Nodes with intact cryptographic identity can re-synchronize version maps and restore facts via S14.
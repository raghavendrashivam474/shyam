# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.7.0] - 2026-09-19 (Milestone S7 Flux Provider Integration)

### Added
- **Flux Gateway Integration (S7)**:
  - `src/shyam/providers/flux/models.py`: Contract models for Flux Gateway API v1 (`FluxIdentityResponse`, `FluxStatusResponse`, `FluxPeerInfo`, `FluxPathInfo`, `FluxTransferRequest`, `FluxTransferResponse`, `FluxTransferStatusResponse`, `FluxCancelResponse`).
  - `src/shyam/providers/flux/exceptions.py`: Typed boundary exceptions (`FluxClientError`, `FluxConnectionError`, `FluxProtocolError`, `FluxPeerNotFoundError`, `FluxTransferError`, `FluxUnavailableError`).
  - `src/shyam/providers/flux/client.py`: Stdlib HTTP client for communicating across the Flux Gateway v1 boundary (`http://127.0.0.1:9100/flux/v1`).
  - `src/shyam/providers/flux/mapper.py`: Semantic translation layer registering 5 invokable connectivity capabilities (`connectivity.peer_discovery`, `connectivity.peer_resolution`, `connectivity.session`, `connectivity.transfer`, `connectivity.transfer_resume`) while classifying multi-path and health properties as provider metadata/status.
  - `src/shyam/providers/flux/provider.py`: High-level `FluxProvider` managing provider descriptor, capability definitions, status polling, and delegated peer/transfer operations.
- **Runtime Lifecycle Integration**:
  - `ShyamSettings` extended with `flux_enabled` and `flux_url`.
  - `ShyamRuntime.start()` connects to Flux Gateway with non-blocking graceful fallback when Flux is offline.
- **Architectural Decision Record**:
  - `docs/adr/ADR-007-flux-provider-contract-first.md`: Contract-first gateway integration model for Aryntra Flux.
- **Testing & Verification**:
  - 20 unit tests across Flux models, exceptions, mapper, client, and provider.
  - 3 runtime integration tests covering offline standalone, online registration, and disabled bypass.

## [0.0.0] - Unreleased (Milestone S0 Foundation)

### Added
- Repository foundation established.
- Initial project structure and directory layout created.
- Python packaging configuration (`pyproject.toml`) targeting Python 3.13+.
- Core architecture documentation and ecosystem boundaries established.
- Sovereign integration boundaries documented for Zarya and Aryntra Flux.
- ADR (Architectural Decision Record) workflow initialized.
- Development setup and contribution discipline guidelines created.

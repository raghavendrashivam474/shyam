# Aryntra Flux Integration Boundary

## 1. Role of Aryntra Flux in the Shyam Ecosystem

Aryntra Flux is the sovereign connectivity and resilient data-movement substrate across the personal computing mesh.

Within the Shyam architecture:
> **Shyam decides what needs to reach where. Flux decides how it gets there.**

Shyam expresses high-level data movement and synchronization intent. Flux is solely responsible for determining transport mechanisms, routing paths, chunking, session multiplexing, resume mechanics, and transfer integrity verification.

---

## 2. The Authoritative Transport Boundary

```text
       SHYAM
         │
         │  1. High-Level Data Transfer Intent
         │     ("Transfer Artifact X to Peer Y")
         ▼
┌────────────────────────────────────────────────────────┐
│                    ARYNTRA FLUX                        │
│                                                        │
│   Peer Discovery ──► Path Probing ──► Transport Select │
│                                              │         │
│   Transfer Integrity ◄── Resume ◄── Chunking ◄─────────┘
└────────────────────────────┬───────────────────────────┘
                             │
         ▲                   │
         │  2. Transfer Progress & Verified Status
         └───────────────────┘
```

## 3. Boundary Matrix
| Domain | Owner | Description |
| --- | --- | --- |
| **Transfer Intent** | Shyam | Determines that an artifact or state payload must be delivered to a target peer. |
| **Target Peer Identity** | Shyam | Identifies the logical peer identity within the personal mesh topology. |
| **Peer Discovery** | Flux | Discovers target peer availability across LAN, WAN, BLE, relay, or direct links. |
| **Path Discovery & Health** | Flux | Evaluates latency, bandwidth, NAT type, and packet loss across active paths. |
| **Path & Transport Selection** | Flux | Selects optimal protocol (QUIC, TCP, WebRTC, BLE, Unix Sockets, Relay). |
| **Session Multiplexing** | Flux | Manages concurrent stream multiplexing over active connections. |
| **Chunking & Checksums** | Flux | Splits large payloads into verified chunks and computes per-chunk hashes. |
| **Resume & Retries** | Flux | Automatically recovers interrupted transfers without restarting from zero. |
| **Transfer Integrity** | Flux | Cryptographically verifies that the received payload matches the source. |
| **Transfer Status Delivery** | Flux | Emits progress, completion, or failure events back to Shyam. |

## 4. Non-Negotiable Integration Rules

1. **No Transport Mechanics in Shyam**: Shyam must never implement socket handling, TCP/QUIC protocols, 
   chunking logic, retry backoffs, or network path probing.
2. **Abstract Endpoint Addressing**: Shyam addresses destinations using high-level peer IDs and artifact hashes, 
   not ephemeral IP addresses or port numbers.
3. **Sovereign Path Selection**: Shyam cannot force a specific low-level network path over Flux's internal routing metrics.
4. **Adapter Decoupling**: Integration with Flux occurs through dedicated provider adapter contracts (to be implemented in S6).


## 5. S7 Flux Gateway API v1 Contract (ADR-007)

To preserve architectural decoupling and solve the lack of a built-in HTTP server in `flux-node` v2.3.0, S7 establishes a contract-first **Flux Gateway HTTP API** running locally at `http://127.0.0.1:9100/flux/v1`.

### Authoritative Endpoints

| Method | Path | Request Body | Response Shape |
|---|---|---|---|
| `GET` | `/identity` | None | `FluxIdentityResponse` |
| `GET` | `/status` | None | `FluxStatusResponse` |
| `GET` | `/peers` | None | `FluxPeersResponse` |
| `GET` | `/peers/{peer_id}` | None | `FluxPeerInfo` |
| `POST` | `/connect` | `{"peer_id": "..."}` | `FluxConnectResponse` |
| `POST` | `/transfer` | `{"peer_id": "...", "artifact_path": "..."}` | `FluxTransferResponse` |
| `GET` | `/transfer/{transfer_id}` | None | `FluxTransferStatusResponse` |
| `POST` | `/transfer/{transfer_id}/cancel` | None | `FluxCancelResponse` |

### Error Payload Specification
Errors returning from the gateway utilize a standard structured format matched by `FluxClientError`:
```json
{
  "code": "peer_not_found",
  "message": "Requested peer is not known to Flux",
  "detail": {
    "peer_id": "550e8400-e29b-41d4-a716-446655440000"
  }
}
```
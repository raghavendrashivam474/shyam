# S17.9.1 — Real Physical Ecosystem Test Plan

## Test Objectives
1. **Discovery**: Machine A discovers Machine B over real LAN with real LAN IP and endpoints.
2. **Trust**: Machine A establishes S13 PEER trust with Machine B.
3. **Flux Transfer**: Real artifact hash generated on A and verified on B.
4. **Zarya Continuation**: Machine A invokes remote Zarya on Machine B with verification.
5. **Surface/UI Flow**: Natural language query drives end-to-end execution.
6. **Integrity & Negatives**: Hash verification matching, untrusted target rejection, and failure isolation.

## Machines
- **Machine A (Source)**: LAPTOP-P6FQOQ5E (LAN: 10.177.67.156)
- **Machine B (Target)**: Remote device on same LAN

## Port Allocation
- Discovery Port: 54322 (UDP broadcast)
- Target Zarya Endpoint: Provided by Machine B
- Target Flux Endpoint: Provided by Machine B

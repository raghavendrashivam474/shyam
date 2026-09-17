# Zarya Integration Boundary

## 1. Role of Zarya in the Shyam Ecosystem

Zarya is the sovereign desktop-agent and computer-work execution platform. 

Within the Shyam architecture:
> **Shyam orchestrates. Zarya executes and verifies.**

Shyam treats Zarya as an authoritative execution provider. Shyam requests bounded tasks from Zarya and ingests verified execution outcomes, without attempting to manage or replicate Zarya's internal execution loops.

---

## 2. The Authoritative Execution Boundary

Zarya maintains total ownership over its execution lifecycle:

```text
       SHYAM
         │
         │  1. Bounded Request (Action Specification)
         ▼
┌────────────────────────────────────────────────────────┐
│                        ZARYA                           │
│                                                        │
│   Intent ──► Action ──► Observation ──► Verification   │
│                                              │         │
│                                              ▼         │
│                                           Outcome      │
└──────────────────────────────────────────────┬─────────┘
                                               │
         ▲                                     │
         │  2. Verified Execution Outcome      │
         └─────────────────────────────────────┘
```

## 3. Boundary Matrix

| Domain | Owner | Description |
| --- | --- | --- |
| **Ecosystem Workflow** | Shyam | Decides that a task needs to be performed as part of a multi-step user goal. |
| **Provider Selection** | Shyam | Selects Zarya on a specific host as the appropriate execution provider. |
| **Execution Request** | Shyam | Passes a bounded intent/contract payload to Zarya. |
| **Execution Authorization** | Zarya | Confirms local user consent and security policies before acting. |
| **Tool / Desktop Execution** | Zarya | Interacts with the host OS, GUI, CLI, filesystem, or APIs. |
| **Safety & Sandboxing** | Zarya | Enforces execution constraints, process containment, and safety rails. |
| **Observation & State** | Zarya | Captures execution state, terminal outputs, and intermediate UI states. |
| **Verification** | Zarya | Validates that the requested action actually succeeded against expected criteria. |
| **Outcome Reporting** | Zarya | Returns structured outcome, verified artifacts, or failure reasons to Shyam. |

## 4. Non-Negotiable Integration Rules

1. **No Authorization Bypassing**: Shyam cannot instruct Zarya to bypass its local permissions, consent prompts, 
   or safety policies.
2. **No Execution Internals Emulation**: Shyam does not inspect raw desktop handles, OS windows, or process 
   memory directly when delegating to Zarya.
3. **Verified Outcome Reliance**: Shyam accepts execution outcomes only as attested by Zarya's verification boundary. 
   If Zarya marks an action as unverified or failed, Shyam must handle it as such.
4. **Adapter Decoupling**: Communication between Shyam and Zarya occurs through defined adapter 
   contracts (to be implemented in S5), preserving the complete sovereignty of both platforms.

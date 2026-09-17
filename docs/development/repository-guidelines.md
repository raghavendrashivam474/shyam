# Repository Guidelines & Architecture Governance

>To ensure the Shyam repository remains maintainable and pure across all roadmap milestones, all contributors must observe these rules.

## 1. Milestone Isolation Rule

>"Never implement architecture or features intended for future milestones."

- S0: Repository foundation, boundaries, docs, package metadata.
- S1: Runtime skeleton.
- S2: Capability model.
- ...
- Do not write empty skeleton classes (e.g., class HybridNavigator: pass) in milestones before their designated phase.

## 2. The Architectural Drift Rule

>"Existing architectural decisions have priority over personal preference."

Before refactoring or relocating files:

1. Inspect the existing structure and understand its intent.
2. If you identify a structural flaw, write an Architectural Decision Record (ADR) under docs/adr/.
3. Receive consensus on trade-offs before executing refactors.

## 3. Package & Directory Rules

- src/shyam/: The core library namespace. All production code belongs inside appropriate subpackages.
- packages/: Modular standalone workspace packages that may be distributed independently.
- apps/: Concrete application binaries or entry point services (e.g., CLI, daemon, desktop host).
- tests/: Organized strictly into unit/, integration/, and contract/.
- docs/: Keep synchronized with code modifications.

## 4. Git & Commit Etiquette

1. Always verify working tree status before committing: git status.
2. Inspect your changes line-by-line: git diff.
3. Use Conventional Commits:
    - feat: A new user-facing capability.
    - fix: A bug fix.
    - docs: Documentation-only changes.
    - chore: Build, repo setup, dependency maintenance.
    - refactor: Code change that neither fixes a bug nor adds a feature.

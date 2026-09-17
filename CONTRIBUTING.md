# Contributing to Shyam

Thank you for contributing to Shyam. To maintain architectural purity, reproducibility, and stability, all contributors must follow these guidelines.

---

## 1. Architectural Guardrails

Shyam is a **local-first, decentralized personal computing ecosystem and orchestration layer**.

Always remember the fundamental boundaries:
* **Shyam orchestrates. Zarya executes and verifies.**
* **Shyam decides what needs to reach where. Flux decides how it gets there.**
* **Shyam must not absorb the internals of Zarya, Flux, or any other sovereign product.**

---

## 2. The Golden Rule: Existing Work Has Priority

> **Never delete, rewrite, rename, or restructure an existing file merely because you would personally design it differently.**

Before changing an existing architectural artifact:
1. **Inspect:** Understand the current implementation and rationale.
2. **Identify:** Clarify the specific problem or limitation.
3. **Propose:** Draft an Architectural Decision Record (ADR) under `docs/adr/`.
4. **Approve:** Agree upon the trade-offs.
5. **Implement:** Execute the change cleanly with updated tests and docs.

---

## 3. Development Discipline

### Before Coding
1. Check `git status` and ensure your working tree is clean.
2. Read the relevant milestone brief and subsystem documentation in `docs/`.
3. Identify affected subsystems and interfaces.
4. Verify you are not duplicating an existing abstraction.

### During Coding
1. Keep changes tightly scoped to the current milestone/task.
2. Do not modify unrelated files.
3. Do not introduce dependencies without explicit justification.
4. Do not bypass established product boundaries.
5. Do not write premature implementations or "mock/fake" future milestone architecture.

### Before Committing
1. Run test suite: `pytest`.
2. Review the diff: `git diff`.
3. Verify documentation reflects all code changes.
4. Confirm no accidental or temporary files are staged.
5. Use clear, conventional commit messages: `feat:`, `fix:`, `docs:`, `chore:`, `refactor:`.

---

## 4. Architectural Decision Records (ADR)

If you discover that the current architecture needs to change:
1. Create a new file in `docs/adr/` following the format: `docs/adr/NNNN-short-title.md`.
2. Include sections: **Status**, **Context**, **Decision**, **Alternatives**, **Consequences**, and **Migration**.
3. Link the ADR in PR discussions.

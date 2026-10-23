# tests/ (shared)

Cross-component and safety-invariant tests. Component unit tests live next to each component (`server/tests/`, `simulator/tests/`, ...).

- `test_contracts.py`: every schema is valid JSON Schema, every example validates, forbidden family fields are rejected, both OpenAPI files are valid. **Runs today.**
- `test_invariants.py`: one test per safety invariant in `RULES.md` (1–13). Tests that need components which are not built yet are marked `skip` with the phase that unblocks them. Turn each one on as its component lands.

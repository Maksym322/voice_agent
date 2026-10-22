# VF-002 acceptance record

Repository: `voice`, based on `0d7c6c2` (`vf-001-foundation`). Implementation
branch: `vf-002-agent-configurations`. Checks ran in an isolated local clone
using the original checkout's installed, pinned Python and Node dependencies.

VF-002 adds a versioned Pydantic/JSON Schema contract, draft import and export,
immutable published snapshots, environment bindings with revision checks, audit
events, and a minimal dashboard editor. Migration `0002_agent_configurations`
adds the tables and a database trigger that rejects published-row changes.

## Criteria

| Criterion | Evidence | Status |
| --- | --- | --- |
| Invalid configurations rejected with actionable errors | Unit validation and HTTP 422 tests; schema exposed in OpenAPI | Passed |
| Published versions cannot be edited | No edit endpoint; PostgreSQL trigger and integration test reject direct update | Passed |
| Atomic activation and explicit concurrent conflicts | Agent row lock plus expected binding revision; simultaneous requests yield 200/409 | Passed |
| Rollback to a previous compatible version | HTTP and browser tests bind v2, then v1; schema version checked | Passed |
| Exports contain no secrets | Schema rejects unknown fields, raw provider values, and common credential patterns; export contains references and published snapshot only | Passed for validated contract; free-text review remains an operator responsibility |
| Viewers cannot modify configurations | HTTP role tests for publish and activation; all mutations share the same role guard | Passed |

## Checks

| Command (isolated clone) | Exit code | Result |
| --- | --- | --- |
| Ruff check and format check on `apps tests scripts` | 0, 0 | Passed |
| Mypy on API, worker, and tests | 0 | Passed |
| Pytest unit | 0 | 13 passed |
| Disposable PostgreSQL integration suite | 0 | 6 passed |
| Biome and TypeScript typecheck | 0, 0 | Passed |
| `npm run build` | 0 | Passed |
| Disposable Chromium browser suite | 0 | 2 passed |

The first sandboxed `uv run` could not read the shared uv cache, so the checks
above used the original checkout's pinned virtual environment. An initial Vite
invocation from the repository root used the wrong entry directory; the actual
`npm run build` command passed. The standalone formatter check initially found
new formatting changes, which were applied; its final run passed. No paid API
or live voice service was used. Detailed local check reports are in the
`voice-fleet-dev/artifacts/vf002-*.json` files.

## Contracts and documentation

See `docs/configuration.md` for schema, endpoints, concurrency, roles, and
bindings; `docs/migrations.md` for the migration and downgrade impact; and
`docs/testing.md` for the tests. Dependencies did not change. VF-003 will pin
published versions to actual sessions; VF-002 has no voice runtime.

## Manual acceptance

1. Start the documented Compose stack and sign in as an admin or operator.
2. Create an agent with instructions, publish v1, edit its JSON draft, and publish v2.
3. Activate v2 locally, then activate v1. Confirm the displayed binding changes.
4. Export v1 and v2 and confirm distinct instructions, references only, and no raw credentials.
5. Open two tabs on the same draft, save in one, and confirm the second reports a revision conflict.
6. Sign in as a viewer and confirm the editor offers no mutation controls; API writes should return 403.
7. Remove the synthetic agent only in a disposable installation; this version has no delete API.

Code completion: verified; ready for owner acceptance.
Human acceptance: pending owner review.

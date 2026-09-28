# VF-003 progress record

## Current verification update 2026-09-27

The owner approved a bounded synthetic Ukrainian live test using LiveKit
Cloud, Deepgram Nova-3, Gemini 3.5 Flash-Lite, and Cartesia Sonic 3. Two
headless Chromium calls produced caller and agent transcripts and nonzero
remote audio. One call recorded 1178 ms server-side speech-end to audio-start
latency; both ended with room cleanup complete. A prior Gemini 2.5 call
returned 404 for a new API project and was safely recorded as an error.
Current checks passed: 21 unit, 17 disposable PostgreSQL integration,
Ruff/format/Mypy, the earlier 3 Chromium UI tests, and a real console browser
smoke using the successful and failed sessions. The owner then confirmed
hearing the response and seeing both transcripts in a manual browser check.
The owner's two sessions both ended with room cleanup complete and both
transcript sides. One included a worker interruption event and a partial agent
turn; a subsequent browser check found its `Interrupted; partial output` label
in History. Perceived interruption timing, disconnection, and duration-cap
acceptance remain pending.
See `docs/vf-003-acceptance.md` for conditions and remaining steps.

## Historical verification update 2026-09-26

The later VF-009 implementation builds on the completed VF-003 worker code.
Latest local checks passed: 18 unit tests, 16 disposable PostgreSQL
integration tests, clean Compose startup after the optional Gemini dependency,
and Python Ruff/format/Mypy. The earlier 3 disposable Chromium browser tests
and web lint/typecheck/build passed before the backend-only Gemini addition.
These were the counts at that checkpoint; historical observations are
retained for traceability. See `docs/vf-003-acceptance.md` and
`docs/vf-009-acceptance.md`.

## Update 2026-09-26: worker implementation

The isolated working copy now registers `voice-fleet-playground` with LiveKit
Agents 1.8.3, verifies dispatch against a pending database session and room,
loads the pinned published snapshot, and constructs a direct Deepgram Nova-3 /
OpenAI GPT-4o mini / Cartesia Sonic 3 pipeline. It emits caller interim/final
transcripts, agent delivered/interrupted transcripts, connection, disconnection,
error, and latency events. It closes the room on worker termination or provider
failure. API logout now closes owned rooms before revoking authorization, and
missing LiveKit configuration is documented as a preflight 503 without a row.
The API purges terminal rows and events on an hourly sweep after the pinned
retention period. Audio recording is disabled.

The direct-provider stack is a **provisional implementation preset**, not an
owner-approved provider or cost decision. No live credentials were inspected,
no paid service was contacted, and audible browser speech, interruption,
provider outage, network loss, and measured latency remain unexecuted. Worker
and browser code completion therefore does not establish VF-003 acceptance.

Latest synthetic evidence: 15 unit tests passed; 11 disposable PostgreSQL HTTP
integration tests passed, including pinned worker lifecycle writes and logout
cleanup. Python Ruff lint, source formatting, and Mypy passed. The first
integration invocation failed because the Windows sandbox denied the helper's
temporary Compose `.env`; the authorized rerun passed. See the dated JSON
check reports in `voice-fleet-dev/artifacts`. Browser lint, typecheck, and build
must be rerun after the final changes. The earlier `ruff format --check .`
failure from inaccessible disposable artifacts remains a traversal issue; use
the documented scoped source check.

### Remaining manual acceptance

1. Confirm providers/models, language, maximum live-test spend, and LiveKit
   Cloud or self-hosted endpoint. Put keys only in ignored `.env` or a secret
   store and set provider-side spend limits; the server's duration cap is not a
   monetary cap.
2. Start a disposable installation, publish/activate an agent, speak through
   the browser, and confirm audible speech and two-sided timestamped transcript.
3. Activate a new version during a conversation and verify the old session
   keeps its original instructions/model/voice while a new session uses v2.
4. Interrupt speech, disconnect the browser, simulate a provider outage, sign
   out during speech, and confirm the correct final state, error code, and room
   cleanup. Confirm viewer/anonymous access is denied and duration is capped.
5. Record actual model IDs, language, session duration, observed latency and
   network conditions. Stop the disposable stack without deleting real data.

## Earlier implementation record (before the worker update)

Repository and revision: isolated `vf-003-voice-playground` checkout based on
`dcc59c9` (`vf-002-agent-configurations`). The source Voice checkout was clean
and remains unchanged. This record covers the working tree, including untracked
files; no commit or deployment has been made.

The API now stores sessions against immutable published versions, issues
room-scoped microphone tokens, creates and explicitly dispatches LiveKit rooms,
limits concurrent sessions, exposes session/event reads, and closes rooms on
request, duration, or worker startup timeout. The browser can join a room,
publish microphone audio, play remote audio, and display status and transcript
events. The actual LiveKit Agents worker is still a scaffold pending the
provider/model, language, budget, and hosting decisions.

## Criteria

| Criterion | Evidence | Status |
| --- | --- | --- |
| User hears a real response | Worker does not yet construct an STT/LLM/TTS pipeline; no live provider call or audible test | Unexecuted |
| Session pins a version across publication | Session row stores immutable `version_id`; PostgreSQL HTTP test activates v2 after starting on v1 and confirms the row remains on v1 | Passed for API storage; worker use pending |
| Interruptions and disconnections | Browser handles LiveKit disconnect, clears audio, and calls end; no worker interruption or real network test | Pending manual acceptance |
| Provider unavailability reports error and releases resources | Synthetic room-start failure returns 503 with an error row; server closes worker startup timeouts and expired rooms | Passed for LiveKit startup and timeout substitutes; STT/LLM/TTS errors unexecuted |
| Unauthorized users cannot obtain room tokens | HTTP test rejects missing CSRF and viewer starts; decoded JWT test proves room, microphone, and five-minute grants | Passed with synthetic credentials |
| Session duration is limited | API uses the lower of published limit and server cap; PostgreSQL HTTP test verifies deadline and sweeper closure | Passed with a synthetic room substitute; live timing unexecuted |

## Checks

| Command and working directory | Actual exit code | Result | Evidence / reason |
| --- | --- | --- | --- |
| `uv run --frozen --all-packages pytest tests/unit -q` in isolated checkout | 0 | Passed | 14 tests; synthetic key only |
| `.venv/Scripts/python.exe scripts/check_integration.py` in isolated checkout via check runner | 0 | Passed | Disposable PostgreSQL Compose stack; 9 tests, synthetic LiveKit room substitute |
| `uv run --frozen --all-packages ruff check apps tests scripts` | 0 | Passed | Scoped source check |
| `uv run --frozen --all-packages ruff format --check apps tests scripts` | 0 | Passed | Scoped source check |
| `uv run --frozen --all-packages mypy apps/api/src apps/voice-worker/src tests` | 0 | Passed | Strict Python types |
| `npm run lint` and `npm run typecheck` | 0, 0 | Passed | Biome and TypeScript |
| `npm run build` | 0 | Passed | Vite production bundle with sandbox permission for Windows spawn |
| `ruff format --check .` | 101 | Failed | Ruff panicked while walking inaccessible disposable test artifacts; scoped source check passed |
| Live voice smoke test and latency measurement | No exit code | Unexecuted | Provider/model, language, budget, hosting mode, and local credentials pending |
| Manual interruption and disconnection checks | No exit code | Unexecuted | Requires working voice pipeline and browser audio |
| Hosted CI and browser voice E2E | No exit code | Unexecuted | No hosted run or live substitute browser case in this branch |

Early lint, format, browser build, and Docker runs exposed formatting and
Windows sandbox restrictions. Formatting was fixed. The browser build and
PostgreSQL integration suite passed after running with the needed permissions.
The actual check output and exit codes are retained in
`voice-fleet-dev/artifacts/vf003-*.json`.

## Contracts and documentation

Migration `0003_voice_sessions` adds `voice_sessions` and `session_events`.
`docs/sessions.md` documents HTTP access, token scope, lifecycle, limits, and
environment settings. `.env.example` and Compose carry optional LiveKit
settings. LiveKit API 1.2.1, LiveKit Agents 1.8.3, and browser client 2.22.3
are pinned in the package manifests and lockfiles. The implemented token,
dispatch, session, and browser track APIs were checked against the official
[LiveKit dispatch](https://docs.livekit.io/agents/server/agent-dispatch/),
[tokens](https://docs.livekit.io/frontends/reference/tokens-grants/), and
[client SDK](https://docs.livekit.io/reference/client-sdk-js/) documentation.

## Limitations

The owner has not selected STT/LLM/TTS providers and models, a budget, the
conversation language, or LiveKit Cloud versus self-hosted mode. No provider
credentials were read or used. The worker has no voice pipeline, so transcripts,
metrics, model versions, and latency cannot yet be measured. The server duration
sweeper needs the API process and reachable LiveKit server to close rooms.
Transcript retention cleanup is not implemented yet; do not use real client
audio in this incomplete branch.

## Manual acceptance

1. Select the provider/model set, budget, language, and LiveKit hosting mode;
   supply credentials locally. Complete the worker and separate live smoke test.
2. In a disposable installation, publish and activate an agent, start a browser
   session, allow microphone access, speak, and confirm an audible reply.
3. Publish and activate another version while speaking; confirm the active
   session stays on its original version and a new session uses the new one.
4. Interrupt the agent, disconnect the network, deny the microphone, make a
   provider unavailable, and verify errors and room cleanup.
5. Sign in as a viewer and as an anonymous browser; confirm neither receives a
   room token. Confirm the session ends at its limit and record model versions,
   latency, and measurement conditions.
6. Remove only the disposable installation's test data and provider credentials.

Code completion: pending the real worker, live smoke test, and transcript policy.
Human acceptance: pending.

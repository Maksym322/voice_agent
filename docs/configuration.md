# Конфігурація

Клієнтський пакет: client.yaml, agents/, knowledge/, branding/, deployment/.
Секрети передаються середовищем або secret store, у файлах лише посилання.

Поля: schema_version, organization, branding, enabled_modules,
agent definitions, provider references, tool allowlists, locale, timezone,
session limits, retention policy.

Файл імпортується як валідована чернетка. Runtime читає опубліковану
версію з бази. Експорт повертає конфігурацію без секретів.
Не допускається неявне перезаписування UI-змін файлом.

Стани: draft -> published -> active binding.
Публікація створює незмінний snapshot. Активація атомарно змінює binding.
Активні розмови зберігають свою версію.

## VF-002 JSON contract

`AgentConfig` is the versioned API schema (`GET /openapi.json` exposes its JSON
Schema). Version 1 requires `instructions` and accepts `locale`, `timezone`,
`provider_references`, `tool_allowlist`, `enabled_modules`, `branding`,
`session_limit_seconds`, `retention_days`, and `voice`. The `voice` object pins
the supported Deepgram Nova-3 STT, OpenAI GPT-4o mini or Google Gemini 2.5
Flash-Lite / 3.5 Flash-Lite LLM, and Cartesia Sonic 3 TTS model IDs and a Cartesia voice ID in
each published snapshot. OpenAI remains the default; selecting Google requires
both `voice.llm_provider="google"` and
`voice.llm_model="gemini-3.5-flash-lite"` in the draft before publication.
Older published 2.5 Flash-Lite snapshots remain valid, though Google limits
access to existing users of that model.
The worker then reads `GOOGLE_API_KEY` rather than `OPENAI_API_KEY`. Only the
selected LLM key is required. This is a provisional provider choice pending
the owner decision; changing a draft cannot alter a
running session's model selection. Unknown fields and unsupported
schema versions fail validation with field-level HTTP 422 errors. Provider
values must be `env:NAME` or `secret:NAME` references. Do not enter raw secrets
in instructions or branding text; those fields are part of an export.

`POST /api/agents` creates a draft. `PUT /api/agents/{id}/draft` saves it;
`POST /api/agents/{id}/import` validates a JSON configuration and replaces the
draft. Both draft mutations require `If-Match: <current draft revision>`.
`POST /api/agents/{id}/publish` also requires that revision and creates a new
immutable snapshot. `GET /api/agents/{id}/versions/{version_id}/export` returns
the validated snapshot, with references but no secret values. There is no
published-version edit endpoint, and the database rejects updates and deletes.

`PUT /api/agents/{id}/bindings/{environment}` accepts a published version ID
and `expected_revision` (0 if no binding exists). `local`, `staging`, and
`production` are supported. An agent row lock serializes publication, draft
edits, and binding changes. Stale revisions return HTTP 409. Binding a previous
version performs rollback for future sessions. The target must belong to the
agent and use a supported schema version. Runtime session pinning starts in
VF-003; VF-002 does not start sessions. The VF-003 session row references the
published version selected by the environment binding at start. Later binding
changes cannot change this row. See `docs/sessions.md` for the session API.

All reads require sign-in. Admins and operators can mutate configurations;
viewers can read only. Mutations require the existing CSRF and Origin checks.
Create, edit, import, publish, and activation write audit events with actor,
time, and identifiers. Audit details never store full configuration text.

## VF-005 phone route configuration

Phone numbers and their active agent routes are stored per installation in
PostgreSQL and are excluded from agent configuration exports. Admins may add a
number only when it is actually owned and an active agent binding exists.
`INBOUND_SIP_ALLOWED_ADDRESSES` is a comma-separated carrier origination IP/CIDR
allowlist in ignored `.env`; it is required to create an inbound LiveKit trunk.
No default carrier or number is provisioned. `OUTBOUND_SIP_TRUNK_ID` and
`OUTBOUND_TEST_DESTINATION` remain independent settings for the bounded manual
outbound call. When an owned number is ported, deactivate its route, update
`INBOUND_SIP_ALLOWED_ADDRESSES` for the new carrier, restart the API, and
reactivate the same inventory row with the new carrier label. See
`docs/sessions.md` for API and session direction contracts.

## VF-011 Voice LLM selection in agent form

The web management console (`AgentEditor`) provides visible, labelled form controls
for LLM provider and model selection during both agent creation and editing,
without requiring direct JSON manipulation.

### Form controls and UI preset
- **Creation preset**: The new-agent form initializes with the owner-selected browser-pilot preset
  Google (`llm_provider: "google"`) and Gemini 3.5 Flash-Lite (`llm_model: "gemini-3.5-flash-lite"`).
  This preset is strictly a UI default; backend defaults (`openai / gpt-4o-mini`) remain unchanged.
- **Provider & model options**: Controls are labelled `LLM provider` and `LLM model`.
  Selecting a provider restricts the model choices to those permitted by the server contract:
  - `google`: `gemini-3.5-flash-lite`, `gemini-2.5-flash-lite` (legacy snapshot support)
  - `openai`: `gpt-4o-mini`
  Arbitrary unsupported models are never added to the selectable choices.
- **Explicit selection**: The selected pair is displayed clearly before submission (e.g. `Selected LLM: Google / gemini-3.5-flash-lite`).
  The UI never silently substitutes OpenAI when Google is chosen. The availability of an option does
  not imply the model is free, authenticated, or verified.
- **Coherent state & field preservation**: Form controls and advanced configuration JSON share one coherent state.
  Changing the provider or model in the form updates the JSON representation while preserving all other configuration
  fields (`instructions`, `locale`, `timezone`, `provider_references`, `tool_allowlist`, `enabled_modules`, `branding`,
  session limits, and retention policy). Manual edits to valid JSON synchronize back to the form controls.
  If the `voice` object is removed or omitted in the advanced JSON, the controls immediately reflect the effective backend
  defaults (`openai / gpt-4o-mini`), preventing false display of Google.
- **Validation before Save & Import**: Effective provider/model pairs are validated against the server contract before
  submitting a save or import. Unsupported models (e.g. `bogus-model`), missing models when provider is Google, or
  mismatched pairs produce visible error alerts and block write requests without sending API calls.
- **Malformed JSON protection**: If the configuration JSON is invalid or malformed, the editor displays a visible error alert
  and rejects the save operation before sending an API request. Attempting to change dropdowns while JSON is malformed
  displays an error alert without mutating control state or discarding unsaved text.
- **Draft vs. Active separation**: The saved draft model (`Draft LLM`) is displayed separately from the locally active
  version model (`Local active LLM`). Saving a draft updates only the draft row and never triggers publication or activation.
  If no local binding exists or active model details cannot be retrieved, the UI explicitly displays `Local active LLM: unavailable`.
- **Role authorization**: Viewers have read-only access. When signed in as a viewer, configuration creation, editing, draft saving,
  import, publication, and activation controls are hidden. The configuration JSON is displayed as preformatted text.

### Owner acceptance steps

1. Sign in to a disposable local stack as an operator or admin (`vf001-admin@example.com`).
2. Navigate to Agents and verify that the Create agent form displays labelled `LLM provider` and `LLM model` controls
   defaulting to `Google / gemini-3.5-flash-lite`, with the selected pair visible before submission.
3. Enter agent name and instructions, submit creation, and confirm that the created draft has `Draft LLM: google / gemini-3.5-flash-lite`
   and the draft JSON contains `voice.llm_provider="google"` and `voice.llm_model="gemini-3.5-flash-lite"`.
4. Replace the advanced JSON with a configuration omitting the `voice` object (e.g. `{"schema_version": 1, "instructions": "..."}`).
   Verify that the dropdowns immediately update to display the effective backend default `OpenAI / gpt-4o-mini` rather than falsely displaying Google.
   Save the draft and verify that the outgoing payload sends no `voice` object while the saved draft confirms `openai / gpt-4o-mini`.
5. Enter unsupported pairs in the JSON (e.g. `voice.llm_model="bogus-model"`, missing `llm_model` with `google`, or mismatched provider/model).
   Verify that a visible error alert is displayed, unsupported models are not appended to the model dropdown, and clicking `Save draft`
   or `Import JSON into draft` blocks write requests.
6. Enter malformed JSON and attempt to change the dropdown. Verify that an error alert is displayed, dropdown state does not change first,
   and the unsaved malformed text in the textarea is preserved.
7. Enter a valid OpenAI configuration with unrelated fields (`locale`, `timezone`, `tool_allowlist`).
   Switch to Google via dropdown, confirm all unrelated fields are preserved, select legacy `gemini-2.5-flash-lite`, save, and then switch to `gemini-3.5-flash-lite`.
8. Publish the draft and activate v1 locally. Confirm `Local active version: 1` and `Local active LLM: google / gemini-3.5-flash-lite`.
9. Switch the draft's LLM provider to `OpenAI` (`gpt-4o-mini`), save the draft, and confirm that:
   - `Draft LLM` updates to `openai / gpt-4o-mini`.
   - `Local active version` remains `1` and `Local active LLM` remains `google / gemini-3.5-flash-lite`.
   - Reopening or re-exporting published versions shows unchanged snapshots.
10. Sign in as a viewer and verify that configurations can be inspected, but no create, edit, save, publish, import, or activate controls are visible.
11. Merge and live deployment remain subsequent explicit owner actions outside this task.

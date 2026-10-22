# Home persistence investigation — 2026-10-22

## Observed runtime evidence

The coordinator queried the home laptop PostgreSQL through key-authenticated SSH,
using `default_transaction_read_only=on`; the transaction confirmed read-only and
was rolled back. Credentials remained in process memory and were not printed.
No production data, configuration, containers, accounts, or provider services were changed.

- Audit time: 2026-10-22 08:19:51 UTC.
- Database process started: 2026-10-21 09:01:34 UTC.
- Migration head: `0007_phone_route_lifecycle`.
- Users: 1; the owner's previously created account exists (existence-only query).
- Agents: 1; published versions: 2; active bindings: 1.
- Voice sessions: 6 (4 ended, 2 error).
- Session events: 160, including 16 transcript events; diagnostics: 2.
- Session creation range: 2026-10-21 19:29:47 through 20:52:02 UTC.
- Both published configurations specify retention of 30 days.

This proves those records exist now. It does not establish that every historical
record the owner expects has survived, or reproduce the exact browser incident.
No restoration or account recreation was necessary for these observed records.

## Different installations

The home application is reached through the existing SSH forward at
`http://localhost:8080`. The earlier owner preview `http://localhost:55921` runs
an independent synthetic Compose project, `vf001check29249a36f1`, at VF013 head
`b95fc460e2d17d80749190e3108d20a4a2e69438`. Its fixture account and its own
temporary database are unrelated to the home account. It expires after one hour
and removes only its own disposable volume. Preview changes are not deployed.
Presenting this preview without prominent lifetime/data-ownership labeling caused
avoidable ambiguity; VF014 addresses it.

## Source findings and remaining uncertainty

- `main.py` sets the fixed host-only cookie `vf_session` at path `/`. Preview and
  home use the same hostname with different ports. Login/logout can therefore
  replace/clear the other installation's browser cookie. This is a concrete
  isolation defect; whether it caused this reported incident is unconfirmed.
- Board hides ended/error calls after five minutes. History holds them until
  configured retention. Logs holds failure diagnostics, not every successful
  session or transcript. History/Logs do not refresh while left open.
- Retention can delete terminal sessions and dependent events/diagnostics after
  their pinned deadline. Here it is 30 days, not zero. Retention does not delete users.
- No normal account deletion or factory-reset endpoint was found.
- Existing startup regression verifies account login after service restart but
  does not prove complete session/transcript persistence through recreation.

Until cookie isolation is implemented, use a separate browser profile/private
browser context for disposable previews. Sign back into the home installation
with the existing account; do not create a replacement account or wipe a volume.

## Product direction

The existing core implements accounts, draft/published configurations, activation,
browser sessions and history. It is a useful foundation, not a completed client
customization product: base reset, a portable client package, the business tool
SDK, scenario evaluation and full self-hosting acceptance remain incomplete.

Proceed with VF014/VF015 for installation identity and durable history, then
VF016 for a versioned base preset and explicit draft reset, followed by VF017 for
a bounded secret-free client configuration package. Reset never means database
reset. Missing configuration files never trigger automatic reset or activation.

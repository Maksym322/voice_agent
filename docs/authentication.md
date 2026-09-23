# VF-001 authentication contract

One independent installation has local accounts with admin, operator, and viewer
roles. There is no registration endpoint or default administrator. The operator
creates accounts using `python -m voice_fleet_api.admin create-user --role ROLE`
inside the API container. Passwords must have at least 12 characters and are
hashed with pwdlib's Argon2 recommendation. Only the hash is stored.
The CLI validates and normalizes email addresses with the same policy as login,
so it cannot create an account that the login route rejects.
For unattended provisioning in a trusted local/container environment, the CLI
also accepts `--email ADDRESS --password-stdin`; it reads one password line
from standard input and does not accept a password argument.

| Endpoint | Access | Result |
| --- | --- | --- |
| `GET /health/live` | Public | Process liveness, 200 |
| `GET /health/ready` | Public | 200 only when database and current migration are available; otherwise 503 |
| `POST /api/auth/login` | Public, same-origin JSON | Valid credentials create a session; invalid credentials return 401 |
| `POST /api/auth/logout` | Signed in, same origin and CSRF header | Revokes the session, clears the cookie, returns 204 |
| `GET /api/auth/me` | Signed in | Identity, role, and session CSRF token |
| `GET /api/admin/health` | Admin | 200 for admin, 403 for other signed-in roles |

Missing, invalid, expired, and revoked sessions return 401. The browser cannot
choose its role via a header or request body. Sessions are random opaque tokens;
only their SHA-256 digests are stored. The cookie is HttpOnly, SameSite=Lax, and
Secure in production. Default lifetime is 480 minutes; expired sessions cannot
access protected endpoints. Logout revokes the database record so replaying the
old cookie fails. The API requires the exact configured `Origin` for login and
cookie-authenticated mutations. Logout also requires the `X-CSRF-Token` returned
by login or `/api/auth/me`.

`ENVIRONMENT=production` requires an HTTPS `APP_ORIGIN` and
`SESSION_SECURE_COOKIE=true`. Terminate TLS at a trusted reverse proxy and
serve the dashboard and API under that one origin. Local mode accepts only a
localhost HTTP origin. The development Compose port binding is localhost only.
Account recovery and external identity providers are outside VF-001.

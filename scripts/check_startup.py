"""Build and verify a clean disposable VF-001 installation."""

import sys
import traceback

from isolated_stack import IsolatedStack


def main() -> int:
    try:
        with IsolatedStack() as stack:
            assert stack.request("/api/auth/me")[0] == 401
            assert stack.request("/api/admin/health")[0] == 401
            stack.bootstrap()
            status, headers, body = stack.request(
                "/api/auth/login",
                method="POST",
                payload={"email": stack.email, "password": stack.password},
            )
            if status != 200 or not isinstance(body, dict):
                raise RuntimeError(f"Login returned HTTP {status}: {body}")
            cookie = headers["set-cookie"].split(";", 1)[0]
            assert stack.request("/api/auth/me", cookie=cookie)[0] == 200
            assert stack.request("/api/admin/health", cookie=cookie)[0] == 200
            assert (
                stack.request(
                    "/api/auth/logout", method="POST", cookie=cookie, csrf=body["csrf_token"]
                )[0]
                == 204
            )
            assert stack.request("/api/auth/me", cookie=cookie)[0] == 401
            assert "voice processing is not implemented" in stack.compose("logs", "worker")
            stack.compose("stop", "api", "web", "worker")
            stack.compose("up", "-d", "api", "web", "worker")
            stack.wait_ready()
            assert (
                stack.request(
                    "/api/auth/login",
                    method="POST",
                    payload={"email": stack.email, "password": stack.password},
                )[0]
                == 200
            )
            stack.compose("stop", "db")
            assert stack.request("/health/ready")[0] == 503
            try:
                stack.compose("exec", "-T", "api", "alembic", "upgrade", "head")
            except RuntimeError:
                pass
            else:
                raise RuntimeError("Migration unexpectedly succeeded without PostgreSQL")
            stack.compose("start", "db")
            stack.wait_ready()
            print("Clean startup, auth, worker scaffold, and restart persistence passed.")
            return 0
    except Exception as exc:
        print(f"Startup check failed: {exc}", file=sys.stderr)
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

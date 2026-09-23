"""Run browser acceptance against a disposable Compose installation."""

import os
import subprocess
import sys

from isolated_stack import ROOT, IsolatedStack


def main() -> int:
    try:
        with IsolatedStack() as stack:
            stack.bootstrap()
            environment = os.environ.copy()
            environment["VF_E2E_URL"] = stack.origin
            environment["VF_E2E_EMAIL"] = stack.email
            environment["VF_E2E_PASSWORD"] = stack.password
            npm = "npm.cmd" if os.name == "nt" else "npm"
            result = subprocess.run(
                [npm, "exec", "--", "playwright", "test"],
                cwd=ROOT,
                env=environment,
                timeout=300,
                check=False,
            )
            return result.returncode
    except Exception as exc:
        print(f"Browser check failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

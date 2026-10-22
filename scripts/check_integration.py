"""Run PostgreSQL integration tests against an isolated Compose database."""

import os
import subprocess
import sys

from isolated_stack import ROOT, IsolatedStack


def main() -> int:
    try:
        with IsolatedStack() as stack:
            stack.compose("exec", "-T", "db", "createdb", "-U", "voice_fleet", "voice_fleet_test")
            environment = os.environ.copy()
            environment["TEST_DATABASE_URL"] = (
                f"postgresql+psycopg://voice_fleet:{stack.password}"
                f"@127.0.0.1:{stack.db_port}/voice_fleet_test"
            )
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "tests/integration", "-q"],
                cwd=ROOT,
                env=environment,
                timeout=300,
                check=False,
            )
            return result.returncode
    except Exception as exc:
        print(f"Integration check failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

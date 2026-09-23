"""Disposable Compose stack used only by foundation checks."""

import json
import os
import secrets
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Self

ROOT = Path(__file__).resolve().parents[1]


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class IsolatedStack:
    def __init__(self) -> None:
        self.docker = shutil.which("docker.exe" if os.name == "nt" else "docker")
        if not self.docker:
            raise RuntimeError("Docker CLI is unavailable")
        self.project = f"vf001check{secrets.token_hex(5)}"
        self.web_port = free_port()
        self.db_port = free_port()
        self.origin = f"http://localhost:{self.web_port}"
        self.email = "vf001-admin@example.com"
        self.password = secrets.token_urlsafe(24)
        artifact_dir = ROOT / "artifacts"
        artifact_dir.mkdir(exist_ok=True)
        self._temp = tempfile.TemporaryDirectory(prefix="vf001-check-", dir=artifact_dir)
        self.env_file = Path(self._temp.name) / ".env"
        self.env_file.write_text(
            "\n".join(
                (
                    f"POSTGRES_PASSWORD={self.password}",
                    f"DATABASE_URL=postgresql+psycopg://voice_fleet:{self.password}@db:5432/voice_fleet",
                    f"APP_ORIGIN={self.origin}",
                    "ENVIRONMENT=local",
                    "SESSION_SECURE_COOKIE=false",
                    f"WEB_PORT={self.web_port}",
                    f"DB_PORT={self.db_port}",
                )
            ),
            encoding="utf-8",
        )

    def compose(self, *args: str, input_text: str | None = None) -> str:
        environment = os.environ.copy()
        for key in (
            "POSTGRES_PASSWORD",
            "DATABASE_URL",
            "APP_ORIGIN",
            "ENVIRONMENT",
            "SESSION_SECURE_COOKIE",
            "WEB_PORT",
            "DB_PORT",
        ):
            environment.pop(key, None)
        command = [
            self.docker or "docker",
            "compose",
            "-f",
            str(ROOT / "compose.yaml"),
            "--env-file",
            str(self.env_file),
            "-p",
            self.project,
            *args,
        ]
        result = subprocess.run(
            command,
            cwd=ROOT,
            input=input_text,
            text=True,
            capture_output=True,
            env=environment,
            timeout=600,
            check=False,
        )
        if result.returncode:
            raise RuntimeError(
                f"Compose {' '.join(args)} failed ({result.returncode}): "
                f"{result.stdout[-2000:]} {result.stderr[-2000:]}"
            )
        return result.stdout

    def request(
        self,
        path: str,
        *,
        method: str = "GET",
        payload: dict[str, str] | None = None,
        cookie: str | None = None,
        csrf: str | None = None,
    ) -> tuple[int, dict[str, str], object]:
        headers = {"Origin": self.origin}
        data = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(payload).encode()
        if cookie:
            headers["Cookie"] = cookie
        if csrf:
            headers["X-CSRF-Token"] = csrf
        request = urllib.request.Request(
            self.origin + path, data=data, method=method, headers=headers
        )
        try:
            response = urllib.request.urlopen(request, timeout=5)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            raw = response.read()
            body = json.loads(raw) if raw else None
            return (
                response.status,
                {key.lower(): value for key, value in response.headers.items()},
                body,
            )

    def wait_ready(self) -> None:
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            try:
                if self.request("/health/ready")[0] == 200:
                    return
            except (OSError, ValueError):
                pass
            time.sleep(2)
        raise RuntimeError("Web/API did not become ready within 180 seconds")

    def bootstrap(self) -> None:
        response = self.compose(
            "exec",
            "-T",
            "api",
            "python",
            "-m",
            "voice_fleet_api.admin",
            "create-user",
            "--role",
            "admin",
            "--email",
            self.email,
            "--password-stdin",
            input_text=self.password + "\n",
        )
        if "Created admin account" not in response:
            raise RuntimeError("Synthetic administrator bootstrap did not complete")
        verify_code = (
            "import sys; from sqlalchemy import select; "
            "from voice_fleet_api.db import SessionLocal; "
            "from voice_fleet_api.models import User; "
            "from voice_fleet_api.security import verify_password; "
            "db=SessionLocal(); "
            "user=db.scalar(select(User).where(User.email=='vf001-admin@example.com')); "
            "print('BOOTSTRAP_VERIFY=' + str(user is not None and "
            "verify_password(sys.stdin.readline().rstrip('\\r\\n'), user.password_hash)))"
        )
        verified = self.compose(
            "exec", "-T", "api", "python", "-c", verify_code, input_text=self.password + "\n"
        )
        if "BOOTSTRAP_VERIFY=True" not in verified:
            raise RuntimeError(f"Synthetic account verification failed: {verified.strip()}")

    def __enter__(self) -> Self:
        try:
            self.compose("up", "-d", "--build")
            self.wait_ready()
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *_args: object) -> None:
        try:
            self.compose("down", "--volumes", "--remove-orphans")
        finally:
            self._temp.cleanup()

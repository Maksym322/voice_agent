"""Interactive account bootstrap for a single installation."""

import argparse
import getpass
import sys

from pydantic import ValidationError
from sqlalchemy import select

from voice_fleet_api.db import SessionLocal
from voice_fleet_api.models import User
from voice_fleet_api.security import hash_password, normalize_email, now_utc

ROLES = ("admin", "operator", "viewer")


def create_user(role: str, email_arg: str | None = None, password_stdin: bool = False) -> int:
    try:
        email = normalize_email(email_arg if email_arg is not None else input("Email: "))
    except ValidationError:
        print("A valid email is required.", file=sys.stderr)
        return 2
    if password_stdin:
        password = sys.stdin.readline().rstrip("\r\n")
    else:
        password = getpass.getpass("Password (12+ characters): ")
        repeat = getpass.getpass("Repeat password: ")
        if password != repeat:
            print("Passwords differ.", file=sys.stderr)
            return 2
    try:
        encoded = hash_password(password)
        with SessionLocal.begin() as db:
            if db.scalar(select(User.id).where(User.email == email)) is not None:
                print("Account already exists.", file=sys.stderr)
                return 2
            db.add(User(email=email, password_hash=encoded, role=role, created_at=now_utc()))
    except Exception as exc:
        print(f"Account creation failed: {type(exc).__name__}", file=sys.stderr)
        return 1
    print(f"Created {role} account for {email}.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create-user")
    create.add_argument("--role", choices=ROLES, required=True)
    create.add_argument("--email", help="For non-interactive provisioning")
    create.add_argument(
        "--password-stdin", action="store_true", help="Read one password line from stdin"
    )
    args = parser.parse_args()
    if args.password_stdin != (args.email is not None):
        parser.error("--email and --password-stdin must be used together")
    return create_user(args.role, args.email, args.password_stdin)


if __name__ == "__main__":
    raise SystemExit(main())

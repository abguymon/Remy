"""Management CLI: ``python -m remy_api <command>``.

Commands
--------
``create-user --username X [--password Y]``
    Bootstrap a user + default settings. Prompts for the password (twice) if
    ``--password`` is omitted. This is the first-user bootstrap — there is no
    registration endpoint and no invite codes (PRD §6).
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys

from remy_api.db import dispose_engine, get_session_factory, init_db
from remy_api.errors import APIError
from remy_api.user_service import create_user


def _prompt_password() -> str:
    first = getpass.getpass("Password: ")
    if not first:
        print("Password must not be empty.", file=sys.stderr)
        raise SystemExit(1)
    second = getpass.getpass("Confirm password: ")
    if first != second:
        print("Passwords do not match.", file=sys.stderr)
        raise SystemExit(1)
    return first


async def _create_user(username: str, password: str) -> None:
    await init_db()
    try:
        factory = get_session_factory()
        async with factory() as session:
            user = await create_user(session, username, password)
        print(f"Created user '{user.username}' (id={user.id}) with default settings.")
    finally:
        await dispose_engine()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="remy_api", description="Remy API management commands.")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create-user", help="Create a user and seed default settings.")
    create.add_argument("--username", required=True)
    create.add_argument("--password", help="Password (omit to be prompted securely).")

    args = parser.parse_args(argv)

    if args.command == "create-user":
        password = args.password or _prompt_password()
        try:
            asyncio.run(_create_user(args.username, password))
        except APIError as exc:
            print(f"Error: {exc.message}", file=sys.stderr)
            return 1
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

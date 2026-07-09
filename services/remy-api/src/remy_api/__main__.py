"""Management CLI: ``python -m remy_api <command>``.

Commands
--------
``create-user --username X [--password Y]``
    Bootstrap a user + default settings. Prompts for the password (twice) if
    ``--password`` is omitted. This is the first-user bootstrap — there is no
    registration endpoint and no invite codes (PRD §6).

``import-mealie --username X --url URL --api-key KEY [--dry-run]``
    One-shot import of a Mealie instance's recipes (+ images) into the store for
    user ``X`` (PRD §5). Idempotent by Mealie slug; safe to re-run.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys

import httpx
from sqlalchemy import select

from remy_api.db import dispose_engine, get_session_factory, init_db
from remy_api.errors import APIError
from remy_api.models import User
from remy_api.recipes.mealie_import import import_mealie
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


async def _resolve_user(session, username: str) -> User:  # noqa: ANN001
    row = await session.execute(select(User).where(User.username == username))
    user = row.scalar_one_or_none()
    if user is None:
        print(f"No such user '{username}'. Create it first with create-user.", file=sys.stderr)
        raise SystemExit(1)
    return user


async def _import_mealie(username: str, url: str, api_key: str, dry_run: bool) -> None:
    await init_db()
    try:
        factory = get_session_factory()
        async with factory() as session:
            user = await _resolve_user(session, username)
            stats = await import_mealie(session, user.id, url, api_key, dry_run=dry_run)
        prefix = "[dry-run] " if dry_run else ""
        print(f"{prefix}Mealie import for '{username}': {stats.summary()}")
    finally:
        await dispose_engine()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="remy_api", description="Remy API management commands.")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create-user", help="Create a user and seed default settings.")
    create.add_argument("--username", required=True)
    create.add_argument("--password", help="Password (omit to be prompted securely).")

    mealie = sub.add_parser("import-mealie", help="Import recipes from a Mealie instance.")
    mealie.add_argument("--username", required=True, help="Owning user for the imported recipes.")
    mealie.add_argument("--url", required=True, help="Mealie base URL, e.g. http://mealie:9000")
    mealie.add_argument("--api-key", required=True, help="Mealie API token.")
    mealie.add_argument("--dry-run", action="store_true", help="Report without writing or downloading.")

    args = parser.parse_args(argv)

    if args.command == "create-user":
        password = args.password or _prompt_password()
        try:
            asyncio.run(_create_user(args.username, password))
        except APIError as exc:
            print(f"Error: {exc.message}", file=sys.stderr)
            return 1
        return 0

    if args.command == "import-mealie":
        try:
            asyncio.run(_import_mealie(args.username, args.url, args.api_key, args.dry_run))
        except APIError as exc:
            print(f"Error: {exc.message}", file=sys.stderr)
            return 1
        except (httpx.HTTPError, OSError) as exc:
            print(
                f"Error: could not reach Mealie at {args.url}: {exc}. "
                "Check the URL is reachable from this host and the API key is valid.",
                file=sys.stderr,
            )
            return 1
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

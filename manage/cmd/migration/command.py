"""

Litecord
Copyright (C) 2018-2021  Luna Mendes and Litecord Contributors

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, version 3 of the License.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""

import inspect
import os
import datetime
import sys

from pathlib import Path
from dataclasses import dataclass
from collections import namedtuple
from typing import Dict

import asyncpg
from logbook import Logger

log = Logger(__name__)


Migration = namedtuple("Migration", "id name path")

# line of change, 4 april 2019, at 1am (gmt+0)
BREAK = datetime.datetime(2019, 4, 4, 1)

# if a database has those tables, it ran 0_base.sql.
HAS_BASE = ["users", "guilds", "e"]


@dataclass
class MigrationContext:
    """Hold information about migration."""

    migration_folder: Path
    scripts: Dict[int, Migration]

    @property
    def latest(self):
        """Return the latest migration ID."""
        return 0 if not self.scripts else max(self.scripts.keys())


def make_migration_ctx() -> MigrationContext:
    """Create the MigrationContext instance."""
    # taken from https://stackoverflow.com/a/6628348
    script_path = inspect.stack()[0][1]
    script_folder = os.sep.join(script_path.split(os.sep)[:-1])
    script_folder = Path(script_folder)

    migration_folder = script_folder / "scripts"

    mctx = MigrationContext(migration_folder, {})

    for mig_path in migration_folder.glob("*.sql"):
        mig_path_str = str(mig_path)

        # extract migration script id and name
        mig_filename = mig_path_str.split(os.sep)[-1].split(".")[0]
        name_fragments = mig_filename.split("_")

        mig_id = int(name_fragments[0])
        mig_name = "_".join(name_fragments[1:])

        mctx.scripts[mig_id] = Migration(mig_id, mig_name, mig_path)

    return mctx


async def _ensure_changelog(app, ctx):
    # make sure we have the migration table up
    try:
        await app.db.execute(
            """
        CREATE TABLE migration_log (
            change_num bigint NOT NULL,

            apply_ts timestamp without time zone default
                (now() at time zone 'utc'),

            description text,

            PRIMARY KEY (change_num)
        );
        """
        )
    except asyncpg.DuplicateTableError:
        log.debug("existing migration table")

        # NOTE: this is a migration breakage,
        # only applying to databases that had their first migration
        # before 4 april 2019 (more on BREAK)

        # if migration_log is empty, just assume this is new
        first = (
            await app.db.fetchval(
                """
        SELECT apply_ts FROM migration_log
        ORDER BY apply_ts ASC
        LIMIT 1
        """
            )
            or BREAK
        )
        if first < BREAK:
            log.info("deleting migration_log due to migration structure change")
            await app.db.execute("DROP TABLE migration_log")
            await _ensure_changelog(app, ctx)


async def _insert_log(app, migration_id: int, description) -> bool:
    try:
        await app.db.execute(
            """
        INSERT INTO migration_log (change_num, description)
        VALUES ($1, $2)
        """,
            migration_id,
            description,
        )

        return True
    except asyncpg.UniqueViolationError:
        log.warning("already inserted {}", migration_id)
        return False


async def _delete_log(app, migration_id: int):
    await app.db.execute(
        """
    DELETE FROM migration_log WHERE change_num = $1
    """,
        migration_id,
    )


async def run_migration(app, conn, migration):
    migration_sql = migration.path.read_text(encoding="utf-8")
    statements = migration_sql.split(";")

    # NOTE: is bodge, split by ; breaks function definitions. sorry.
    if migration.id == 0:
        statements = [migration_sql]

    for index, stmt in enumerate(statements):
        if not stmt.strip():
            break

        try:
            await app.db.execute(stmt)
        except Exception:
            log.exception("error at statement {}", index + 1)
            raise Exception()


async def apply_migration(app, migration: Migration) -> bool:
    """Apply a single migration.

    Tries to insert it to the migration logs first, and if it exists,
    skips it.

    If any error happens while migrating, this will rollback the log,
    by removing it from the logs.

    Returns a boolean signaling if this failed or not.
    """

    res = await _insert_log(app, migration.id, f"migration: {migration.name}")

    if not res:
        return False

    try:
        async with app.db.acquire() as conn:
            async with conn.transaction():
                await run_migration(app, conn, migration)

        log.info("applied {} {}", migration.id, migration.name)
        return True
    except Exception:
        log.exception("failed to run migration, rollbacking log")
        await _delete_log(app, migration.id)
        return False


async def _check_base(app) -> bool:
    """Return if the current database has ran the 0_base.sql
    file."""
    try:
        for table in HAS_BASE:
            await app.db.execute(
                f"""
            SELECT * FROM {table} LIMIT 0
            """
            )
    except asyncpg.UndefinedTableError:
        return False

    return True


async def migrate_cmd(app, _args):
    """Main migration command.

    This makes sure the database is updated, here's the steps:
     - create the migration_log table, or recreate it (due to migration
        changes in 4 april 2019)
     - check the latest local point in migration_log
     - check if the database is on the base schema
    """
    ctx = make_migration_ctx()

    # ensure there is a migration_log table
    await _ensure_changelog(app, ctx)

    # check HAS_BASE tables, and if they exist, implicitly
    # assume this has the base schema.
    has_base = await _check_base(app)

    # fetch latest local migration that has been run on this database
    local_change = await app.db.fetchval(
        """
    SELECT max(change_num)
    FROM migration_log
    """
    )

    # if base exists, add it to logs, if not, apply (and add to logs)
    if has_base:
        await _insert_log(app, 0, "migration setup (from existing)")
    else:
        await apply_migration(app, ctx.scripts[0])

    # after that check the current local_change
    # and the latest migration to be run

    # if no migrations, then we are on migration 0 (which is base)
    local_change = local_change or 0
    latest_change = ctx.latest

    log.debug("local: {}, latest: {}", local_change, latest_change)

    if local_change == latest_change:
        print("no changes to do, exiting")
        return

    # we do local_change + 1 so we start from the
    # next migration to do, end in latest_change + 1
    # because of how range() works.
    for idx in range(local_change + 1, latest_change + 1):
        migration = ctx.scripts.get(idx)

        print("applying", migration.id, migration.name)
        if not await apply_migration(app, migration):
            print("stopped migration due to error.")
            sys.exit(1)


def setup(subparser):
    migrate_parser = subparser.add_parser(
        "migrate", help="Run migration tasks", description=migrate_cmd.__doc__
    )

    migrate_parser.set_defaults(func=migrate_cmd)

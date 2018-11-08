import inspect
from pathlib import Path
from dataclasses import dataclass
from collections import namedtuple
from typing import Dict

import asyncpg
from logbook import Logger

log = Logger(__name__)


Migration = namedtuple('Migration', 'id name path')


@dataclass
class MigrationContext:
    """Hold information about migration."""
    migration_folder: Path
    scripts: Dict[int, Migration]

    @property
    def latest(self):
        """Return the latest migration ID."""
        return max(self.scripts.keys())


def make_migration_ctx() -> MigrationContext:
    """Create the MigrationContext instance."""
    # taken from https://stackoverflow.com/a/6628348
    script_path = inspect.stack()[0][1]
    script_folder = '/'.join(script_path.split('/')[:-1])
    script_folder = Path(script_folder)

    migration_folder = script_folder / 'scripts'

    mctx = MigrationContext(migration_folder, {})

    for mig_path in migration_folder.glob('*.sql'):
        mig_path_str = str(mig_path)

        # extract migration script id and name
        mig_filename = mig_path_str.split('/')[-1].split('.')[0]
        name_fragments = mig_filename.split('_')

        mig_id = int(name_fragments[0])
        mig_name = '_'.join(name_fragments[1:])

        mctx.scripts[mig_id] = Migration(
            mig_id, mig_name, mig_path)

    return mctx


async def _ensure_changelog(app, ctx):
    # make sure we have the migration table up

    try:
        await app.db.execute("""
        CREATE TABLE migration_log (
            change_num bigint NOT NULL,

            apply_ts timestamp without time zone default
                (now() at time zone 'utc'),

            description text,

            PRIMARY KEY (change_num)
        );
        """)

        # if we were able to create the
        # migration_log table, insert that we are
        # on the latest version.
        await app.db.execute("""
        INSERT INTO migration_log (change_num, description)
        VALUES ($1, $2)
        """, ctx.latest, 'migration setup')
    except asyncpg.DuplicateTableError:
        log.debug('existing migration table')


async def apply_migration(app, migration: Migration):
    """Apply a single migration."""
    migration_sql = migration.path.read_text(encoding='utf-8')

    try:
        await app.db.execute("""
        INSERT INTO migration_log (change_num, description)
        VALUES ($1, $2)
        """, migration.id, f'migration: {migration.name}')
    except asyncpg.UniqueViolationError:
        log.warning('already applied {}', migration.id)
        return

    await app.db.execute(migration_sql)
    log.info('applied {}', migration.id)


async def migrate_cmd(app, _args):
    """Main migration command.

    This makes sure the database
    is updated.
    """

    ctx = make_migration_ctx()

    await _ensure_changelog(app, ctx)

    # local point in the changelog
    local_change = await app.db.fetchval("""
    SELECT max(change_num)
    FROM migration_log
    """)

    local_change = local_change or 0
    latest_change = ctx.latest

    log.debug('local: {}, latest: {}', local_change, latest_change)

    if local_change == latest_change:
        print('no changes to do, exiting')
        return

    # we do local_change + 1 so we start from the
    # next migration to do, end in latest_change + 1
    # because of how range() works.
    for idx in range(local_change + 1, latest_change + 1):
        migration = ctx.scripts.get(idx)

        print('applying', migration.id, migration.name)
        await apply_migration(app, migration)


def setup(subparser):
    migrate_parser = subparser.add_parser(
        'migrate',
        help='Run migration tasks',
        description=migrate_cmd.__doc__
    )

    migrate_parser.set_defaults(func=migrate_cmd)

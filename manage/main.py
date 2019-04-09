"""

Litecord
Copyright (C) 2018-2019  Luna Mendes

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

import asyncio
import argparse
from sys import argv
from dataclasses import dataclass

from logbook import Logger

from run import init_app_managers, init_app_db
from manage.cmd.migration import migration
from manage.cmd import users, tests, invites

log = Logger(__name__)


@dataclass
class FakeApp:
    """Fake app instance."""
    config: dict
    db = None
    loop: asyncio.BaseEventLoop = None
    ratelimiter = None
    state_manager = None
    storage = None
    dispatcher = None
    presence = None


def init_parser():
    parser = argparse.ArgumentParser()
    subparser = parser.add_subparsers(help='operations')

    migration(subparser)
    users.setup(subparser)
    tests.setup(subparser)
    invites.setup(subparser)

    return parser


def main(config):
    """Start the script"""
    loop = asyncio.get_event_loop()
    cfg = getattr(config, config.MODE)
    app = FakeApp(cfg.__dict__)

    # initialize argparser
    parser = init_parser()

    loop.run_until_complete(init_app_db(app))

    try:
        if len(argv) < 2:
            parser.print_help()
            return

        # only init app managers when we aren't migrating
        # as the managers require it
        # and the migrate command also sets the db up
        if argv[1] != 'migrate':
            init_app_managers(app)

        args = parser.parse_args()
        loop.run_until_complete(args.func(app, args))
    except Exception:
        log.exception('error while running command')
    finally:
        loop.run_until_complete(app.db.close())

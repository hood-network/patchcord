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

import asyncio
import argparse
import inspect
from sys import argv
from dataclasses import dataclass

from quart import Quart
from logbook import Logger

from run import init_app_managers, init_app_db
from manage.cmd.migration import migration
from manage.cmd import users, invites

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
    user_storage = None
    icons = None
    dispatcher = None
    presence = None
    voice = None
    guild_store = None

    def make_app(self) -> Quart:
        app = Quart(__name__)
        app.config.from_object(self.config)
        fields = [
            field
            for (field, _val) in inspect.getmembers(self)
            if not field.startswith("__")
        ]

        for field in fields:
            setattr(app, field, getattr(self, field))

        return app


def init_parser():
    parser = argparse.ArgumentParser()
    subparser = parser.add_subparsers(help="operations")

    migration(subparser)
    users.setup(subparser)
    invites.setup(subparser)

    return parser


def main(config):
    """Start the script"""
    loop = asyncio.get_event_loop()

    # by doing this we can "import" quart's default config keys,
    # like SERVER_NAME, required for app_context to work.
    quart_app = Quart(__name__)
    quart_app.config.from_object(f"config.{config.MODE}")

    app = FakeApp(quart_app.config)
    parser = init_parser()

    loop.run_until_complete(init_app_db(app))

    async def _ctx_wrapper(fake_app, args):
        app = fake_app.make_app()
        async with app.app_context():
            return await args.func(fake_app, args)

    try:
        if len(argv) < 2:
            parser.print_help()
            return

        # only init app managers when we aren't migrating
        # as the managers require it
        # and the migrate command also sets the db up
        if argv[1] != "migrate":
            init_app_managers(app, init_voice=False)

        args = parser.parse_args()
        return loop.run_until_complete(_ctx_wrapper(app, args))
    except Exception:
        log.exception("error while running command")
        return 1
    finally:
        loop.run_until_complete(app.db.close())

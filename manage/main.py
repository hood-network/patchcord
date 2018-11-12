import asyncio
import argparse
from sys import argv
from dataclasses import dataclass

from logbook import Logger

from run import init_app_managers, init_app_db
from manage.cmd.migration import migration
from manage.cmd import users, tests

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

    return parser


def main(config):
    """Start the script"""
    loop = asyncio.get_event_loop()
    cfg = getattr(config, config.MODE)
    app = FakeApp(cfg.__dict__)

    loop.run_until_complete(init_app_db(app))
    init_app_managers(app)

    # initialize argparser
    parser = init_parser()

    try:
        if len(argv) < 2:
            parser.print_help()
            return

        args = parser.parse_args()
        loop.run_until_complete(args.func(app, args))
    except Exception:
        log.exception('error while running command')
    finally:
        loop.run_until_complete(app.db.close())

import asyncio
from dataclasses import dataclass


from run import init_app_managers, init_app_db


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


def main(config):
    """Start the script"""
    loop = asyncio.get_event_loop()
    cfg = getattr(config, config.MODE)
    app = FakeApp(cfg.__dict__)

    loop.run_until_complete(init_app_db(app))
    init_app_managers(app)

    print(app)

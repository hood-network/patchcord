import asyncio
import sys
import os

import pytest

# this is very hacky.
sys.path.append(os.getcwd())

from run import app as main_app, set_blueprints


@pytest.fixture(name='app')
def _test_app(unused_tcp_port, event_loop):
    set_blueprints(main_app)
    main_app.config['_testing'] = True

    # reassign an unused tcp port for websockets
    # since the config might give a used one.
    main_app.config['WS_PORT'] = unused_tcp_port
    main_app.config['WEBSOCKET_URL'] = f'localhost:{unused_tcp_port}'

    # make sure we're calling the before_serving hooks
    event_loop.run_until_complete(main_app.startup())

    return main_app


@pytest.fixture(name='test_cli')
def _test_cli(app):
    """Give a test client."""
    return app.test_client()

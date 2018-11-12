import asyncio
import sys
import os

import pytest

# this is very hacky.
sys.path.append(os.getcwd())

from run import app as main_app, set_blueprints


@pytest.fixture(name='app')
def _test_app(unused_tcp_port):
    set_blueprints(main_app)

    loop = asyncio.get_event_loop()

    # reassign an unused tcp port for websockets
    # since the config might give a used one.
    main_app.config['WS_PORT'] = unused_tcp_port

    # make sure we're calling the before_serving hooks
    loop.run_until_complete(main_app.startup())

    return main_app


@pytest.fixture(name='test_cli')
def _test_cli(app):
    """Give a test client."""
    return app.test_client()


@pytest.mark.asyncio
async def test_index(test_cli):
    """Test if the main index page works."""
    resp = await test_cli.get('/')
    assert resp.status_code == 200
    assert (await resp.get_data()).decode() == 'hewwo'


@pytest.mark.asyncio
async def test_gw(test_cli):
    """Test if the gateway route is sane."""
    resp = await test_cli.get('/api/v6/gateway')
    assert resp.status_code == 200
    rjson = await resp.json
    assert isinstance(rjson, dict)
    assert 'url' in rjson
    assert isinstance(rjson['url'], str)

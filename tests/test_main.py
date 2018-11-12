import asyncio
import sys
import os

import pytest

sys.path.append(os.getcwd())

from run import make_app, init_app_db, init_app_managers, set_blueprints


@pytest.fixture(name='app')
def _test_app():
    app = make_app()
    set_blueprints(app)
    loop = asyncio.get_event_loop()
    loop.run_until_complete(init_app_db(app))
    init_app_managers(app)
    return app


@pytest.fixture(name='test_cli')
def _test_cli(app):
    return app.test_client()


@pytest.mark.asyncio
async def test_index(test_cli):
    resp = await test_cli.get('/')
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_gw(test_cli):
    resp = await test_cli.get('/api/v6/gateway/')
    assert resp.status_code == 200
    rjson = await resp.json()
    assert isinstance(rjson, dict)
    assert 'gateway' in rjson
    assert isinstance(rjson['gateway'], str)

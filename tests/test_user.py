import pytest

from tests.common import login, get_uid


@pytest.mark.asyncio
async def test_get_me(test_cli):
    token = await login('normal', test_cli)
    resp = await test_cli.get('/api/v6/users/@me', headers={
        'Authorization': token
    })

    assert resp.status_code == 200
    rjson = await resp.json
    assert isinstance(rjson, dict)


@pytest.mark.asyncio
async def test_get_me_guilds(test_cli):
    token = await login('normal', test_cli)
    resp = await test_cli.get('/api/v6/users/@me/guilds', headers={
        'Authorization': token
    })

    assert resp.status_code == 200
    rjson = await resp.json
    assert isinstance(rjson, list)


@pytest.mark.asyncio
async def test_get_profile_self(test_cli):
    token = await login('normal', test_cli)
    user_id = await get_uid(token, test_cli)

    resp = await test_cli.get(f'/api/v6/users/{user_id}/profile', headers={
        'Authorization': token
    })

    assert resp.status_code == 200
    rjson = await resp.json
    assert isinstance(rjson, dict)
    assert isinstance(rjson['user'], dict)
    assert isinstance(rjson['connected_accounts'], list)
    assert (rjson['premium_since'] is None
            or isinstance(rjson['premium_since'], str))
    assert isinstance(rjson['mutual_guilds'], list)

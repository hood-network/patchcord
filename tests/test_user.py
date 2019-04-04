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

import pytest
import secrets

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

    # incomplete user assertions, but should be enough
    assert isinstance(rjson['id'], str)
    assert isinstance(rjson['username'], str)
    assert isinstance(rjson['discriminator'], str)
    assert rjson['avatar'] is None or isinstance(rjson['avatar'], str)
    assert isinstance(rjson['flags'], int)
    assert isinstance(rjson['bot'], bool)


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


@pytest.mark.asyncio
async def test_create_user(test_cli):
    """Test the creation and deletion of a user."""
    username = secrets.token_hex(4)
    _email = secrets.token_hex(5)
    email = f'{_email}@{_email}.com'
    password = secrets.token_hex(6)

    resp = await test_cli.post('/api/v6/auth/register', json={
        'username': username,
        'email': email,
        'password': password
    })

    assert resp.status_code == 200
    rjson = await resp.json

    assert isinstance(rjson, dict)
    token = rjson['token']
    assert isinstance(token, str)

    resp = await test_cli.get('/api/v6/users/@me', headers={
        'Authorization': token,
    })

    assert resp.status_code == 200
    rjson = await resp.json
    assert rjson['username'] == username
    assert rjson['email'] == email

    resp = await test_cli.post('/api/v6/users/@me/delete', headers={
        'Authorization': token,
    }, json={
        'password': password
    })

    assert resp.status_code == 204

    await test_cli.app.db.execute("""
    DELETE FROM users WHERE id = $1
    """, int(rjson['id']))

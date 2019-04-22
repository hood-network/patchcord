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

import secrets

import pytest

from tests.common import login
from tests.credentials import CREDS
from litecord.enums import UserFlags


async def _search(test_cli, *, username='', discrim='', token=None):
    token = token or await login('admin', test_cli)

    query_string = {
        'username': username,
        'discriminator': discrim
    }

    return await test_cli.get('/api/v6/admin/users', headers={
        'Authorization': token
    }, query_string=query_string)


@pytest.mark.asyncio
async def test_list_users(test_cli):
    """Try to list as many users as possible."""
    resp = await _search(test_cli, username=CREDS['admin']['username'])

    assert resp.status_code == 200
    rjson = await resp.json
    assert isinstance(rjson, list)
    assert rjson


async def _setup_user(test_cli, *, token=None) -> dict:
    token = token or await login('admin', test_cli)
    genned = secrets.token_hex(7)

    resp = await test_cli.post('/api/v6/admin/users', headers={
        'Authorization': token
    }, json={
        'username': genned,
        'email': f'{genned}@{genned}.com',
        'password': genned,
    })

    assert resp.status_code == 200
    rjson = await resp.json
    assert isinstance(rjson, dict)
    assert rjson['username'] == genned

    return rjson


async def _del_user(test_cli, user_id, *, token=None):
    """Delete a user."""
    token = token or await login('admin', test_cli)

    resp = await test_cli.delete(f'/api/v6/admin/users/{user_id}', headers={
        'Authorization': token
    })

    assert resp.status_code == 200
    rjson = await resp.json
    assert isinstance(rjson, dict)
    assert rjson['new']['id'] == user_id
    assert rjson['old']['id'] == rjson['new']['id']

    # TODO: remove from database at this point? it'll just keep being
    # filled up every time we run a test..


@pytest.mark.asyncio
async def test_create_delete(test_cli):
    """Create a user. Then delete them."""
    token = await login('admin', test_cli)

    rjson = await _setup_user(test_cli, token=token)

    genned = rjson['username']
    genned_uid = rjson['id']

    try:
        # check if side-effects went through with a search
        resp = await _search(test_cli, username=genned, token=token)

        assert resp.status_code == 200
        rjson = await resp.json
        assert isinstance(rjson, list)
        assert rjson[0]['id'] == genned_uid
    finally:
        await _del_user(test_cli, genned_uid, token=token)


@pytest.mark.asyncio
async def test_user_update(test_cli):
    """Test user update."""
    token = await login('admin', test_cli)
    rjson = await _setup_user(test_cli, token=token)

    user_id = rjson['id']

    # test update

    try:
        # set them as partner flag
        resp = await test_cli.patch(f'/api/v6/admin/users/{user_id}', headers={
            'Authorization': token
        }, json={
            'flags': UserFlags.partner,
        })

        assert resp.status_code == 200
        rjson = await resp.json
        assert rjson['id'] == user_id
        assert rjson['flags'] == UserFlags.partner

        # TODO: maybe we can check for side effects by fetching the
        # user manually too...
    finally:
        await _del_user(test_cli, user_id, token=token)

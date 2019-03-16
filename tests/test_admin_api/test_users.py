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

async def _search(test_cli, *, username='', discrim='', token=None):
    if token is None:
        token = await login('admin', test_cli)

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
    # NOTE: replace here if admin username changes
    resp = await _search(test_cli, username='big_girl')

    assert resp.status_code == 200
    rjson = await resp.json
    assert isinstance(rjson, list)
    assert rjson


@pytest.mark.asyncio
async def test_create_delete(test_cli):
    """Create a user. Then delete them."""
    token = await login('admin', test_cli)

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

    genned_uid = rjson['id']

    # check if side-effects went through with a search
    resp = await _search(test_cli, username=genned, token=token)

    assert resp.status_code == 200
    rjson = await resp.json
    assert isinstance(rjson, list)
    assert rjson[0]['id'] == genned_uid

    # delete
    resp = await test_cli.delete(f'/api/v6/admin/users/{genned_uid}', headers={
        'Authorization': token
    })

    assert resp.status_code == 200
    rjson = await resp.json
    assert isinstance(rjson, dict)
    assert rjson['new']['id'] == genned_uid
    assert rjson['old']['id'] == rjson['new']['id']

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

from tests.common import login

async def _get_invs(test_cli, token=None):
    if token is None:
        token = await login('admin', test_cli)

    resp = await test_cli.get('/api/v6/admin/instance/invites', headers={
        'Authorization': token
    })

    assert resp.status_code == 200
    rjson = await resp.json
    assert isinstance(rjson, list)
    return rjson


@pytest.mark.asyncio
async def test_get_invites(test_cli):
    """Test the listing of instance invites."""
    await _get_invs(test_cli)


@pytest.mark.asyncio
async def test_inv_delete_invalid(test_cli):
    """Test errors happen when trying to delete a
    non-existing instance invite."""
    token = await login('admin', test_cli)
    resp = await test_cli.delete(
        '/api/v6/admin/instance/invites/aaaaaaaaaa',
        headers={
            'Authorization': token
        }
    )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_invite(test_cli):
    """Test the creation of an instance invite, then listing it,
    then deleting it."""
    token = await login('admin', test_cli)
    resp = await test_cli.put('/api/v6/admin/instance/invites', headers={
        'Authorization': token
    }, json={
        'max_uses': 1
    })

    assert resp.status_code == 200
    rjson = await resp.json
    assert isinstance(rjson, dict)
    code = rjson['code']

    # assert that the invite is in the list
    invites = await _get_invs(test_cli, token)
    assert any(inv['code'] == code for inv in invites)

    # delete it, and assert it worked
    resp = await test_cli.delete(
        f'/api/v6/admin/instance/invites/{code}',
        headers={
            'Authorization': token
        }
    )

    assert resp.status_code == 204

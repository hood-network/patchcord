"""

Litecord
Copyright (C) 2018-2021  Luna Mendes and Litecord Contributors

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

from tests.common import email
from litecord.enums import UserFlags


async def _search(test_cli, *, username="", discrim=""):
    query_string = {"username": username, "discriminator": discrim}

    return await test_cli.get("/api/v6/admin/users", query_string=query_string)


@pytest.mark.asyncio
async def test_list_users(test_cli_staff):
    """Try to list as many users as possible."""
    resp = await _search(test_cli_staff, username=test_cli_staff.user["username"])

    assert resp.status_code == 200
    rjson = await resp.json
    assert isinstance(rjson, list)
    assert rjson


@pytest.mark.asyncio
async def test_find_single_user(test_cli_staff):
    user = await test_cli_staff.create_user(
        username="test_user" + secrets.token_hex(2), email=email()
    )
    resp = await _search(test_cli_staff, username=user.name)

    assert resp.status_code == 200
    rjson = await resp.json
    assert isinstance(rjson, list)
    fetched_user = rjson[0]
    assert fetched_user["id"] == str(user.id)


async def _setup_user(test_cli) -> dict:
    genned = secrets.token_hex(7)

    resp = await test_cli.post(
        "/api/v6/admin/users",
        json={
            "username": genned,
            "email": f"{genned}@{genned}.com",
            "password": genned,
        },
    )

    assert resp.status_code == 200
    rjson = await resp.json
    assert isinstance(rjson, dict)
    assert rjson["username"] == genned

    return rjson


async def _del_user(test_cli, user_id):
    """Delete a user."""
    resp = await test_cli.delete(f"/api/v6/admin/users/{user_id}")

    assert resp.status_code == 200
    rjson = await resp.json
    assert isinstance(rjson, dict)
    assert rjson["new"]["id"] == user_id
    assert rjson["old"]["id"] == rjson["new"]["id"]

    # delete the original record since the DELETE endpoint will just
    # replace the user by a "Deleted User <random hex>", and we don't want
    # to have obsolete users filling up our db every time we run tests
    await test_cli.app.db.execute(
        """
    DELETE FROM users WHERE id = $1
    """,
        int(user_id),
    )


@pytest.mark.asyncio
async def test_create_delete(test_cli_staff):
    """Create a user. Then delete them."""
    rjson = await _setup_user(test_cli_staff)

    genned = rjson["username"]
    genned_uid = rjson["id"]

    try:
        # check if side-effects went through with a search
        resp = await _search(test_cli_staff, username=genned)

        assert resp.status_code == 200
        rjson = await resp.json
        assert isinstance(rjson, list)
        assert rjson[0]["id"] == genned_uid
    finally:
        await _del_user(test_cli_staff, genned_uid)


@pytest.mark.asyncio
async def test_user_update(test_cli_staff):
    """Test user update."""
    user = await test_cli_staff.create_user()

    # set them as partner flag
    resp = await test_cli_staff.patch(
        f"/api/v6/admin/users/{user.id}", json={"flags": UserFlags.partner}
    )

    assert resp.status_code == 200
    rjson = await resp.json
    assert rjson["id"] == str(user.id)
    assert rjson["flags"] == UserFlags.partner

    refetched = await user.refetch()
    assert refetched.flags == UserFlags.partner

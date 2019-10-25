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

from litecord.blueprints.guilds import delete_guild
from litecord.errors import GuildNotFound


async def _create_guild(test_cli_staff):
    genned_name = secrets.token_hex(6)

    resp = await test_cli_staff.post(
        "/api/v6/guilds", json={"name": genned_name, "region": None}
    )

    assert resp.status_code == 200
    rjson = await resp.json
    assert isinstance(rjson, dict)
    assert rjson["name"] == genned_name

    return rjson


async def _fetch_guild(test_cli_staff, guild_id, *, ret_early=False):
    resp = await test_cli_staff.get(f"/api/v6/admin/guilds/{guild_id}")

    if ret_early:
        return resp

    assert resp.status_code == 200
    rjson = await resp.json
    assert isinstance(rjson, dict)
    assert rjson["id"] == guild_id

    return rjson


@pytest.mark.asyncio
async def test_guild_fetch(test_cli_staff):
    """Test the creation and fetching of a guild via the Admin API."""
    rjson = await _create_guild(test_cli_staff)
    guild_id = rjson["id"]

    try:
        await _fetch_guild(test_cli_staff, guild_id)
    finally:
        await delete_guild(int(guild_id), app_=test_cli_staff.app)


@pytest.mark.asyncio
async def test_guild_update(test_cli_staff):
    """Test the update of a guild via the Admin API."""
    rjson = await _create_guild(test_cli_staff)
    guild_id = rjson["id"]
    assert not rjson["unavailable"]

    try:
        # I believe setting up an entire gateway client registered to the guild
        # would be overkill to test the side-effects, so... I'm not
        # testing them. Yes, I know its a bad idea, but if someone has an easier
        # way to write that, do send an MR.
        resp = await test_cli_staff.patch(
            f"/api/v6/admin/guilds/{guild_id}", json={"unavailable": True}
        )

        assert resp.status_code == 200
        rjson = await resp.json
        assert isinstance(rjson, dict)
        assert rjson["id"] == guild_id
        assert rjson["unavailable"]

        rjson = await _fetch_guild(test_cli_staff, guild_id)
        assert rjson["unavailable"]
    finally:
        await delete_guild(int(guild_id), app_=test_cli_staff.app)


@pytest.mark.asyncio
async def test_guild_delete(test_cli_staff):
    """Test the update of a guild via the Admin API."""
    rjson = await _create_guild(test_cli_staff)
    guild_id = rjson["id"]

    try:
        resp = await test_cli_staff.delete(f"/api/v6/admin/guilds/{guild_id}")

        assert resp.status_code == 204

        resp = await _fetch_guild(test_cli_staff, guild_id, ret_early=True)

        assert resp.status_code == 404
        rjson = await resp.json
        assert isinstance(rjson, dict)
        assert rjson["error"]
        assert rjson["code"] == GuildNotFound.error_code
    finally:
        await delete_guild(int(guild_id), app_=test_cli_staff.app)

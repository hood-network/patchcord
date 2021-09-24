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

from litecord.errors import GuildNotFound


async def _fetch_guild(test_cli_staff, guild_id: str, *, return_early: bool = False):
    resp = await test_cli_staff.get(f"/api/v6/admin/guilds/{guild_id}")

    if return_early:
        return resp

    assert resp.status_code == 200
    rjson = await resp.json
    assert isinstance(rjson, dict)
    assert rjson["id"] == guild_id

    return rjson


@pytest.mark.asyncio
async def test_guild_fetch(test_cli_staff):
    """Test the creation and fetching of a guild via the Admin API."""
    guild = await test_cli_staff.create_guild()
    await _fetch_guild(test_cli_staff, str(guild.id))


@pytest.mark.asyncio
async def test_guild_update(test_cli_staff):
    """Test the update of a guild via the Admin API."""
    guild = await test_cli_staff.create_guild()
    guild_id = str(guild.id)

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
    assert rjson["id"] == guild_id
    assert rjson["unavailable"]


@pytest.mark.asyncio
async def test_guild_delete(test_cli_staff):
    """Test the update of a guild via the Admin API."""
    guild = await test_cli_staff.create_guild()
    guild_id = str(guild.id)

    resp = await test_cli_staff.delete(f"/api/v6/admin/guilds/{guild_id}")
    assert resp.status_code == 204

    resp = await _fetch_guild(test_cli_staff, guild_id, return_early=True)
    assert resp.status_code == 404

    rjson = await resp.json
    assert isinstance(rjson, dict)
    assert rjson["error"]
    assert rjson["code"] == GuildNotFound.error_code


@pytest.mark.asyncio
async def test_guild_create_voice(test_cli_staff):
    region_id = secrets.token_hex(6)
    region_name = secrets.token_hex(6)
    resp = await test_cli_staff.put(
        "/api/v6/admin/voice/regions", json={"id": region_id, "name": region_name}
    )
    assert resp.status_code == 200
    rjson = await resp.json
    assert isinstance(rjson, list)
    assert region_id in [r["id"] for r in rjson]

    # This test is basically creating the guild with a self-selected region
    # then deleting the guild afterwards on test resource cleanup
    try:
        await test_cli_staff.create_guild(region=region_id)
    finally:
        await test_cli_staff.app.db.execute(
            """
            DELETE FROM voice_regions
            WHERE id = $1
            """,
            region_id,
        )

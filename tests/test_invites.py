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

import pytest
from litecord.enums import MessageType

pytestmark = pytest.mark.asyncio


async def _create_invite(test_cli_user, guild, channel, max_uses=0):
    resp = await test_cli_user.post(
        f'/api/v9/channels/{channel["id"]}/invites', json={"max_uses": max_uses}
    )
    assert resp.status_code == 200
    rjson = await resp.json

    assert rjson["channel"]["id"] == channel["id"]
    assert rjson["guild"]["id"] == str(guild.id)
    return rjson


async def _join_invite(test_cli_user, invite, user):
    resp = await test_cli_user.post(f'/api/v9/invites/{invite["code"]}', as_user=user)
    assert resp.status_code == 200


async def test_invite_create(test_cli_user):
    """Test the creation of an invite."""
    guild = await test_cli_user.create_guild()
    channel = guild.channels[0]

    await _create_invite(test_cli_user, guild, channel)


async def test_invite_join(test_cli_user):
    """Test the ability to create & join an invite."""
    guild = await test_cli_user.create_guild()
    channel = guild.channels[0]

    invite = await _create_invite(test_cli_user, guild, channel)
    user = await test_cli_user.create_user()

    await _join_invite(test_cli_user, invite, user)


async def test_invite_system_message(test_cli_user):
    """Test creating & joining an invite, and
    the welcome message that appears when joining
    a guild."""
    guild = await test_cli_user.create_guild()
    channel = guild.channels[0]
    channel_id = channel["id"]

    # set the system message channel
    resp = await test_cli_user.patch(
        f"/api/v9/guilds/{guild.id}",
        json={
            "system_channel_id": channel_id,
        },
    )
    assert resp.status_code == 200
    rjson = await resp.json

    invite = await _create_invite(test_cli_user, guild, channel)
    user = await test_cli_user.create_user()

    await _join_invite(test_cli_user, invite, user)

    resp = await test_cli_user.get(f"/api/v9/channels/{channel_id}/messages")
    assert resp.status_code == 200
    rjson = await resp.json

    system_message = rjson[0]
    assert system_message["channel_id"] == channel_id
    assert system_message["guild_id"] == str(guild.id)
    assert system_message["type"] == MessageType.GUILD_MEMBER_JOIN.value
    assert system_message["content"] == ""
    assert system_message["author"]["id"] == str(user.id)


async def test_leave_join_invite_cycle(test_cli_user):
    """Assert repeatedly joining and leaving a guild works"""
    guild = await test_cli_user.create_guild()
    channel = guild.channels[0]
    invite = await _create_invite(test_cli_user, guild, channel)
    user = await test_cli_user.create_user()

    for x in range(1, 4):
        print(f"pass {x}")

        await _join_invite(test_cli_user, invite, user)
        resp = await test_cli_user.get("/api/v6/users/@me/guilds", as_user=user)
        assert resp.status_code == 200
        rjson = await resp.json

        assert any(incoming_guild["id"] == str(guild.id) for incoming_guild in rjson)

        resp = await test_cli_user.delete(
            f"/api/v6/users/@me/guilds/{guild.id}", as_user=user
        )
        assert resp.status_code == 204

        resp = await test_cli_user.get("/api/v6/users/@me/guilds", as_user=user)
        assert resp.status_code == 200
        rjson = await resp.json

        for incoming_guild in rjson:
            assert incoming_guild["id"] != str(guild.id)


async def test_invite_max_uses(test_cli_user):
    """Assert max_uses in invites is respected"""
    guild = await test_cli_user.create_guild()
    channel = guild.channels[0]
    invite = await _create_invite(test_cli_user, guild, channel, 1)
    user = await test_cli_user.create_user()

    # join and leave
    await _join_invite(test_cli_user, invite, user)

    resp = await test_cli_user.delete(
        f"/api/v6/users/@me/guilds/{guild.id}", as_user=user
    )
    assert resp.status_code == 204

    resp = await test_cli_user.post(f'/api/v9/invites/{invite["code"]}', as_user=user)
    assert resp.status_code == 403

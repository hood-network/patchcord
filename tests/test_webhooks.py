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

pytestmark = pytest.mark.asyncio


async def test_webhook_flow(test_cli_user):
    guild = await test_cli_user.create_guild()
    channel = await test_cli_user.create_guild_channel(guild_id=guild.id)

    resp = await test_cli_user.post(
        f"/api/v6/channels/{channel.id}/webhooks", json={"name": "awooga"}
    )
    assert resp.status_code == 200
    rjson = await resp.json
    assert rjson["channel_id"] == str(channel.id)
    assert rjson["guild_id"] == str(guild.id)
    assert rjson["name"] == "awooga"

    webhook_id = rjson["id"]
    webhook_token = rjson["token"]

    resp = await test_cli_user.post(
        f"/api/v6/webhooks/{webhook_id}/{webhook_token}",
        json={"content": "test_message"},
        headers={"authorization": ""},
    )
    assert resp.status_code == 204

    refetched_channel = await channel.refetch()
    message = await test_cli_user.app.storage.get_message(
        refetched_channel.last_message_id
    )
    assert message["author"]["id"] == webhook_id

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
import urllib.parse

pytestmark = pytest.mark.asyncio


async def test_reaction_flow(test_cli_user):
    guild = await test_cli_user.create_guild()
    channel = await test_cli_user.create_guild_channel(guild_id=guild.id)
    message = await test_cli_user.create_message(
        guild_id=guild.id, channel_id=channel.id
    )

    reaction = urllib.parse.quote("\N{THINKING FACE}")

    resp = await test_cli_user.put(
        f"/api/v6/channels/{channel.id}/messages/{message.id}/reactions/{reaction}/@me"
    )
    assert resp.status_code == 204

    resp = await test_cli_user.get(
        f"/api/v6/channels/{channel.id}/messages/{message.id}/reactions/{reaction}"
    )
    assert resp.status_code == 200
    rjson = await resp.json
    assert len(rjson) == 1

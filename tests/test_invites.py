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

pytestmark = pytest.mark.asyncio

# todo: maybe add more tests lol
# :)


async def test_invite_join(test_cli_user):
    guild = await test_cli_user.create_guild()
    channel = guild.channels[0]

    resp = await test_cli_user.patch(
        f"/api/v9/guilds/{guild.id}",
        json={
            "system_channel_id": channel["id"],
        },
    )

    assert resp.status_code == 200
    rjson = await resp.json
    assert rjson["system_channel_id"] == channel["id"]

    resp = await test_cli_user.post(
        f'/api/v9/channels/{channel["id"]}/invites', json={}
    )

    assert resp.status_code == 200
    rjson = await resp.json
    invite_code = rjson["code"]
    assert rjson["channel"]["id"] == channel["id"]
    assert rjson["guild"]["id"] == str(guild.id)

    user = await test_cli_user.create_user()

    resp = await test_cli_user.post(
        f"/api/v9/invites/{invite_code}", headers={"Authorization": user.token}
    )
    assert resp.status_code == 200

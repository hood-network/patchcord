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

from quart import current_app as app

from litecord.errors import Forbidden
from litecord.enums import RelationshipType


class ForbiddenDM(Forbidden):
    error_code = 50007


async def dm_pre_check(user_id: int, channel_id: int, peer_id: int):
    """Check if the user can DM the peer."""
    # first step is checking if there is a block in any direction
    blockrow = await app.db.fetchrow("""
    SELECT rel_type
    FROM relationships
    WHERE rel_type = $3
      AND user_id IN ($1, $2)
      AND peer_id IN ($1, $2)
    """, user_id, peer_id, RelationshipType.BLOCK.value)

    if blockrow is not None:
        raise ForbiddenDM()

    # check if theyre friends
    friends = await app.user_storage.are_friends_with(user_id, peer_id)

    # if they're mutual friends, we don't do mutual guild checking
    if friends:
        return

    # now comes the fun part, which is guild settings.
    mutual_guilds = await app.user_storage.get_mutual_guilds(user_id, peer_id)
    mutual_guilds = set(mutual_guilds)

    # user_settings.restricted_guilds gives us the dms a user doesn't
    # want dms from, so we use that setting from both user and peer

    user_settings = await app.user_storage.get_user_settings(user_id)
    peer_settings = await app.user_storage.get_user_settings(peer_id)

    restricted_user_ = [int(v) for v in user_settings['restricted_guilds']]
    restricted_peer_ = [int(v) for v in peer_settings['restricted_guilds']]

    restricted_user = set(restricted_user_)
    restricted_peer = set(restricted_peer_)

    mutual_guilds -= restricted_user
    mutual_guilds -= restricted_peer

    # if after this filtering we don't have any more guilds, error
    if not mutual_guilds:
        raise ForbiddenDM()

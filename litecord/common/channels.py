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
from typing import Optional, TYPE_CHECKING

from litecord.errors import Forbidden
from litecord.enums import RelationshipType
from litecord.pubsub.member import dispatch_member
from litecord.pubsub.user import dispatch_user

if TYPE_CHECKING:
    from litecord.typing_hax import app, request
else:
    from quart import current_app as app, request


async def channel_ack(
    user_id: int,
    channel_id: int,
    guild_id: Optional[int] = None,
    message_id: Optional[int] = None,
):
    """ACK a channel."""

    message_id = message_id or await app.storage.chan_last_message(channel_id)

    # never ack without a message, as that breaks read state.
    if message_id is None:
        return

    await app.db.execute(
        """
        INSERT INTO user_read_state
            (user_id, channel_id, last_message_id, mention_count)
        VALUES
            ($1, $2, $3, 0)
        ON CONFLICT ON CONSTRAINT user_read_state_pkey
        DO
        UPDATE
            SET last_message_id = $3, mention_count = 0
            WHERE user_read_state.user_id = $1
            AND user_read_state.channel_id = $2
        """,
        user_id,
        channel_id,
        message_id,
    )

    if guild_id:
        await dispatch_member(
            guild_id,
            user_id,
            (
                "MESSAGE_ACK",
                {"message_id": str(message_id), "channel_id": str(channel_id)},
            ),
        )
    else:
        # we don't use ChannelDispatcher here because since
        # guild_id is None, all user devices are already subscribed
        # to the given channel (a dm or a group dm)
        await dispatch_user(
            user_id,
            (
                "MESSAGE_ACK",
                {"message_id": str(message_id), "channel_id": str(channel_id)},
            ),
        )


async def dm_pre_check(user_id: int, channel_id: int, peer_id: int):
    """Check if the user can DM the peer."""
    # first step is checking if there is a block in any direction
    blockrow = await app.db.fetchrow(
        """
        SELECT rel_type
        FROM relationships
        WHERE rel_type = $3
        AND user_id IN ($1, $2)
        AND peer_id IN ($1, $2)
        """,
        user_id,
        peer_id,
        RelationshipType.BLOCK.value,
    )

    if blockrow is not None:
        raise Forbidden(50007)

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

    restricted_user_ = [int(v) for v in user_settings["restricted_guilds"]]
    restricted_peer_ = [int(v) for v in peer_settings["restricted_guilds"]]

    restricted_user = set(restricted_user_)
    restricted_peer = set(restricted_peer_)

    mutual_guilds -= restricted_user
    mutual_guilds -= restricted_peer

    # if after this filtering we don't have any more guilds, error
    if not mutual_guilds:
        raise Forbidden(50007)


async def try_dm_state(user_id: int, dm_id: int):
    """Try inserting the user into the dm state
    for the given DM.

    Does not do anything if the user is already
    in the dm state.
    """
    await app.db.execute(
        """
    INSERT INTO dm_channel_state (user_id, dm_id)
    VALUES ($1, $2)
    ON CONFLICT DO NOTHING
    """,
        user_id,
        dm_id,
    )

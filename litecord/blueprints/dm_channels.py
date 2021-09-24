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

from typing import Iterable

from quart import Blueprint, current_app as app, jsonify
from logbook import Logger

from litecord.blueprints.auth import token_check
from litecord.blueprints.checks import channel_check
from litecord.enums import ChannelType, MessageType
from litecord.errors import BadRequest, Forbidden

from litecord.system_messages import send_sys_message
from litecord.pubsub.channel import gdm_recipient_view
from litecord.pubsub.user import dispatch_user

log = Logger(__name__)
bp = Blueprint("dm_channels", __name__)


async def _raw_gdm_add(channel_id, user_id):
    await app.db.execute(
        """
    INSERT INTO group_dm_members (id, member_id)
    VALUES ($1, $2)
    """,
        channel_id,
        user_id,
    )


async def _raw_gdm_remove(channel_id, user_id):
    await app.db.execute(
        """
    DELETE FROM group_dm_members
    WHERE id = $1 AND member_id = $2
    """,
        channel_id,
        user_id,
    )


async def gdm_pubsub(channel_id: int, recipients: Iterable[int]):
    for recipient_id in recipients:
        await app.dispatcher.channel.sub_many(
            channel_id,
            [state.session_id for state in app.state_manager.user_states(recipient_id)],
        )


async def gdm_create(user_id, peer_id) -> int:
    """Create a group dm, given two users.

    Returns the new GDM id.
    """
    channel_id = app.winter_factory.snowflake()

    await app.db.execute(
        """
    INSERT INTO channels (id, channel_type)
    VALUES ($1, $2)
    """,
        channel_id,
        ChannelType.GROUP_DM.value,
    )

    await app.db.execute(
        """
    INSERT INTO group_dm_channels (id, owner_id, name, icon)
    VALUES ($1, $2, NULL, NULL)
    """,
        channel_id,
        user_id,
    )

    await _raw_gdm_add(channel_id, user_id)
    await _raw_gdm_add(channel_id, peer_id)

    await gdm_pubsub(channel_id, (user_id, peer_id))

    chan = await app.storage.get_channel(channel_id)
    await app.dispatcher.channel.dispatch(channel_id, ("CHANNEL_CREATE", chan))

    return channel_id


async def gdm_add_recipient(channel_id: int, peer_id: int, *, user_id=None):
    """Add a recipient to a Group DM.

    Dispatches:
     - A system message with the join (depending of user_id)
     - A CHANNEL_CREATE to the peer.
     - A CHANNEL_UPDATE to all remaining recipients.
    """
    await _raw_gdm_add(channel_id, peer_id)

    chan = await app.storage.get_channel(channel_id)

    # the reasoning behind gdm_recipient_view is in its docstring.
    await dispatch_user(peer_id, ("CHANNEL_CREATE", gdm_recipient_view(chan, peer_id)))

    await app.dispatcher.channel.dispatch(channel_id, ("CHANNEL_UPDATE", chan))
    await gdm_pubsub(channel_id, (peer_id,))

    if user_id:
        await send_sys_message(channel_id, MessageType.RECIPIENT_ADD, user_id, peer_id)


async def gdm_remove_recipient(channel_id: int, peer_id: int, *, user_id=None):
    """Remove a member from a GDM.

    Dispatches:
     - A system message with the leave or forced removal (depending if user_id)
        exists or not.
     - A CHANNEL_DELETE to the peer.
     - A CHANNEL_UPDATE to all remaining recipients.
    """
    await _raw_gdm_remove(channel_id, peer_id)

    chan = await app.storage.get_channel(channel_id)
    await dispatch_user(peer_id, ("CHANNEL_DELETE", gdm_recipient_view(chan, user_id)))

    await app.dispatcher.channel.unsub(peer_id)

    await app.dispatcher.channel.dispatch(
        channel_id,
        (
            "CHANNEL_RECIPIENT_REMOVE",
            {
                "channel_id": str(channel_id),
                "user": await app.storage.get_user(peer_id),
            },
        ),
    )

    author_id = peer_id if user_id is None else user_id

    await send_sys_message(channel_id, MessageType.RECIPIENT_REMOVE, author_id, peer_id)


async def gdm_destroy(channel_id):
    """Destroy a Group DM."""
    chan = await app.storage.get_channel(channel_id)

    await app.db.execute(
        """
    DELETE FROM group_dm_members
    WHERE id = $1
    """,
        channel_id,
    )

    await app.db.execute(
        """
    DELETE FROM group_dm_channels
    WHERE id = $1
    """,
        channel_id,
    )

    await app.db.execute(
        """
    DELETE FROM channels
    WHERE id = $1
    """,
        channel_id,
    )

    await app.dispatcher.channel.dispatch(channel_id, ("CHANNEL_DELETE", chan))
    await app.dispatcher.channel.drop(channel_id)


async def gdm_is_member(channel_id: int, user_id: int) -> bool:
    """Return if the given user is a member of the Group DM."""
    row = await app.db.fetchval(
        """
    SELECT id
    FROM group_dm_members
    WHERE id = $1 AND member_id = $2
    """,
        channel_id,
        user_id,
    )

    return row is not None


@bp.route("/<int:dm_chan>/recipients/<int:peer_id>", methods=["PUT"])
async def add_to_group_dm(dm_chan, peer_id):
    """Adds a member to a group dm OR creates a group dm."""
    user_id = await token_check()

    # other_id is the owner of the group dm (gdm) if the
    # given channel is a gdm

    # other_id is the peer of the dm if the given channel is a dm
    ctype, other_id = await channel_check(
        user_id, dm_chan, only=[ChannelType.DM, ChannelType.GROUP_DM]
    )

    # check relationship with the given user id
    # and the user id making the request
    friends = await app.user_storage.are_friends_with(user_id, peer_id)

    if not friends:
        raise BadRequest("Cant insert peer into dm")

    if ctype == ChannelType.DM:
        dm_chan = await gdm_create(user_id, other_id)

    await gdm_add_recipient(dm_chan, peer_id, user_id=user_id)

    return jsonify(await app.storage.get_channel(dm_chan))


@bp.route("/<int:dm_chan>/recipients/<int:peer_id>", methods=["DELETE"])
async def remove_from_group_dm(dm_chan, peer_id):
    """Remove users from group dm."""
    user_id = await token_check()
    _ctype, owner_id = await channel_check(user_id, dm_chan, only=ChannelType.GROUP_DM)

    if owner_id != user_id:
        raise Forbidden("You are now the owner of the group DM")

    await gdm_remove_recipient(dm_chan, peer_id)
    return "", 204

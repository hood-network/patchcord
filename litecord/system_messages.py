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

from logbook import Logger
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from litecord.typing_hax import app
else:
    from quart import current_app as app

from litecord.enums import MessageType

log = Logger(__name__)


async def _handle_pin_msg(channel_id, _pinned_id, author_id):
    """Handle a message pin."""
    new_id = app.winter_factory.snowflake()

    await app.db.execute(
        """
        INSERT INTO messages
            (id, channel_id, guild_id, author_id, content, message_type)
        VALUES
            ($1, $2, $3, $4, '', $5)
        """,
        new_id,
        channel_id,
        await app.storage.guild_from_channel(channel_id),
        author_id,
        MessageType.CHANNEL_PINNED_MESSAGE.value,
    )

    return new_id


async def _handle_guild_join_msg(channel_id, user_id):
    """Handle the system join message."""
    new_id = app.winter_factory.snowflake()

    await app.db.execute(
        """
        INSERT INTO messages
            (id, channel_id, guild_id, author_id, content, message_type)
        VALUES
            ($1, $2, $3, $4, '', $5)
        """,
        new_id,
        channel_id,
        await app.storage.guild_from_channel(channel_id),
        user_id,
        MessageType.GUILD_MEMBER_JOIN.value,
    )

    return new_id


# TODO: decrease repetition between add and remove handlers
async def _handle_recp_add(channel_id, author_id, peer_id):
    new_id = app.winter_factory.snowflake()

    await app.db.execute(
        """
        INSERT INTO messages
            (id, channel_id, author_id, content, message_type)
        VALUES
            ($1, $2, $3, $4, $5)
        """,
        new_id,
        channel_id,
        author_id,
        f"<@{peer_id}>",
        MessageType.RECIPIENT_ADD.value,
    )

    return new_id


async def _handle_recp_rmv(channel_id, author_id, peer_id):
    new_id = app.winter_factory.snowflake()

    await app.db.execute(
        """
        INSERT INTO messages
            (id, channel_id, author_id, content, message_type)
        VALUES
            ($1, $2, $3, $4, $5)
        """,
        new_id,
        channel_id,
        author_id,
        f"<@{peer_id}>",
        MessageType.RECIPIENT_REMOVE.value,
    )

    return new_id


async def _handle_gdm_name_edit(channel_id, author_id):
    new_id = app.winter_factory.snowflake()

    gdm_name = await app.db.fetchval(
        """
    SELECT name FROM group_dm_channels
    WHERE id = $1
    """,
        channel_id,
    )

    if not gdm_name:
        log.warning("no gdm name found for sys message")
        return

    await app.db.execute(
        """
        INSERT INTO messages
            (id, channel_id, author_id, content, message_type)
        VALUES
            ($1, $2, $3, $4, $5)
        """,
        new_id,
        channel_id,
        author_id,
        gdm_name,
        MessageType.CHANNEL_NAME_CHANGE.value,
    )

    return new_id


async def _handle_gdm_icon_edit(channel_id, author_id):
    new_id = app.winter_factory.snowflake()

    await app.db.execute(
        """
        INSERT INTO messages
            (id, channel_id, author_id, content, message_type)
        VALUES
            ($1, $2, $3, $4, $5)
        """,
        new_id,
        channel_id,
        author_id,
        "",
        MessageType.CHANNEL_ICON_CHANGE.value,
    )

    return new_id


async def send_sys_message(
    channel_id: int, m_type: MessageType, *args, **kwargs
) -> int:
    """Send a system message.

    The handler for a given message type MUST return an integer, that integer
    being the message ID generated. This function takes care of feching the
    message and dispatching the needed event.

    Parameters
    ----------
    channel_id
        The channel ID to send the system message to.
    m_type
        The system message's type.

    Returns
    -------
    int
        The message ID.
    """
    try:
        handler = {
            MessageType.CHANNEL_PINNED_MESSAGE: _handle_pin_msg,
            MessageType.GUILD_MEMBER_JOIN: _handle_guild_join_msg,
            # gdm specific
            MessageType.RECIPIENT_ADD: _handle_recp_add,
            MessageType.RECIPIENT_REMOVE: _handle_recp_rmv,
            MessageType.CHANNEL_NAME_CHANGE: _handle_gdm_name_edit,
            MessageType.CHANNEL_ICON_CHANGE: _handle_gdm_icon_edit,
        }[m_type]
    except KeyError:
        raise ValueError("Invalid system message type")

    message_id = await handler(channel_id, *args, **kwargs)
    message = await app.storage.get_message(message_id, include_member=True)
    await app.dispatcher.channel.dispatch(channel_id, ("MESSAGE_CREATE", message))
    return message_id

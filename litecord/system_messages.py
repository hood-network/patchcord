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

from logbook import Logger

from litecord.snowflake import get_snowflake
from litecord.enums import MessageType

log = Logger(__name__)

async def _handle_pin_msg(app, channel_id, _pinned_id, author_id):
    """Handle a message pin."""
    new_id = get_snowflake()

    await app.db.execute(
        """
        INSERT INTO messages
            (id, channel_id, guild_id, author_id,
             webhook_id, content, message_type)
        VALUES
            ($1, $2, NULL, $3, NULL, '',
             $4)
        """,
        new_id, channel_id, author_id,
        MessageType.CHANNEL_PINNED_MESSAGE.value
    )

    return new_id


# TODO: decrease repetition between add and remove handlers
async def _handle_recp_add(app, channel_id, author_id, peer_id):
    new_id = get_snowflake()

    await app.db.execute(
        """
        INSERT INTO messages
            (id, channel_id, author_id, webhook_id,
             content, message_type)
        VALUES
            ($1, $2, $3, NULL, $4, $5)
        """,
        new_id, channel_id, author_id,
        f'<@{peer_id}>',
        MessageType.RECIPIENT_ADD.value
    )

    return new_id



async def _handle_recp_rmv(app, channel_id, author_id, peer_id):
    new_id = get_snowflake()

    await app.db.execute(
        """
        INSERT INTO messages
            (id, channel_id, author_id, webhook_id,
             content, message_type)
        VALUES
            ($1, $2, $3, NULL, $4, $5)
        """,
        new_id, channel_id, author_id,
        f'<@{peer_id}>',
        MessageType.RECIPIENT_REMOVE.value
    )

    return new_id


async def _handle_gdm_name_edit(app, channel_id, author_id):
    new_id = get_snowflake()

    gdm_name = await app.db.fetchval("""
    SELECT name FROM group_dm_channels
    WHERE id = $1
    """, channel_id)

    if not gdm_name:
        log.warning('no gdm name found for sys message')
        return

    await app.db.execute(
        """
        INSERT INTO messages
            (id, channel_id, author_id, webhook_id,
             content, message_type)
        VALUES
            ($1, $2, $3, NULL, $4, $5)
        """,
        new_id, channel_id, author_id,
        gdm_name,
        MessageType.RECIPIENT_ADD.value
    )

    return new_id


async def _handle_gdm_icon_edit(app, channel_id, author_id):
    new_id = get_snowflake()

    await app.db.execute(
        """
        INSERT INTO messages
            (id, channel_id, author_id, webhook_id,
             content, message_type)
        VALUES
            ($1, $2, $3, NULL, $4, $5)
        """,
        new_id, channel_id, author_id,
        '',
        MessageType.CHANNEL_ICON_CHANGE.value
    )

    return new_id


async def send_sys_message(app, channel_id: int, m_type: MessageType,
                           *args, **kwargs) -> int:
    """Send a system message."""
    try:
        handler = {
            MessageType.CHANNEL_PINNED_MESSAGE: _handle_pin_msg,

            # gdm specific
            MessageType.RECIPIENT_ADD: _handle_recp_add,
            MessageType.RECIPIENT_REMOVE: _handle_recp_rmv,
            MessageType.CHANNEL_NAME_CHANGE: _handle_gdm_name_edit,
            MessageType.CHANNEL_ICON_CHANGE: _handle_gdm_icon_edit
        }[m_type]
    except KeyError:
        raise ValueError('Invalid system message type')

    message_id = await handler(app, channel_id, *args, **kwargs)

    message = await app.storage.get_message(message_id)

    await app.dispatcher.dispatch(
        'channel', channel_id, 'MESSAGE_CREATE', message
    )

    return message_id

"""

Litecord
Copyright (C) 2018  Luna Mendes

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

from litecord.snowflake import get_snowflake
from litecord.enums import MessageType


async def _handle_pin_msg(app, channel_id, pinned_id, author_id):
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


async def send_sys_message(app, channel_id: int, m_type: MessageType,
                           *args, **kwargs):
    """Send a system message."""
    handler = {
        MessageType.CHANNEL_PINNED_MESSAGE: _handle_pin_msg,
    }[m_type]

    message_id = await handler(app, channel_id, *args, **kwargs)

    message = await app.storage.get_message(message_id)

    await app.dispatcher.dispatch(
        'channel', channel_id, 'MESSAGE_CREATE', message
    )

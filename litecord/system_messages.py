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

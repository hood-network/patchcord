from quart import Blueprint, current_app as app, jsonify

from litecord.auth import token_check
from litecord.blueprints.checks import channel_check, channel_perm_check
from litecord.snowflake import snowflake_datetime
from litecord.types import timestamp_

bp = Blueprint('channel_pins', __name__)


@bp.route('/<int:channel_id>/pins', methods=['GET'])
async def get_pins(channel_id):
    """Get the pins for a channel"""
    user_id = await token_check()
    await channel_check(user_id, channel_id)

    ids = await app.db.fetch("""
    SELECT message_id
    FROM channel_pins
    WHERE channel_id = $1
    ORDER BY message_id DESC
    """, channel_id)

    ids = [r['message_id'] for r in ids]
    res = []

    for message_id in ids:
        message = await app.storage.get_message(message_id)
        if message is not None:
            res.append(message)

    return jsonify(res)


@bp.route('/<int:channel_id>/pins/<int:message_id>', methods=['PUT'])
async def add_pin(channel_id, message_id):
    """Add a pin to a channel"""
    user_id = await token_check()
    _ctype, guild_id = await channel_check(user_id, channel_id)

    await channel_perm_check(user_id, channel_id, 'manage_messages')

    await app.db.execute("""
    INSERT INTO channel_pins (channel_id, message_id)
    VALUES ($1, $2)
    """, channel_id, message_id)

    row = await app.db.fetchrow("""
    SELECT message_id
    FROM channel_pins
    WHERE channel_id = $1
    ORDER BY message_id ASC
    LIMIT 1
    """, channel_id)

    timestamp = snowflake_datetime(row['message_id'])

    await app.dispatcher.dispatch(
        'channel', channel_id, 'CHANNEL_PINS_UPDATE',
        {
            'channel_id': str(channel_id),
            'last_pin_timestamp': timestamp_(timestamp)
        }
    )

    return '', 204


@bp.route('/<int:channel_id>/pins/<int:message_id>', methods=['DELETE'])
async def delete_pin(channel_id, message_id):
    user_id = await token_check()
    _ctype, guild_id = await channel_check(user_id, channel_id)

    await channel_perm_check(user_id, channel_id, 'manage_messages')

    await app.db.execute("""
    DELETE FROM channel_pins
    WHERE channel_id = $1 AND message_id = $2
    """, channel_id, message_id)

    row = await app.db.fetchrow("""
    SELECT message_id
    FROM channel_pins
    WHERE channel_id = $1
    ORDER BY message_id ASC
    LIMIT 1
    """, channel_id)

    timestamp = snowflake_datetime(row['message_id'])

    await app.dispatcher.dispatch(
        'channel', channel_id, 'CHANNEL_PINS_UPDATE', {
            'channel_id': str(channel_id),
            'last_pin_timestamp': timestamp.isoformat()
        })

    return '', 204

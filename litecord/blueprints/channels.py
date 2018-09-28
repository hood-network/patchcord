import time

from quart import Blueprint, request, current_app as app, jsonify
from logbook import Logger

from ..auth import token_check
from ..snowflake import get_snowflake, snowflake_datetime
from ..enums import ChannelType, MessageType
from ..errors import Forbidden, BadRequest, ChannelNotFound, MessageNotFound
from ..schemas import validate, MESSAGE_CREATE

from .guilds import guild_check

log = Logger(__name__)
bp = Blueprint('channels', __name__)


async def channel_check(user_id, channel_id):
    """Check if the current user is authorized
    to read the channel's information."""
    ctype = await app.storage.get_chan_type(channel_id)

    if ctype is None:
        raise ChannelNotFound(f'channel type not found')

    if ChannelType(ctype) in (ChannelType.GUILD_TEXT, ChannelType.GUILD_VOICE,
                              ChannelType.GUILD_CATEGORY):
        guild_id = await app.db.fetchval("""
        SELECT guild_id
        FROM guild_channels
        WHERE guild_channels.id = $1
        """, channel_id)

        await guild_check(user_id, guild_id)
        return guild_id


@bp.route('/<int:channel_id>', methods=['GET'])
async def get_channel(channel_id):
    user_id = await token_check()
    await channel_check(user_id, channel_id)
    chan = await app.storage.get_channel(channel_id)

    if not chan:
        raise ChannelNotFound('single channel not found')

    return jsonify(chan)


@bp.route('/<int:channel_id>/messages', methods=['GET'])
async def get_messages(channel_id):
    user_id = await token_check()
    await channel_check(user_id, channel_id)

    # TODO: before, after, around keys

    message_ids = await app.db.fetch(f"""
    SELECT id
    FROM messages
    WHERE channel_id = $1
    ORDER BY id DESC
    LIMIT 100
    """, channel_id)

    result = []

    for message_id in message_ids:
        msg = await app.storage.get_message(message_id['id'])

        if msg is None:
            continue

        result.append(msg)

    log.info('Fetched {} messages', len(result))
    return jsonify(result)


@bp.route('/<int:channel_id>/messages/<int:message_id>', methods=['GET'])
async def get_single_message(channel_id, message_id):
    user_id = await token_check()
    await channel_check(user_id, channel_id)

    # TODO: check READ_MESSAGE_HISTORY permissions

    message = await app.storage.get_message(message_id)

    if not message:
        raise MessageNotFound()

    return jsonify(message)


@bp.route('/<int:channel_id>/messages', methods=['POST'])
async def create_message(channel_id):
    user_id = await token_check()
    guild_id = await channel_check(user_id, channel_id)

    j = validate(await request.get_json(), MESSAGE_CREATE)
    message_id = get_snowflake()

    # TODO: check SEND_MESSAGES permission
    # TODO: check SEND_TTS_MESSAGES
    # TODO: check connection to the gateway

    await app.db.execute(
        """
        INSERT INTO messages (id, channel_id, author_id, content, tts,
            mention_everyone, nonce, message_type)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
    """,
        message_id,
        channel_id,
        user_id,
        j['content'],
        j.get('tts', False),
        '@everyone' in j['content'],
        int(j.get('nonce', 0)),
        MessageType.DEFAULT.value
    )

    # TODO: dispatch_channel
    payload = await app.storage.get_message(message_id)
    await app.dispatcher.dispatch_guild(guild_id, 'MESSAGE_CREATE', payload)

    return jsonify(payload)


@bp.route('/<int:channel_id>/messages/<int:message_id>', methods=['PATCH'])
async def edit_message(channel_id, message_id):
    user_id = await token_check()
    guild_id = await channel_check(user_id, channel_id)

    author_id = await app.db.fetchval("""
    SELECT author_id FROM messages
    WHERE messages.id = $1
    """, message_id)

    if not author_id == user_id:
        raise Forbidden('You can not edit this message')

    j = await request.get_json()
    updated = 'content' in j or 'embed' in j

    if 'content' in j:
        await app.db.execute("""
        UPDATE messages
        SET content=$1
        WHERE messages.id = $2
        """, j['content'], message_id)

    # TODO: update embed

    message = await app.storage.get_message(message_id)

    # only dispatch MESSAGE_CREATE if we actually had any update to start with
    if updated:
        await app.dispatcher.dispatch_guild(guild_id,
                                            'MESSAGE_UPDATE', message)

    return jsonify(message)


@bp.route('/<int:channel_id>/messages/<int:message_id>', methods=['DELETE'])
async def delete_message(channel_id, message_id):
    user_id = await token_check()
    guild_id = await channel_check(user_id, channel_id)

    author_id = await app.db.fetchval("""
    SELECT author_id FROM messages
    WHERE messages.id = $1
    """, message_id)

    # TODO: MANAGE_MESSAGES permission check
    if author_id != user_id:
        raise Forbidden('You can not delete this message')

    await app.db.execute("""
    DELETE FROM messages
    WHERE messages.id = $1
    """, message_id)

    await app.dispatcher.dispatch_guild(guild_id, 'MESSAGE_DELETE', {
        'id': str(message_id),
        'channel_id': str(channel_id)
    })

    return '', 204


@bp.route('/<int:channel_id>/pins', methods=['GET'])
async def get_pins(channel_id):
    user_id = await token_check()
    await channel_check(user_id, channel_id)

    ids = await app.db.fetch("""
    SELECT message_id
    FROM channel_pins
    WHERE channel_id = $1
    ORDER BY message_id ASC
    """, channel_id)

    ids = [r['message_id'] for r in ids]
    res = []

    for message_id in ids:
        message = await app.storage.get_message(message_id)
        if message is not None:
            res.append(message)

    return jsonify(message)


@bp.route('/<int:channel_id>/pins/<int:message_id>', methods=['PUT'])
async def add_pin(channel_id, message_id):
    user_id = await token_check()
    guild_id = await channel_check(user_id, channel_id)

    # TODO: check MANAGE_MESSAGES permission

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

    await app.dispatcher.dispatch_guild(guild_id, 'CHANNEL_PINS_UPDATE', {
        'channel_id': str(channel_id),
        'last_pin_timestamp': timestamp.isoformat()
    })

    return '', 204


@bp.route('/<int:channel_id>/pins/<int:message_id>', methods=['DELETE'])
async def delete_pin(channel_id, message_id):
    user_id = await token_check()
    guild_id = await channel_check(user_id, channel_id)

    # TODO: check MANAGE_MESSAGES permission

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

    await app.dispatcher.dispatch_guild(guild_id, 'CHANNEL_PINS_UPDATE', {
        'channel_id': str(channel_id),
        'last_pin_timestamp': timestamp.isoformat()
    })

    return '', 204


@bp.route('/<int:channel_id>/typing', methods=['POST'])
async def trigger_typing(channel_id):
    user_id = await token_check()
    guild_id = await channel_check(user_id, channel_id)

    await app.dispatcher.dispatch_guild(guild_id, 'TYPING_START', {
        'channel_id': str(channel_id),
        'user_id': str(user_id),
        'timestamp': int(time.time()),
    })

    return '', 204

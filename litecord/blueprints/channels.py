import time

from quart import Blueprint, request, current_app as app, jsonify
from logbook import Logger

from ..auth import token_check
from ..snowflake import get_snowflake, snowflake_datetime
from ..enums import ChannelType, MessageType, GUILD_CHANS
from ..errors import Forbidden, ChannelNotFound, MessageNotFound
from ..schemas import validate, MESSAGE_CREATE

from .checks import channel_check, guild_check

log = Logger(__name__)
bp = Blueprint('channels', __name__)


@bp.route('/<int:channel_id>', methods=['GET'])
async def get_channel(channel_id):
    """Get a single channel's information"""
    user_id = await token_check()

    # channel_check takes care of checking
    # DMs and group DMs
    await channel_check(user_id, channel_id)
    chan = await app.storage.get_channel(channel_id)

    if not chan:
        raise ChannelNotFound('single channel not found')

    return jsonify(chan)


async def __guild_chan_sql(guild_id, channel_id, field: str) -> str:
    """Update a guild's channel id field to NULL,
    if it was set to the given channel id before."""
    return await app.db.execute(f"""
    UPDATE guilds
    SET {field} = NULL
    WHERE guilds.id = $1 AND {field} = $2
    """, guild_id, channel_id)


async def _update_guild_chan_text(guild_id: int, channel_id: int):
    res_embed = await __guild_chan_sql(
        guild_id, channel_id, 'embed_channel_id')

    res_widget = await __guild_chan_sql(
        guild_id, channel_id, 'widget_channel_id')

    res_system = await __guild_chan_sql(
        guild_id, channel_id, 'system_channel_id')

    # if none of them were actually updated,
    # ignore and dont dispatch anything
    if 'UPDATE 1' not in (res_embed, res_widget, res_system):
        return

    # at least one of the fields were updated,
    # dispatch GUILD_UPDATE
    guild = await app.storage.get_guild(guild_id)
    await app.dispatcher.dispatch_guild(
        guild_id, 'GUILD_UPDATE', guild)


async def _update_guild_chan_voice(guild_id: int, channel_id: int):
    res = await __guild_chan_sql(guild_id, channel_id, 'afk_channel_id')

    # guild didnt update
    if res == 'UPDATE 0':
        return

    guild = await app.storage.get_guild(guild_id)
    await app.dispatcher.dispatch_guild(
        guild_id, 'GUILD_UPDATE', guild)


async def _update_guild_chan_cat(guild_id: int, channel_id: int):
    # get all channels that were childs of the category
    childs = await app.db.fetch("""
    SELECT id
    FROM guild_channels
    WHERE guild_id = $1 AND parent_id = $2
    """, guild_id, channel_id)
    childs = [c['id'] for c in childs]

    # update every child channel to parent_id = NULL
    await app.db.execute("""
    UPDATE guild_channels
    SET parent_id = NULL
    WHERE guild_id = $1 AND parent_id = $2
    """, guild_id, channel_id)

    # tell all people in the guild of the category removal
    for child_id in childs:
        child = await app.storage.get_channel(child_id)
        await app.dispatcher.dispatch_guild(
            guild_id, 'CHANNEL_UPDATE', child
        )


async def delete_messages(channel_id):
    await app.db.execute("""
    DELETE FROM channel_pins
    WHERE channel_id = $1
    """, channel_id)

    await app.db.execute("""
    DELETE FROM user_read_state
    WHERE channel_id = $1
    """, channel_id)

    await app.db.execute("""
    DELETE FROM messages
    WHERE channel_id = $1
    """, channel_id)


async def guild_cleanup(channel_id):
    await app.db.execute("""
    DELETE FROM channel_overwrites
    WHERE channel_id = $1
    """, channel_id)

    await app.db.execute("""
    DELETE FROM invites
    WHERE channel_id = $1
    """, channel_id)

    await app.db.execute("""
    DELETE FROM webhooks
    WHERE channel_id = $1
    """, channel_id)


@bp.route('/<int:channel_id>', methods=['DELETE'])
async def close_channel(channel_id):
    user_id = await token_check()

    chan_type = await app.storage.get_chan_type(channel_id)
    ctype = ChannelType(chan_type)

    if ctype in GUILD_CHANS:
        _, guild_id = await channel_check(user_id, channel_id)
        chan = await app.storage.get_channel(channel_id)

        # the selected function will take care of checking
        # the sanity of tables once the channel becomes deleted.
        _update_func = {
            ChannelType.GUILD_TEXT: _update_guild_chan_text,
            ChannelType.GUILD_VOICE: _update_guild_chan_voice,
            ChannelType.GUILD_CATEGORY: _update_guild_chan_cat,
        }[ctype]

        main_tbl = {
            ChannelType.GUILD_TEXT: 'guild_text_channels',
            ChannelType.GUILD_VOICE: 'guild_voice_channels',

            # TODO: categories?
        }[ctype]

        await _update_func(guild_id, channel_id)

        # for some reason ON DELETE CASCADE
        # didn't work on my setup, so I delete
        # everything before moving to the main
        # channel table deletes
        await delete_messages(channel_id)
        await guild_cleanup(channel_id)

        await app.db.execute(f"""
        DELETE FROM {main_tbl}
        WHERE id = $1
        """, channel_id)

        await app.db.execute("""
        DELETE FROM guild_channels
        WHERE id = $1
        """, channel_id)

        await app.db.execute("""
        DELETE FROM channels
        WHERE id = $1
        """, channel_id)

        await app.dispatcher.dispatch_guild(
            guild_id, 'CHANNEL_DELETE', chan)
        return jsonify(chan)

    if ctype == ChannelType.DM:
        chan = await app.storage.get_channel(channel_id)

        # we don't ever actually delete DM channels off the database.
        # instead, we close the channel for the user that is making
        # the request via removing the link between them and
        # the channel on dm_channel_state
        await app.db.execute("""
        DELETE FROM dm_channel_state (user_id, dm_id)
        VALUES ($1, $2)
        """, user_id, channel_id)

        # nothing happens to the other party of the dm channel
        await app.dispacher.dispatch_user(user_id, 'CHANNEL_DELETE', chan)
        return jsonify(chan)

    if ctype == ChannelType.GROUP_DM:
        # TODO: group dm
        pass

    return '', 404


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
    _ctype, guild_id = await channel_check(user_id, channel_id)

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
    # we really need dispatch_channel to make dm messages work,
    # since they aren't part of any existing guild.
    payload = await app.storage.get_message(message_id)

    await app.dispatcher.dispatch('channel', channel_id,
                                  'MESSAGE_CREATE', payload)

    # TODO: dispatch the MESSAGE_CREATE to any mentioning user.

    for str_uid in payload['mentions']:
        uid = int(str_uid)

        await app.db.execute("""
        UPDATE user_read_state
        SET mention_count += 1
        WHERE user_id = $1 AND channel_id = $2
        """, uid, channel_id)

    return jsonify(payload)


@bp.route('/<int:channel_id>/messages/<int:message_id>', methods=['PATCH'])
async def edit_message(channel_id, message_id):
    user_id = await token_check()
    _ctype, guild_id = await channel_check(user_id, channel_id)

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

    # only dispatch MESSAGE_UPDATE if we actually had any update to start with
    if updated:
        await app.dispatcher.dispatch('channel', channel_id,
                                      'MESSAGE_UPDATE', message)

    return jsonify(message)


@bp.route('/<int:channel_id>/messages/<int:message_id>', methods=['DELETE'])
async def delete_message(channel_id, message_id):
    user_id = await token_check()
    _ctype, guild_id = await channel_check(user_id, channel_id)

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

    await app.dispatcher.dispatch(
        'channel', channel_id,
        'MESSAGE_DELETE', {
            'id': str(message_id),
            'channel_id': str(channel_id),

            # for lazy guilds
            'guild_id': str(guild_id),
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
    _ctype, guild_id = await channel_check(user_id, channel_id)

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
    _ctype, guild_id = await channel_check(user_id, channel_id)

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

    # TODO: dispatch_channel
    await app.dispatcher.dispatch_guild(guild_id, 'CHANNEL_PINS_UPDATE', {
        'channel_id': str(channel_id),
        'last_pin_timestamp': timestamp.isoformat()
    })

    return '', 204


@bp.route('/<int:channel_id>/typing', methods=['POST'])
async def trigger_typing(channel_id):
    user_id = await token_check()
    _ctype, guild_id = await channel_check(user_id, channel_id)

    # TODO: dispatch_channel
    await app.dispatcher.dispatch_guild(guild_id, 'TYPING_START', {
        'channel_id': str(channel_id),
        'user_id': str(user_id),
        'timestamp': int(time.time()),

        # guild_id for lazy guilds
        'guild_id': str(guild_id),
    })

    return '', 204


async def channel_ack(user_id, guild_id, channel_id, message_id: int = None):
    """ACK a channel."""

    if not message_id:
        message_id = await app.storage.chan_last_message(channel_id)

    res = await app.db.execute("""
    UPDATE user_read_state

    SET last_message_id = $1,
        mention_count = 0

    WHERE user_id = $2 AND channel_id = $3
    """, message_id, user_id, channel_id)

    if res == 'UPDATE 0':
        await app.db.execute("""
        INSERT INTO user_read_state
            (user_id, channel_id, last_message_id, mention_count)
        VALUES ($1, $2, $3, $4)
        """, user_id, channel_id, message_id, 0)

    if guild_id:
        await app.dispatcher.dispatch_user_guild(
            user_id, guild_id, 'MESSAGE_ACK', {
                'message_id': str(message_id),
                'channel_id': str(channel_id)
            })
    else:
        # TODO: use ChannelDispatcher
        await app.dispatcher.dispatch_user(
            user_id, 'MESSAGE_ACK', {
                'message_id': str(message_id),
                'channel_id': str(channel_id)
            })


@bp.route('/<int:channel_id>/messages/<int:message_id>/ack', methods=['POST'])
async def ack_channel(channel_id, message_id):
    user_id = await token_check()
    ctype, guild_id = await channel_check(user_id, channel_id)

    if ctype == ChannelType.DM:
        guild_id = None

    await channel_ack(user_id, guild_id, channel_id, message_id)

    return jsonify({
        # token seems to be used for
        # data collection activities,
        # so we never use it.
        'token': None
    })


@bp.route('/<int:channel_id>/messages/ack', methods=['DELETE'])
async def delete_read_state(channel_id):
    user_id = await token_check()
    await channel_check(user_id, channel_id)

    await app.db.execute("""
    DELETE FROM user_read_state
    WHERE user_id = $1 AND channel_id = $2
    """, user_id, channel_id)

    return '', 204

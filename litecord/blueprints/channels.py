import time

from quart import Blueprint, request, current_app as app, jsonify
from logbook import Logger

from litecord.auth import token_check
from litecord.enums import ChannelType, GUILD_CHANS
from litecord.errors import ChannelNotFound
from litecord.schemas import (
    validate, CHAN_UPDATE
)

from litecord.blueprints.checks import channel_check, channel_perm_check

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
    """Close or delete a channel."""
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
        DELETE FROM dm_channel_state
        WHERE user_id = $1 AND dm_id = $2
        """, user_id, channel_id)

        # unsubscribe
        await app.dispatcher.unsub('channel', channel_id, user_id)

        # nothing happens to the other party of the dm channel
        await app.dispatcher.dispatch_user(user_id, 'CHANNEL_DELETE', chan)

        return jsonify(chan)

    if ctype == ChannelType.GROUP_DM:
        # TODO: group dm
        pass

    raise ChannelNotFound()


async def _update_pos(channel_id, pos: int):
    await app.db.execute("""
    UPDATE guild_channels
    SET position = $1
    WHERE id = $2
    """, pos, channel_id)


async def _mass_chan_update(guild_id, channel_ids: int):
    for channel_id in channel_ids:
        chan = await app.storage.get_channel(channel_id)
        await app.dispatcher.dispatch(
            'guild', guild_id, 'CHANNEL_UPDATE', chan)


async def _update_channel_common(channel_id, guild_id: int, j: dict):
    if 'name' in j:
        await app.db.execute("""
        UPDATE guild_channels
        SET name = $1
        WHERE id = $2
        """, j['name'], channel_id)

    if 'position' in j:
        channel_data = await app.storage.get_channel_data(guild_id)

        chans = [None * len(channel_data)]
        for chandata in channel_data:
            chans.insert(chandata['position'], int(chandata['id']))

        # are we changing to the left or to the right?

        # left: [channel1, channel2, ..., channelN-1, channelN]
        #       becomes
        #       [channel1, channelN-1, channel2, ..., channelN]
        #       so we can say that the "main change" is
        #       channelN-1 going to the position channel2
        #       was occupying.
        current_pos = chans.index(channel_id)
        new_pos = j['position']

        # if the new position is bigger than the current one,
        # we're making a left shift of all the channels that are
        # beyond the current one, to make space
        left_shift = new_pos > current_pos

        # find all channels that we'll have to shift
        shift_block = (chans[current_pos:new_pos]
                       if left_shift else
                       chans[new_pos:current_pos]
                       )

        shift = -1 if left_shift else 1

        # do the shift (to the left or to the right)
        await app.db.executemany("""
        UPDATE guild_channels
        SET position = position + $1
        WHERE id = $2
        """, [(shift, chan_id) for chan_id in shift_block])

        await _mass_chan_update(guild_id, shift_block)

        # since theres now an empty slot, move current channel to it
        await _update_pos(channel_id, new_pos)


async def _update_text_channel(channel_id: int, j: dict):
    pass


async def _update_voice_channel(channel_id: int, j: dict):
    pass


@bp.route('/<int:channel_id>', methods=['PUT', 'PATCH'])
async def update_channel(channel_id):
    """Update a channel's information"""
    user_id = await token_check()
    ctype, guild_id = await channel_check(user_id, channel_id)

    if ctype not in GUILD_CHANS:
        raise ChannelNotFound('Can not edit non-guild channels.')

    await channel_perm_check(user_id, channel_id, 'manage_channels')
    j = validate(await request.get_json(), CHAN_UPDATE)

    # TODO: categories?
    update_handler = {
        ChannelType.GUILD_TEXT: _update_text_channel,
        ChannelType.GUILD_VOICE: _update_voice_channel,
    }[ctype]

    await _update_channel_common(channel_id, guild_id, j)
    await update_handler(channel_id, j)

    chan = await app.storage.get_channel(channel_id)
    await app.dispatcher.dispatch('guild', guild_id, 'CHANNEL_UPDATE', chan)
    return jsonify(chan)


@bp.route('/<int:channel_id>/typing', methods=['POST'])
async def trigger_typing(channel_id):
    user_id = await token_check()
    ctype, guild_id = await channel_check(user_id, channel_id)

    await app.dispatcher.dispatch('channel', channel_id, 'TYPING_START', {
        'channel_id': str(channel_id),
        'user_id': str(user_id),
        'timestamp': int(time.time()),

        # guild_id for lazy guilds
        'guild_id': str(guild_id) if ctype == ChannelType.GUILD_TEXT else None,
    })

    return '', 204


async def channel_ack(user_id, guild_id, channel_id, message_id: int = None):
    """ACK a channel."""

    if not message_id:
        message_id = await app.storage.chan_last_message(channel_id)

    await app.db.execute("""
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
    """, user_id, channel_id, message_id)

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
    """Acknowledge a channel."""
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
    """Delete the read state of a channel."""
    user_id = await token_check()
    await channel_check(user_id, channel_id)

    await app.db.execute("""
    DELETE FROM user_read_state
    WHERE user_id = $1 AND channel_id = $2
    """, user_id, channel_id)

    return '', 204

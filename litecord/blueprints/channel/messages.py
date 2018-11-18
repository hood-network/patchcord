from quart import Blueprint, request, current_app as app, jsonify

from logbook import Logger


from litecord.blueprints.auth import token_check
from litecord.blueprints.checks import channel_check, channel_perm_check
from litecord.blueprints.dms import try_dm_state
from litecord.errors import MessageNotFound, Forbidden, BadRequest
from litecord.enums import MessageType, ChannelType, GUILD_CHANS
from litecord.snowflake import get_snowflake
from litecord.schemas import validate, MESSAGE_CREATE


log = Logger(__name__)
bp = Blueprint('channel_messages', __name__)


def extract_limit(request, default: int = 50):
    try:
        limit = int(request.args.get('limit', default))

        if limit not in range(0, 100):
            raise ValueError()
    except (TypeError, ValueError):
        raise BadRequest('limit not int')

    return limit


def query_tuple_from_args(args: dict, limit: int) -> tuple:
    """Extract a 2-tuple out of request arguments."""
    before, after = None, None

    if 'around' in request.args:
        average = int(limit / 2)
        around = int(args['around'])

        after = around - average
        before = around + average

    elif 'before' in args:
        before = int(args['before'])
    elif 'after' in args:
        before = int(args['after'])

    return before, after


@bp.route('/<int:channel_id>/messages', methods=['GET'])
async def get_messages(channel_id):
    user_id = await token_check()

    # TODO: check READ_MESSAGE_HISTORY permission
    ctype, peer_id = await channel_check(user_id, channel_id)

    if ctype == ChannelType.DM:
        # make sure both parties will be subbed
        # to a dm
        await _dm_pre_dispatch(channel_id, user_id)
        await _dm_pre_dispatch(channel_id, peer_id)

    limit = extract_limit(request, 50)

    where_clause = ''
    before, after = query_tuple_from_args(request.args, limit)

    if before:
        where_clause += f'AND id < {before}'

    if after:
        where_clause += f'AND id > {after}'

    message_ids = await app.db.fetch(f"""
    SELECT id
    FROM messages
    WHERE channel_id = $1 {where_clause}
    ORDER BY id DESC
    LIMIT {limit}
    """, channel_id)

    result = []

    for message_id in message_ids:
        msg = await app.storage.get_message(message_id['id'], user_id)

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
    message = await app.storage.get_message(message_id, user_id)

    if not message:
        raise MessageNotFound()

    return jsonify(message)


async def _dm_pre_dispatch(channel_id, peer_id):
    """Do some checks pre-MESSAGE_CREATE so we
    make sure the receiving party will handle everything."""

    # check the other party's dm_channel_state

    dm_state = await app.db.fetchval("""
    SELECT dm_id
    FROM dm_channel_state
    WHERE user_id = $1 AND dm_id = $2
    """, peer_id, channel_id)

    if dm_state:
        # the peer already has the channel
        # opened, so we don't need to do anything
        return

    dm_chan = await app.storage.get_channel(channel_id)

    # dispatch CHANNEL_CREATE so the client knows which
    # channel the future event is about
    await app.dispatcher.dispatch_user(peer_id, 'CHANNEL_CREATE', dm_chan)

    # subscribe the peer to the channel
    await app.dispatcher.sub('channel', channel_id, peer_id)

    # insert it on dm_channel_state so the client
    # is subscribed on the future
    await try_dm_state(peer_id, channel_id)


@bp.route('/<int:channel_id>/messages', methods=['POST'])
async def create_message(channel_id):
    user_id = await token_check()
    ctype, guild_id = await channel_check(user_id, channel_id)

    if ctype in GUILD_CHANS:
        await channel_perm_check(user_id, channel_id, 'send_messages')

    j = validate(await request.get_json(), MESSAGE_CREATE)
    message_id = get_snowflake()

    # TODO: check connection to the gateway

    mentions_everyone = ('@everyone' in j['content'] and
                         await channel_perm_check(
                             user_id, channel_id, 'mention_everyone', False
                         )
                         )

    is_tts = (j.get('tts', False) and
              await channel_perm_check(
                  user_id, channel_id, 'send_tts_messages', False
              ))

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

        is_tts,
        mentions_everyone,

        int(j.get('nonce', 0)),
        MessageType.DEFAULT.value
    )

    payload = await app.storage.get_message(message_id, user_id)

    if ctype == ChannelType.DM:
        # guild id here is the peer's ID.
        await _dm_pre_dispatch(channel_id, user_id)
        await _dm_pre_dispatch(channel_id, guild_id)

    await app.dispatcher.dispatch('channel', channel_id,
                                  'MESSAGE_CREATE', payload)

    if ctype == ChannelType.GUILD_TEXT:
        for mention in payload['mentions']:
            uid = int(mention['id'])

            print('updating user read state', repr(uid), repr(channel_id))

            await app.db.execute("""
            UPDATE user_read_state
            SET mention_count = mention_count + 1
            WHERE user_id = $1
              AND channel_id = $2
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

    message = await app.storage.get_message(message_id, user_id)

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

    by_perm = await channel_perm_check(
        user_id, channel_id, 'manage_messages', False
    )

    by_ownership = author_id == user_id

    if not by_perm and not by_ownership:
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

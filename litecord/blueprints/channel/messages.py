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

import json
from pathlib import Path

from PIL import Image
from quart import Blueprint, request, current_app as app, jsonify
from logbook import Logger

from litecord.blueprints.auth import token_check
from litecord.blueprints.checks import channel_check, channel_perm_check
from litecord.blueprints.dms import try_dm_state
from litecord.errors import MessageNotFound, Forbidden, BadRequest
from litecord.enums import MessageType, ChannelType, GUILD_CHANS
from litecord.snowflake import get_snowflake
from litecord.schemas import validate, MESSAGE_CREATE
from litecord.utils import pg_set_json
from litecord.permissions import get_permissions

from litecord.embed.sanitizer import fill_embed
from litecord.embed.messages import process_url_embed
from litecord.blueprints.channel.dm_checks import dm_pre_check
from litecord.images import try_unlink


log = Logger(__name__)
bp = Blueprint('channel_messages', __name__)


def extract_limit(request_, default: int = 50, max_val: int = 100):
    """Extract a limit kwarg."""
    try:
        limit = int(request_.args.get('limit', default))

        if limit not in range(0, max_val + 1):
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

    ctype, peer_id = await channel_check(user_id, channel_id)
    await channel_perm_check(user_id, channel_id, 'read_history')

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
    await channel_perm_check(user_id, channel_id, 'read_history')

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


async def create_message(channel_id: int, actual_guild_id: int,
                         author_id: int, data: dict) -> int:
    message_id = get_snowflake()

    async with app.db.acquire() as conn:
        await pg_set_json(conn)

        await conn.execute(
            """
            INSERT INTO messages (id, channel_id, guild_id, author_id,
                content, tts, mention_everyone, nonce, message_type,
                embeds)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        """,
            message_id,
            channel_id,
            actual_guild_id,
            author_id,
            data['content'],

            data['tts'],
            data['everyone_mention'],

            data['nonce'],
            MessageType.DEFAULT.value,
            data.get('embeds') or []
        )

    return message_id

async def msg_guild_text_mentions(payload: dict, guild_id: int,
                                  mentions_everyone: bool, mentions_here: bool):
    """Calculates mention data side-effects."""
    channel_id = int(payload['channel_id'])

    # calculate the user ids we'll bump the mention count for
    uids = set()

    # first is extracting user mentions
    for mention in payload['mentions']:
        uids.add(int(mention['id']))

    # then role mentions
    for role_mention in payload['mention_roles']:
        role_id = int(role_mention)
        member_ids = await app.storage.get_role_members(role_id)

        for member_id in member_ids:
            uids.add(member_id)

    # at-here only updates the state
    # for the users that have a state
    # in the channel.
    if mentions_here:
        uids = set()

        await app.db.execute("""
        UPDATE user_read_state
        SET mention_count = mention_count + 1
        WHERE channel_id = $1
        """, channel_id)

    # at-here updates the read state
    # for all users, including the ones
    # that might not have read permissions
    # to the channel.
    if mentions_everyone:
        uids = set()

        member_ids = await app.storage.get_member_ids(guild_id)

        await app.db.executemany("""
        UPDATE user_read_state
        SET mention_count = mention_count + 1
        WHERE channel_id = $1 AND user_id = $2
        """, [(channel_id, uid) for uid in member_ids])

    for user_id in uids:
        await app.db.execute("""
        UPDATE user_read_state
        SET mention_count = mention_count + 1
        WHERE user_id = $1
            AND channel_id = $2
        """, user_id, channel_id)


async def msg_create_request() -> tuple:
    """Extract the json input and any file information
    the client gave to us in the request.

    This only applies to create message route.
    """
    form = await request.form
    request_json = await request.get_json() or {}

    # NOTE: embed isn't set on form data
    json_from_form = {
        'content': form.get('content', ''),
        'nonce': form.get('nonce', '0'),
        'tts': json.loads(form.get('tts', 'false')),
    }

    payload_json = json.loads(form.get('payload_json', '{}'))

    json_from_form.update(request_json)
    json_from_form.update(payload_json)

    files = await request.files

    # we don't really care about the given fields on the files dict, so
    # we only extract the values
    return json_from_form, [v for k, v in files.items()]


def msg_create_check_content(payload: dict, files: list, *, use_embeds=False):
    """Check if there is actually any content being sent to us."""
    has_content = bool(payload.get('content', ''))
    has_files = len(files) > 0

    embed_field = 'embeds' if use_embeds else 'embed'
    has_embed = embed_field in payload and payload.get(embed_field) is not None

    has_total_content = has_content or has_embed or has_files

    if not has_total_content:
        raise BadRequest('No content has been provided.')


async def msg_add_attachment(message_id: int, channel_id: int,
                             attachment_file) -> int:
    """Add an attachment to a message.

    Parameters
    ----------
    message_id: int
        The ID of the message getting the attachment.
    channel_id: int
        The ID of the channel the message belongs to.

        Exists because the attachment URL scheme contains
        a channel id. The purpose is unknown, but we are
        implementing Discord's behavior.
    attachment_file: quart.FileStorage
        quart FileStorage instance of the file.
    """

    attachment_id = get_snowflake()
    filename = attachment_file.filename

    # understand file info
    mime = attachment_file.mimetype
    is_image = mime.startswith('image/')

    img_width, img_height = None, None

    # extract file size
    # TODO: this is probably inneficient
    file_size = attachment_file.stream.getbuffer().nbytes

    if is_image:
        # open with pillow, extract image size
        image = Image.open(attachment_file.stream)
        img_width, img_height = image.size

        # NOTE: DO NOT close the image, as closing the image will
        # also close the stream.

        # reset it to 0 for later usage
        attachment_file.stream.seek(0)

    await app.db.execute(
        """
        INSERT INTO attachments
            (id, channel_id, message_id,
             filename, filesize,
             image, width, height)
        VALUES
            ($1, $2, $3, $4, $5, $6, $7, $8)
        """,
        attachment_id, channel_id, message_id,
        filename, file_size,
        is_image, img_width, img_height)

    ext = filename.split('.')[-1]

    with open(f'attachments/{attachment_id}.{ext}', 'wb') as attach_file:
        attach_file.write(attachment_file.stream.read())

    log.debug('written {} bytes for attachment id {}',
              file_size, attachment_id)

    return attachment_id


async def _spawn_embed(app_, payload, **kwargs):
    app_.sched.spawn(
        process_url_embed(
            app_.config, app_.storage, app_.dispatcher, app_.session,
            payload, **kwargs)
    )


@bp.route('/<int:channel_id>/messages', methods=['POST'])
async def _create_message(channel_id):
    """Create a message."""

    user_id = await token_check()
    ctype, guild_id = await channel_check(user_id, channel_id)

    actual_guild_id = None

    if ctype in GUILD_CHANS:
        await channel_perm_check(user_id, channel_id, 'send_messages')
        actual_guild_id = guild_id

    payload_json, files = await msg_create_request()
    j = validate(payload_json, MESSAGE_CREATE)

    msg_create_check_content(payload_json, files)

    # TODO: check connection to the gateway

    if ctype == ChannelType.DM:
        # guild_id is the dm's peer_id
        await dm_pre_check(user_id, channel_id, guild_id)

    can_everyone = await channel_perm_check(
        user_id, channel_id, 'mention_everyone', False
    )

    mentions_everyone = ('@everyone' in j['content']) and can_everyone
    mentions_here = ('@here' in j['content']) and can_everyone

    is_tts = (j.get('tts', False) and
              await channel_perm_check(
                  user_id, channel_id, 'send_tts_messages', False
              ))

    message_id = await create_message(
        channel_id, actual_guild_id, user_id, {
            'content': j['content'],
            'tts': is_tts,
            'nonce': int(j.get('nonce', 0)),
            'everyone_mention': mentions_everyone or mentions_here,

            # fill_embed takes care of filling proxy and width/height
            'embeds': ([await fill_embed(j['embed'])]
                       if j.get('embed') is not None
                       else []),
        })

    # for each file given, we add it as an attachment
    for pre_attachment in files:
        await msg_add_attachment(message_id, channel_id, pre_attachment)

    payload = await app.storage.get_message(message_id, user_id)

    if ctype == ChannelType.DM:
        # guild id here is the peer's ID.
        await _dm_pre_dispatch(channel_id, user_id)
        await _dm_pre_dispatch(channel_id, guild_id)

    await app.dispatcher.dispatch('channel', channel_id,
                                  'MESSAGE_CREATE', payload)

    # spawn url processor for embedding of images
    perms = await get_permissions(user_id, channel_id)
    if perms.bits.embed_links:
        await _spawn_embed(app, payload)

    # update read state for the author
    await app.db.execute("""
    UPDATE user_read_state
    SET last_message_id = $1
    WHERE channel_id = $2 AND user_id = $3
    """, message_id, channel_id, user_id)

    if ctype == ChannelType.GUILD_TEXT:
        await msg_guild_text_mentions(
            payload, guild_id, mentions_everyone, mentions_here)

    return jsonify(payload)


@bp.route('/<int:channel_id>/messages/<int:message_id>', methods=['PATCH'])
async def edit_message(channel_id, message_id):
    user_id = await token_check()
    _ctype, _guild_id = await channel_check(user_id, channel_id)

    author_id = await app.db.fetchval("""
    SELECT author_id FROM messages
    WHERE messages.id = $1
    """, message_id)

    if not author_id == user_id:
        raise Forbidden('You can not edit this message')

    j = await request.get_json()
    updated = 'content' in j or 'embed' in j
    old_message = await app.storage.get_message(message_id)

    if 'content' in j:
        await app.db.execute("""
        UPDATE messages
        SET content=$1
        WHERE messages.id = $2
        """, j['content'], message_id)

    if 'embed' in j:
        embeds = [await fill_embed(j['embed'])]

        await app.db.execute("""
        UPDATE messages
        SET embeds=$1
        WHERE messages.id = $2
        """, embeds, message_id)

        # do not spawn process_url_embed since we already have embeds.
    elif 'content' in j:
        # if there weren't any embed changes BUT
        # we had a content change, we dispatch process_url_embed but with
        # an artificial delay.

        # the artificial delay keeps consistency between the events, since
        # it makes more sense for the MESSAGE_UPDATE with new content to come
        # BEFORE the MESSAGE_UPDATE with the new embeds (based on content)
        perms = await get_permissions(user_id, channel_id)
        if perms.bits.embed_links:
            await _spawn_embed(app, {
                'id': message_id,
                'channel_id': channel_id,
                'content': j['content'],
                'embeds': old_message['embeds']
            }, delay=0.2)

    # only set new timestamp upon actual update
    if updated:
        await app.db.execute("""
        UPDATE messages
        SET edited_at = (now() at time zone 'utc')
        WHERE id = $1
        """, message_id)

    message = await app.storage.get_message(message_id, user_id)

    # only dispatch MESSAGE_UPDATE if any update
    # actually happened
    if updated:
        await app.dispatcher.dispatch('channel', channel_id,
                                      'MESSAGE_UPDATE', message)

    return jsonify(message)


async def _del_msg_fkeys(message_id: int):
    attachs = await app.db.fetch("""
    SELECT id FROM attachments
    WHERE message_id = $1
    """, message_id)

    attachs = [r['id'] for r in attachs]

    attachments = Path('./attachments')
    for attach_id in attachs:
        # anything starting with the given attachment shall be
        # deleted, because there may be resizes of the original
        # attachment laying around.
        for filepath in attachments.glob(f'{attach_id}*'):
            try_unlink(filepath)

    # after trying to delete all available attachments, delete
    # them from the database.

    # take the chance and delete all the data from the other tables too!

    tables = ['attachments', 'message_webhook_info',
              'message_reactions', 'channel_pins']

    for table in tables:
        await app.db.execute(f"""
        DELETE FROM {table}
        WHERE message_id = $1
        """, message_id)


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

    can_delete = by_perm or by_ownership
    if not can_delete:
        raise Forbidden('You can not delete this message')

    await _del_msg_fkeys(message_id)

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
